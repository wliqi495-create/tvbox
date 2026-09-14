#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def unpack_packer(p, a, c, k):
    """
    纯 Python 实现 Dean Edwards Packer 解密器 (Base62 / 词典映射)
    零外部依赖，严格遵守平台开发规范
    """
    def int2base(x, base):
        chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if x < 0:
            return "-" + int2base(-x, base)
        res = []
        while x > 0:
            res.append(chars[x % base])
            x //= base
        return "".join(reversed(res)) if res else "0"

    d = {}
    while c > 0:
        c -= 1
        key = int2base(c, a)
        val = k[c] if c < len(k) and k[c] else key
        d[key] = val

    def replace_token(match):
        w = match.group(0)
        return d.get(w, w)

    return re.sub(r'\b\w+\b', replace_token, p)

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        # 兜底默认域名
        self.defaultHost = "https://www.missav888.cc"
        self.baseHost = self.defaultHost
        # 导航发布站双活入口
        self.navUrls = ["https://x99dh.cc", "https://x99dh.one"]
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}

        # 启动时执行活链感知
        self._get_active_host()
        return True

    def getName(self):
        return "蝴蝶·MissAV自愈生产蜘蛛"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    # 动态活链调度自愈引擎
    def _resolve_nav_sites(self):
        """
        从 x99dh 导航站静默抓取并反解出 MissAV 最新镜像站地址
        """
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate"
        }

        for nav in self.navUrls:
            try:
                req = urllib.request.Request(nav, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
            except urllib.error.HTTPError as e:
                try:
                    raw = e.read()
                    if raw.startswith(b"\x1f\x8b"):
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
            except Exception:
                continue

            if not text:
                continue

            # 扫描 Base64 编码密文段
            b64_blocks = re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', text)
            for b in b64_blocks:
                try:
                    decoded = base64.b64decode(b).decode("utf-8", errors="ignore")
                    unquoted = urllib.parse.unquote(decoded)
                    if "MissAV" in unquoted and "[" in unquoted:
                        site_list = json.loads(unquoted)
                        for item in site_list:
                            if item.get("name") == "MissAV":
                                cand_urls = []
                                main_url = item.get("url", "")
                                if main_url:
                                    cand_urls.append(main_url)
                                for u_obj in item.get("urls", []):
                                    u = u_obj.get("url", "")
                                    if u and u not in cand_urls:
                                        cand_urls.append(u)

                                # 提取纯根域名 (去掉末尾的 /cn 等路径)
                                for c_url in cand_urls:
                                    parsed = urllib.parse.urlparse(c_url)
                                    base = "%s://%s" % (parsed.scheme, parsed.netloc)
                                    # 握手验活
                                    chk = self._fetch(base + "/dm247/cn", check_host=False)
                                    if chk.get("code") == 200:
                                        return base
                except Exception:
                    continue

        return self.defaultHost

    def _get_active_host(self):
        # 1. 优先读取持久缓存
        cached_host = self.getCache("missav_live_host")
        if cached_host and cached_host.startswith("http"):
            self.baseHost = cached_host
            return self.baseHost

        # 2. 缓存失效，自愈探活
        new_host = self._resolve_nav_sites()
        self.baseHost = new_host if new_host else self.defaultHost
        self.setCache("missav_live_host", self.baseHost)
        return self.baseHost

    def _fetch(self, target_url, referer="", check_host=True):
        if not target_url:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.baseHost + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.baseHost + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        last_err = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=12) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (404, 502, 503) and check_host and attempt == 0:
                    # 遭遇阻断或站点下线，清空缓存并立刻触发自愈
                    self.delCache("missav_live_host")
                    self._get_active_host()
                    target_url = re.sub(r'https?://[^/]+', self.baseHost, target_url)
                    continue
                err_raw = ""
                try:
                    err_raw = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_raw, "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if attempt == 0 and check_host:
                    self.delCache("missav_live_host")
                    self._get_active_host()
                    target_url = re.sub(r'https?://[^/]+', self.baseHost, target_url)
                    continue
                return {"code": -1, "text": "", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "err": last_err, "final_url": target_url}

    # 1. 首页分类矩阵
    def homeContent(self, filter):
        result = {
            "class": [
                {"type_name": "🔥最近更新", "type_id": "/dm539/cn/new"},
                {"type_name": "⭐今日热门", "type_id": "/dm301/cn/today-hot"},
                {"type_name": "📊本週热门", "type_id": "/dm170/cn/weekly-hot"},
                {"type_name": "🏆本月热门", "type_id": "/dm273/cn/monthly-hot"},
                {"type_name": "💬中文字幕", "type_id": "/dm278/cn/chinese-subtitle"},
                {"type_name": "✨新作上市", "type_id": "/dm635/cn/release"},
                {"type_name": "🔓无码流出", "type_id": "/dm817/cn/uncensored-leak"},
                {"type_name": "💎FC2", "type_id": "/dm597/cn/fc2"},
                {"type_name": "👑HEYZO", "type_id": "/dm2208642/cn/heyzo"},
                {"type_name": "♨️东京热", "type_id": "/dm42/cn/tokyohot"},
                {"type_name": "🔞一本道", "type_id": "/dm5199603/cn/1pondo"}
            ]
        }
        if filter:
            result["filters"] = {}
        return result

    def homeVideoContent(self):
        res = self.categoryContent("/dm539/cn/new", "1", False, {})
        return {"list": res.get("list", [])}

    # 2. 分类列表 (支持动态活链拼接)
    def categoryContent(self, tid, pg, filter, extend):
        del filter
        extend = extend if isinstance(extend, dict) else {}
        route = str(tid).strip()
        page_int = int(pg) if str(pg).isdigit() else 1

        clean_route = route.rstrip("/")
        if page_int > 1:
            req_url = "%s%s?page=%d" % (self.baseHost, clean_route, page_int)
        else:
            req_url = "%s%s" % (self.baseHost, clean_route)

        res = self._fetch(req_url)
        html_text = res.get("text", "")
        if not html_text:
            return {"page": page_int, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        pattern = re.compile(
            r'<a[^>]+href=["\']([^"\']*/cn/[a-zA-Z0-9_-]+)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*>([\s\S]*?)</a>',
            re.I
        )
        matches = pattern.findall(html_text)
        vod_list = []
        seen_urls = set()

        for href, alt, title_raw in matches:
            clean_url = href.strip()
            if clean_url in seen_urls or any(x in clean_url for x in ("actresses", "genres", "makers", "vip", "ranking")):
                continue
            seen_urls.add(clean_url)

            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            if not title:
                title = alt.strip()
            if not title:
                continue

            code_m = re.search(r'/cn/([a-zA-Z0-9_-]+)', clean_url)
            code_str = code_m.group(1).upper() if code_m else ""
            cover_pic = "https://spic2-147.71352.men/%s/cover-n.jpg" % code_str.lower()

            # 将链接转化为绝对路径
            full_vod_id = clean_url if clean_url.startswith("http") else urllib.parse.urljoin(self.baseHost, clean_url)

            vod_list.append({
                "vod_id": full_vod_id,
                "vod_name": title,
                "vod_pic": cover_pic,
                "vod_remarks": code_str,
                "style": {"type": "rect", "ratio": 1.78}
            })

        page_count = page_int + 1 if len(vod_list) >= 12 else page_int
        if page_count < 1:
            page_count = 1

        return {
            "page": page_int,
            "pagecount": page_count,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    # 3. 详情页：解密 Packer + 独立清晰度 Tabs 分流
    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_url = str(raw_id).strip()

        # 确保 target_url 跟随当前活跃 baseHost
        if not target_url.startswith("http"):
            target_url = urllib.parse.urljoin(self.baseHost, target_url)

        res = self._fetch(target_url)
        html_text = res.get("text", "")
        if not html_text:
            return {"list": []}

        title_m = re.search(r'<title>(.*?)</title>', html_text, re.I)
        raw_title = title_m.group(1).strip() if title_m else "精彩视频"
        vod_name = raw_title.split(" - ")[0].strip()

        poster_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html_text, re.I)
        vod_pic = poster_m.group(1).strip() if poster_m else ""

        # 执行原生 Packer 逆向解密
        packer_m = re.search(r"}\s*\(\s*['\"]([\s\S]*?)['\"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*['\"]([^'\"]+)['\"]\.split\(['\"]\|['\"]\)", html_text)

        from_list = []
        url_list = []

        if packer_m:
            p = packer_m.group(1)
            a = int(packer_m.group(2))
            c = int(packer_m.group(3))
            k = packer_m.group(4).split("|")
            unpacked_code = unpack_packer(p, a, c, k)

            source_1080 = re.search(r"source1280\s*=\s*['\"]([^'\"]+)['\"]", unpacked_code)
            source_720 = re.search(r"source842\s*=\s*['\"]([^'\"]+)['\"]", unpacked_code)
            source_auto = re.search(r"source\s*=\s*['\"]([^'\"]+)['\"]", unpacked_code)

            # 通过当前基准域名做 Jmpres 代理映射 (防 403 阻断)
            proxy_prefix = "%s/jmpres/\\1/" % self.baseHost

            if source_1080:
                u = source_1080.group(1)
                proxy_u = re.sub(r'https?://(([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})/', proxy_prefix, u)
                from_list.append("1080P超清")
                url_list.append("正片$%s" % proxy_u)

            if source_720:
                u = source_720.group(1)
                proxy_u = re.sub(r'https?://(([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})/', proxy_prefix, u)
                from_list.append("720P高清")
                url_list.append("正片$%s" % proxy_u)

            if source_auto:
                u = source_auto.group(1)
                proxy_u = re.sub(r'https?://(([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})/', proxy_prefix, u)
                from_list.append("自适应线路")
                url_list.append("正片$%s" % proxy_u)

        if not from_list:
            from_list.append("官方原线")
            url_list.append("正片$%s" % target_url)

        play_from = "$$$".join(from_list)
        play_url = "$$$".join(url_list)

        intro_desc = (
            "【🦋 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "【当前接入节点】: %s (动态自愈引擎已就绪)\n"
            "影片标题：%s"
        ) % (self.tgGroup, self.baseHost, vod_name)
        escaped_desc = intro_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        return {
            "list": [{
                "vod_id": target_url,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": "HD高清",
                "vod_content": escaped_desc,
                "vod_play_from": play_from,
                "vod_play_url": play_url
            }]
        }

    # 4. 播放器：parse=0 直通中继
    def playerContent(self, flag, id, vipFlags):
        play_url = str(id).strip()
        headers = {
            "User-Agent": self._ua,
            "Referer": self.baseHost + "/",
            "Accept": "*/*"
        }
        is_page = not play_url.endswith(".m3u8") and not play_url.endswith(".mp4")
        return {
            "parse": 1 if is_page else 0,
            "jx": 0,
            "url": play_url,
            "header": headers
        }

    # 5. 搜索功能
    def searchContent(self, key, quick, pg="1"):
        page_int = int(pg) if str(pg).isdigit() else 1
        encoded_key = urllib.parse.quote(key)
        
        if page_int > 1:
            search_url = "%s/cn/search/%s?page=%d" % (self.baseHost, encoded_key, page_int)
        else:
            search_url = "%s/cn/search/%s" % (self.baseHost, encoded_key)

        res = self._fetch(search_url)
        html_text = res.get("text", "")
        if not html_text:
            return {"page": page_int, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        matches = re.findall(
            r'<a[^>]+href=["\']([^"\']*/cn/[a-zA-Z0-9_-]+)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*>([\s\S]*?)</a>',
            html_text,
            re.I
        )
        vod_list = []
        seen_urls = set()

        for href, alt, title_raw in matches:
            clean_url = href.strip()
            if clean_url in seen_urls or any(x in clean_url for x in ("actresses", "genres", "makers", "vip", "ranking")):
                continue
            seen_urls.add(clean_url)

            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            if not title:
                title = alt.strip()
            if not title:
                continue

            code_m = re.search(r'/cn/([a-zA-Z0-9_-]+)', clean_url)
            code_str = code_m.group(1).upper() if code_m else ""
            cover_pic = "https://spic2-147.71352.men/%s/cover-n.jpg" % code_str.lower()
            full_vod_id = clean_url if clean_url.startswith("http") else urllib.parse.urljoin(self.baseHost, clean_url)

            vod_list.append({
                "vod_id": full_vod_id,
                "vod_name": title,
                "vod_pic": cover_pic,
                "vod_remarks": code_str,
                "style": {"type": "rect", "ratio": 1.78}
            })

        return {
            "page": page_int,
            "pagecount": page_int + 1 if len(vod_list) >= 12 else page_int,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "MissAV自愈生产蜘蛛运行正常"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}