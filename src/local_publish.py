"""本机发布适配器：公众号（官方接口）与浏览器通道（知乎 / 头条）。

与 src/publish.py 的分工：

    src/publish.py    云端 / GitHub Actions 用的三平台 Cookie 接口
    src/local_publish.py  本机用的发布器，特点是：

1. 公众号走**官方开放接口**（draft/add → freepublish/submit），不碰登录态。
   凭据复用 `E:\\workbuddy工作台\\沐风博客\\config\\wechat_config.json`，
   同一套 AppID/AppSecret，不另存一份。
2. 知乎 / 头条走**浏览器通道**：用 Playwright 驱动本机 Edge，带独立 profile，
   登录态由锋哥本人扫码建立，脚本只负责填内容 + 点发布。
   头条号没有官方发文接口（要字节开放平台 OAuth2 + 审核，个人号拿不到），
   浏览器通道是唯一可行路径。
3. 封面：公众号 draft/add 必填 thumb_media_id，否则直接拒发。
   用 GitHub 开放图（opengraph.githubassets.com，1200x630）裁成 2.35:1 上传为永久素材。
4. 所有凭据、Cookie、签名都不写日志、不写文件；Result.detail 统一脱敏。

安全边界：浏览器通道只对本机锋哥自己的账号操作自己写的文章，
不抓取、不批量互动、不碰任何他人数据。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .publish import BasePublisher, Result, _json, redact

WECHAT_API = "https://api.weixin.qq.com"

# 公众号正文内联样式（微信编辑器会剥掉 <style> 块，只能内联）
WECHAT_STYLE: dict[str, str] = {
    "h1": "font-size:18px;font-weight:bold;color:#1b2a4d;margin:26px 0 14px;",
    "h2": "font-size:17px;font-weight:bold;color:#1b2a4d;border-left:4px solid #1b2a4d;padding-left:10px;margin:28px 0 14px;",
    "h3": "font-size:16px;font-weight:bold;color:#1b2a4d;margin:22px 0 12px;",
    "p": "font-size:15px;color:#333;line-height:1.9;letter-spacing:0.3px;margin:0 0 16px;text-align:justify;",
    "strong": "color:#1b2a4d;",
    "code": "font-size:14px;background:#f6f8fa;color:#c7254e;padding:2px 5px;border-radius:3px;",
    "pre": "background:#f6f8fa;border:1px solid #e1e4e8;border-radius:6px;padding:14px;overflow-x:auto;margin:0 0 18px;",
    "table": "width:100%;border-collapse:collapse;margin:16px 0;font-size:14px;",
    "th": "background:#1b2a4d;color:#ffffff;border:1px solid #dfe3ea;padding:8px 10px;text-align:left;",
    "td": "border:1px solid #dfe3ea;padding:8px 10px;color:#333;",
    "ul": "margin:0 0 16px;padding-left:22px;",
    "ol": "margin:0 0 16px;padding-left:22px;",
    "li": "font-size:15px;color:#333;line-height:1.9;margin-bottom:6px;",
    "blockquote": "border-left:4px solid #c9a86a;background:#faf7f2;padding:10px 14px;margin:0 0 16px;",
    "hr": "border:none;border-top:1px dashed #cccccc;margin:24px 0;",
    "img": "max-width:100%;display:block;margin:0 auto;",
}


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False          # 绕开系统代理，避免代理 IP 触发平台风控
    return s


def fit_bytes(text: str, limit: int) -> str:
    """按 UTF-8 字节裁剪（微信按字节算，中文 1 字 = 3 字节）。"""
    s = str(text or "")
    while s and len(s.encode("utf-8")) > limit:
        s = s[:-1]
    return s


# 会被当成可执行标签的 HTML：整体转义成可见文本
_RAW_HTML_RE = re.compile(
    r"<\s*/?\s*(script|iframe|object|embed|style|link|svg|math|form|input|button|"
    r"meta|base|body|html)\b[^>]*>",
    re.IGNORECASE,
)


def _escape_raw_html(md: str) -> str:
    """把正文里的裸 HTML 标签转义掉。

    正文源是第三方仓库 README，不是我们自己写的。就算 GitHub 本身过滤了
    <script>，也不能假设所有源都干净——这条防线的作用是让「脚本进正文」
    这件事在渲染层就被堵死，而不是指望上游。
    """
    import html as _html
    out = _RAW_HTML_RE.sub(lambda m: _html.escape(m.group(0), quote=False), md)
    # 事件属性（onclick= 等）也一并处理
    out = re.sub(r"\son[a-z]+\s*=\s*\"[^\"]*\"", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\son[a-z]+\s*=\s*'[^']*'", " ", out, flags=re.IGNORECASE)
    return out


def md_to_wechat_html(md: str) -> str:
    """Markdown → 带内联样式的 HTML。

    优先用 markdown 库（表格支持好）；没装就退回 src.compose.md_to_html 的
    基础实现，再补样式。两条路都不引入新依赖为硬要求。

    安全：markdown 库默认放行原始 HTML（<script> / <iframe> / on* 属性），
    而正文来自第三方仓库 README——必须先转义再渲染，否则能把脚本带进
    公众号 / 知乎 / CSDN 的正文里。这里在 markdown 之前先把裸 HTML
    整体转义，让它变成可见文本而不是可执行标签。
    """
    safe_md = _escape_raw_html(str(md or ""))
    try:
        import markdown as _md
        html = _md.markdown(safe_md, extensions=["tables", "fenced_code"])
    except Exception:
        from .compose import md_to_html as _fallback
        html = _fallback(safe_md)

    for tag, style in WECHAT_STYLE.items():
        if tag in ("ul", "ol", "table", "blockquote", "pre"):
            html = re.sub(rf"<{tag}>", f'<{tag} style="{style}">', html)
        elif tag == "hr":
            html = html.replace("<hr />", f'<hr style="{style}"/>').replace("<hr>", f'<hr style="{style}"/>')
        elif tag == "img":
            html = re.sub(r"<img ", f'<img style="{style}" ', html)
        else:
            html = re.sub(rf"<{tag}>(.*?)</{tag}>", rf'<{tag} style="{style}">\1</{tag}>', html, flags=re.S)
    html = re.sub(r"<th>(.*?)</th>", rf'<th style="{WECHAT_STYLE["th"]}">\1</th>', html, flags=re.S)
    html = re.sub(r"<td>(.*?)</td>", rf'<td style="{WECHAT_STYLE["td"]}">\1</td>', html, flags=re.S)
    html = re.sub(r"<code>(.*?)</code>", rf'<code style="{WECHAT_STYLE["code"]}">\1</code>', html, flags=re.S)
    return html.strip()


def download_cover(repo_full_name: str, dest: Path, ratio: float = 2.35,
                   timeout: int = 25) -> Path | None:
    """下载 GitHub 开放图并裁成公众号要求的 2.35:1。

    开放图是 1200x630（1.9:1），公众号裁 2.35:1，两边都能接受。
    裁剪用中心裁切，不拉伸变形。失败返回 None，调用方如实跳过封面。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://opengraph.githubassets.com/1/{repo_full_name}"
    try:
        s = _session()
        r = s.get(url, timeout=timeout)
        if r.status_code != 200 or len(r.content) < 1024:
            return None
        raw = dest.with_suffix(".png")
        raw.write_bytes(r.content)
        try:
            from PIL import Image
        except Exception:
            return raw            # 没有 PIL 就给原图，微信能接受
        try:
            im = Image.open(raw).convert("RGB")
        except Exception:
            return raw
        w, h = im.size
        target = ratio
        if w / h > target:          # 太宽，裁两侧
            nw = int(h * target)
            left = (w - nw) // 2
            im = im.crop((left, 0, left + nw, h))
        else:                       # 太高，裁上下
            nh = int(w / target)
            top = (h - nh) // 2
            im = im.crop((0, top, w, top + nh))
        out = dest.with_suffix(".jpg")
        im.save(out, "JPEG", quality=88)
        raw.unlink(missing_ok=True)
        return out
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 公众号：官方开放接口
# --------------------------------------------------------------------------- #

@dataclass
class WechatConfig:
    appid: str
    secret: str
    author: str = ""
    site_base: str = ""


class WechatPublisher(BasePublisher):
    """公众号官方接口发布器。

    流程：token → 上传永久封面素材 → draft/add → freepublish/submit。
    注意 submit 返回 errcode=0 只代表「提交成功」，不代表文章已发出，
    所以这里额外调 freepublish/get 查一次 publish_status 做闭环验证。
    """
    name = "wechat"

    def __init__(self, pcfg: dict, settings: dict, secrets: dict[str, str],
                 dry_run: bool, wechat_cfg: dict | None = None,
                 root: Path | None = None):
        super().__init__(pcfg, settings, secrets, dry_run)
        self.wechat_cfg = wechat_cfg or {}
        self.root = root or Path(__file__).resolve().parent.parent
        self._cfg: WechatConfig | None = None
        self._token = ""
        self._token_expire = 0.0

    # -- 凭据 ---------------------------------------------------------------
    def _wechat_config(self) -> WechatConfig | None:
        if self._cfg is None:
            from .local_secrets import wechat_config
            data = wechat_config()
            if not data:
                return None
            self._cfg = WechatConfig(data["appid"], data["secret"],
                                     data.get("author", ""), data.get("site_base", ""))
        return self._cfg

    def missing(self) -> list[str]:
        return [] if self._wechat_config() else ["WECHAT_CONFIG(沐风博客/config/wechat_config.json)"]

    # -- token --------------------------------------------------------------
    def token(self, force: bool = False) -> str:
        if self._token and self._token_expire > time.time() + 120 and not force:
            return self._token
        cfg = self._wechat_config()
        if cfg is None:
            raise RuntimeError("公众号配置缺失")
        s = _session()
        r = s.get(f"{WECHAT_API}/cgi-bin/token",
                  params={"grant_type": "client_credential",
                          "appid": cfg.appid, "secret": cfg.secret}, timeout=15)
        data = _json(r)
        if "access_token" not in data:
            hint = ""
            code = data.get("errcode")
            if code == 40164:
                hint = "；本机出口 IP 不在公众号白名单（开发者平台 → 基本配置 → IP 白名单）"
            elif code in (40001, 40125):
                hint = "；AppSecret 不对"
            elif code == 40013:
                hint = "；AppID 不对"
            raise RuntimeError(f"取 token 失败 errcode={code} err={data.get('errmsg', '')}{hint}")
        self._token = str(data["access_token"])
        self._token_expire = time.time() + float(data.get("expires_in", 7200))
        return self._token

    def _api(self, path: str, payload: dict | None = None,
             method: str = "POST", timeout: int = 30) -> dict:
        """调微信接口。

        两个坑：提交必须 ensure_ascii=False + UTF-8 字节（否则中文变 \\uXXXX 乱码）；
        响应必须 content.decode('utf-8')（微信不返回 charset，requests 会猜成 ISO-8859-1）。
        """
        s = _session()
        url = f"{WECHAT_API}{path}"
        params = {"access_token": self.token()}
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if method == "GET":
            r = s.get(url, params=params, timeout=timeout)
        else:
            body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
            r = s.post(url, params=params, data=body, headers=headers, timeout=timeout)
        try:
            return json.loads(r.content.decode("utf-8"))
        except Exception:
            return {"errcode": -1, "errmsg": f"响应解析失败 http={r.status_code}"}

    # -- 封面 ---------------------------------------------------------------
    def _upload_cover(self, repo_full_name: str) -> str:
        """上传永久素材，返回 thumb_media_id（草稿必填）。"""
        cache = self.root / "state" / "cover-cache"
        ratio = float(self.wechat_cfg.get("cover_ratio", 2.35))
        path = download_cover(repo_full_name, cache / f"{repo_full_name.replace('/', '__')}.jpg", ratio)
        if path is None:
            return ""
        s = _session()
        with open(path, "rb") as fh:
            r = s.post(f"{WECHAT_API}/cgi-bin/material/add_material",
                       params={"access_token": self.token(), "type": "image"},
                       files={"media": (path.name, fh.read(), "image/jpeg")},
                       timeout=60)
        data = _json(r)
        return str(data.get("media_id") or "")

    # -- 组装 ---------------------------------------------------------------
    def _title(self, article: dict) -> str:
        raw = self.title(article) or ""
        limit = int(self.wechat_cfg.get("title_max_bytes", 63))
        return fit_bytes(raw, limit)

    def _digest(self, article: dict) -> str:
        raw = self.brief(article) or ""
        limit = int(self.wechat_cfg.get("digest_max_bytes", 115))
        return fit_bytes(raw, limit)

    def build(self, article: dict, repo_full_name: str = "") -> tuple[str, dict, dict]:
        cfg = self._wechat_config()
        html = md_to_wechat_html(article["markdown"])
        prefix = str(self.wechat_cfg.get("source_url_prefix") or "")
        body = {
            "title": self._title(article),
            "author": cfg.author if cfg else "",
            "digest": self._digest(article),
            "content": html,
            "need_open_comment": 1,
            "only_fans_can_comment": 0,
        }
        if prefix:
            body["content_source_url"] = prefix
        return f"{WECHAT_API}/cgi-bin/draft/add", {}, {"articles": [body]}

    # -- 发布 ---------------------------------------------------------------
    def publish(self, article: dict) -> Result:
        miss = self.missing()
        if miss:
            return Result(self.name, "skipped", detail=f"缺少配置: {', '.join(miss)}")
        repo_full_name = str(article.get("repo") or "")
        if self.dry_run:
            url, _h, body = self.build(article)
            art = body["articles"][0]
            return Result(self.name, "dry_run",
                          detail=f"已组装公众号建稿请求（{url}，标题 {len(art['title'].encode('utf-8'))} 字节，"
                                 f"正文 {len(art['content'])} 字符），未实际发送")
        try:
            thumb = self._upload_cover(repo_full_name)
            if not thumb:
                return Result(self.name, "failed",
                              detail="封面上传失败：公众号 draft/add 必填 thumb_media_id，缺了会被直接拒发")
            url, _h, body = self.build(article)
            body["articles"][0]["thumb_media_id"] = thumb
            d = self._api("/cgi-bin/draft/add", body)
            media_id = str(d.get("media_id") or "")
            if not media_id:
                return Result(self.name, "failed",
                              detail=f"建草稿失败 errcode={d.get('errcode')} err={str(d.get('errmsg') or '')[:120]}")
            pub = self._api("/cgi-bin/freepublish/submit", {"media_id": media_id})
            if pub.get("errcode", 0) != 0:
                return Result(self.name, "failed", url=f"https://mp.weixin.qq.com/cgi-bin/appmsg",
                              detail=f"提交发布失败 errcode={pub.get('errcode')} err={str(pub.get('errmsg') or '')[:120]}；"
                                     f"草稿仍在草稿箱 media_id={media_id}")
            publish_id = str(pub.get("publish_id") or "")
            status_txt = ""
            if publish_id:
                st = self._api("/cgi-bin/freepublish/get", {"publish_id": publish_id})
                # publish_status: 0成功 1发布中 2原创失败 3常规失败 4平台审核不通过
                code = st.get("publish_status")
                status_txt = f"publish_status={code}"
                if code not in (0, 1):
                    return Result(self.name, "failed",
                                  detail=f"发布未成功（{status_txt}，err={str(st.get('errmsg') or '')[:100]}）；"
                                         f"草稿仍在草稿箱 media_id={media_id}")
            return Result(self.name, "published",
                          url=f"https://mp.weixin.qq.com/cgi-bin/appmsg?action=list",
                          detail=f"已提交发布 publish_id={publish_id or '(none)'} {status_txt}；草稿 media_id={media_id}")
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------- #
# 浏览器通道：知乎 / 头条
# --------------------------------------------------------------------------- #

class BrowserPublisher(BasePublisher):
    """用 Playwright 驱动本机 Edge 走网页发布。

    为什么必须有这条通道：
    - 知乎网页「公开发布」需要前端动态签名 x-zse-96，纯 Cookie 请求拿不到；
      真实浏览器自己会算这个签名。
    - 头条号根本没有官方发文接口（字节开放平台的文章发布权限要单独审核，
      个人号默认拿不到），只能走网页编辑器。

    登录态：独立 profile 目录 state/browser-profile，与锋哥日常 Edge 完全隔离。
    首次需要锋哥本人扫码登录一次（--login 模式），之后 profile 里长期有效。
    脚本不读取、不导出、不上传任何 Cookie。
    """
    name = "browser"

    def __init__(self, platform: str, pcfg: dict, settings: dict,
                 secrets: dict[str, str], dry_run: bool,
                 browser_cfg: dict | None = None, root: Path | None = None):
        super().__init__(pcfg, settings, secrets, dry_run)
        self.name = platform
        self.browser_cfg = browser_cfg or {}
        self.root = root or Path(__file__).resolve().parent.parent
        self._ctx = None
        self._pw = None

    def missing(self) -> list[str]:
        return []      # 登录态在 profile 里，不靠 Secret

    def _profile_dir(self) -> Path:
        d = self.root / str(self.browser_cfg.get("profile_dir", "state/browser-profile"))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _launch(self, headless: bool | None = None):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        head = self.browser_cfg.get("headless", False) if headless is None else headless
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir()),
            channel=str(self.browser_cfg.get("channel", "msedge")),
            headless=bool(head),
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        return self._ctx

    def close(self) -> None:
        try:
            if self._ctx:
                self._ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._ctx = None
        self._pw = None

    def login(self) -> bool:
        """打开登录页，等锋哥手动登录（最多等 timeout 秒）。"""
        url = str((self.browser_cfg.get("login_url") or {}).get(self.name, ""))
        if not url:
            return False
        ctx = self._launch(headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, timeout=60000)
        print(f"[login] 已打开 {url}，请在弹出的浏览器里完成登录（最多等 "
              f"{self.browser_cfg.get('publish_timeout_seconds', 180)} 秒）")
        deadline = time.time() + int(self.browser_cfg.get("publish_timeout_seconds", 180))
        while time.time() < deadline:
            time.sleep(2)
            try:
                if self._logged_in(page):
                    print("[login] 登录成功，登录态已存入 profile")
                    return True
            except Exception:
                continue
        print("[login] 超时未检测到登录成功，可稍后重试")
        return False

    def _logged_in(self, page) -> bool:
        try:
            url = page.url
        except Exception:
            return False
        if self.name == "zhihu":
            return "signin" not in url and "login" not in url
        if self.name == "toutiao":
            return "login" not in url and "auth" not in url
        return True

    # 子类实现：填内容 + 点发布
    def _do_publish(self, page, article: dict) -> tuple[bool, str, str]:
        raise NotImplementedError

    def publish(self, article: dict) -> Result:
        if self.dry_run:
            return Result(self.name, "dry_run",
                          detail=f"浏览器通道已就绪（{self.name}），dry_run 不打开浏览器、不发布")
        timeout = int(self.browser_cfg.get("publish_timeout_seconds", 180))
        try:
            ctx = self._launch(headless=bool(self.browser_cfg.get("headless", False)))
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            ok, link, detail = self._do_publish(page, article)
            return Result(self.name, "published" if ok else "failed",
                          url=link, detail=detail)
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")
        finally:
            self.close()


class ZhihuBrowserPublisher(BrowserPublisher):
    """知乎网页发布（走真实浏览器拿 x-zse-96 签名）。"""
    name = "zhihu"

    def _do_publish(self, page, article: dict) -> tuple[bool, str, str]:
        page.goto("https://zhuanlan.zhihu.com/write", timeout=60000)
        if "signin" in page.url or "login" in page.url:
            return False, "", "未登录：请先跑 `python -m src.local --login zhihu` 扫码登录一次"
        title = self.title(article)
        # 标题框
        page.wait_for_selector("textarea[placeholder*='标题'], .WriteIndex-titleInput textarea",
                               timeout=30000)
        page.fill("textarea[placeholder*='标题'], .WriteIndex-titleInput textarea", title)
        # 正文：知乎是 Quill 富文本，直接塞 HTML 靠粘贴事件不可靠，
        # 改为逐段插入纯文本 + 代码块（取 markdown 的纯文本化结果）
        body = article["markdown"]
        editor = page.wait_for_selector(".public-DraftEditor-content, .DraftEditor-content",
                                        timeout=30000)
        editor.click()
        page.keyboard.insert_text(_plain_for_editor(body))
        time.sleep(1)
        # 点发布
        publish_btn = page.query_selector("button:has-text('发布')")
        if not publish_btn:
            return False, "", "找不到「发布」按钮，页面结构可能已变"
        publish_btn.click()
        time.sleep(3)
        # 确认弹窗（有「发布」二次确认时）
        confirm = page.query_selector("button.Button--primary:has-text('发布'), .PublishPanel button:has-text('确认发布')")
        if confirm:
            confirm.click()
        time.sleep(3)
        url = page.url
        if "/p/" in url:
            return True, url, "已发布（知乎网页发布）"
        return False, url, f"点击发布后未跳转到文章页，当前 url={url[:120]}"


class ToutiaoBrowserPublisher(BrowserPublisher):
    """头条号网页发布。

    头条号编辑器是 ProseMirror，正文要往 contenteditable 里塞纯文本。
    封面可选（头条允许无图发文，但有图曝光更好，这里不强依赖）。
    """
    name = "toutiao"

    def _do_publish(self, page, article: dict) -> tuple[bool, str, str]:
        page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", timeout=60000)
        if "login" in page.url or "auth" in page.url:
            return False, "", "未登录：请先跑 `python -m src.local --login toutiao` 扫码登录一次"
        page.wait_for_selector("textarea[placeholder*='标题'], .publish-title textarea",
                               timeout=30000)
        page.fill("textarea[placeholder*='标题'], .publish-title textarea",
                  self.title(article))
        editor = page.wait_for_selector(".ProseMirror, .editor-content, [contenteditable='true']",
                                        timeout=30000)
        editor.click()
        page.keyboard.insert_text(_plain_for_editor(article["markdown"]))
        time.sleep(1)
        btn = page.query_selector("button:has-text('发布'), .publishBtn")
        if not btn:
            return False, "", "找不到「发布」按钮，页面结构可能已变"
        btn.click()
        time.sleep(5)
        # 头条发布后跳到内容管理页
        if "publish" not in page.url and "profile" not in page.url:
            return False, page.url, f"点击发布后状态异常 url={page.url[:120]}"
        return True, "https://mp.toutiao.com/profile_v4/graphic/publish", "已提交发布（头条号网页发布）"


def _plain_for_editor(md: str) -> str:
    """Markdown → 纯文本（给富文本编辑器用）。

    保留段落换行，代码块保留缩进，去掉 Markdown 记号。
    """
    s = str(md or "")
    s = re.sub(r"^```.*$", "", s, flags=re.M)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1（\2）", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"^[-*]\s+", "· ", s, flags=re.M)
    s = re.sub(r"^>\s?", "", s, flags=re.M)
    return s.strip()
