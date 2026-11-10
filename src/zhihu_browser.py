"""知乎专栏发布器（浏览器通道）。

为什么必须走浏览器：
知乎公开发布要浏览器自己算签名 `x-zse-96`（由页面的 JS 在请求拦截器里加），
纯 HTTP 带 Cookie 请求会被拒（40003 / 缺少签名）。
所以只能驱动真实浏览器，让页面自己发。

编辑器技术栈（2026-11-10 实测）：
    标题  textarea[placeholder='请输入标题（最多 100 个字）']
    正文  Draft.js → .public-DraftEditor-content / [data-contents=true]

⚠️ Draft.js 的坑：**不能直接设 innerHTML**（React 状态不会更新，
   点发布时存的是空的）。必须用 insert_text 模拟真实输入。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from .publish import Result


class ZhihuBrowserPublisher:
    """知乎专栏发布器。"""

    name = "zhihu"

    def __init__(self, browser_cfg: dict | None = None, root: Path | None = None):
        self.browser_cfg = browser_cfg or {}
        self.root = root or Path(__file__).resolve().parent.parent
        self._ctx = None
        self._pw = None

    def _profile_dir(self) -> Path:
        d = self.root / str(self.browser_cfg.get("profile_dir", "state/browser-profile"))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _launch(self, headless: bool = True):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        # channel: 云端（Linux runner）用自带的 chromium，本机用 msedge。
        # 配置里 channel 写成空字符串表示「用 Playwright 自带浏览器」。
        channel = str(self.browser_cfg.get("channel", "msedge") or "").strip()
        launch_kw: dict[str, Any] = {
            "user_data_dir": str(self._profile_dir()),
            "headless": headless,
            "args": ["--disable-blink-features=AutomationControlled"],
            "viewport": {"width": 1440, "height": 900},
            "locale": "zh-CN",
        }
        if channel:
            launch_kw["channel"] = channel
        self._ctx = self._pw.chromium.launch_persistent_context(**launch_kw)
        self._inject_cookies(self._ctx)
        return self._ctx

    def _inject_cookies(self, ctx) -> None:
        """云端没有本地登录态：把环境变量里的 Cookie 注入浏览器上下文。

        本机走扫码登录，profile 里已有登录态，不需要注入；
        云端每次跑都从 secrets 取 ZHIHU_COOKIE 注入（知乎 Cookie 有效期 ≤4h，
        所以云端需要每天重跑时重新注入一份新鲜的）。
        """
        raw = (os.environ.get("ZHIHU_COOKIE") or "").strip()
        if not raw:
            return
        cookies = []
        for part in raw.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, _, value = part.partition("=")
            name = name.strip()
            if not name:
                continue
            cookies.append({
                "name": name,
                "value": value.strip(),
                "domain": ".zhihu.com",
                "path": "/",
            })
        if cookies:
            try:
                ctx.add_cookies(cookies)
                print(f"[zhihu] 已注入 {len(cookies)} 个 Cookie（云端登录态）")
            except Exception as e:
                print(f"[zhihu] Cookie 注入失败：{type(e).__name__}: {e}")

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

    def _dismiss(self, page) -> None:
        """关掉可能挡住编辑器的弹窗（登录提示 / 新手引导 / 公告）。"""
        for sel in ('.Modal', '.sign-wrap', '[class*=modal]', '[class*=Modal]',
                    '.Popover', '[class*=guide]', '[class*=Guide]'):
            try:
                els = page.locator(sel)
                for i in range(min(els.count(), 6)):
                    el = els.nth(i)
                    if not el.is_visible():
                        continue
                    # 优先点关闭按钮
                    for close_sel in (f"{sel} button[aria-label='关闭']",
                                      f"{sel} .Icon-close", f"{sel} [class*=close]"):
                        try:
                            c = el.locator(close_sel).first
                            if c.count() > 0 and c.is_visible():
                                c.click(timeout=2500)
                                page.wait_for_timeout(400)
                                break
                        except Exception:
                            continue
            except Exception:
                continue
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass

    def publish_browser(self, article: dict, title: str = "", body: str = "",
                        brief: str = "", tags: str = "") -> Result:
        """知乎发布（浏览器通道）。"""
        title = title or (article.get("titles") or {}).get("zhihu") or article.get("title", "")
        body = body or article.get("markdown", "")
        tags = tags or (article.get("platform_tags") or {}).get("zhihu") or article.get("tags", "")

        # 采集发布相关请求，用来判定真实结果
        events: list[dict[str, Any]] = []

        try:
            ctx = self._launch(headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            def on_resp(r):
                if "zhihu.com" in r.url and r.request.method == "POST":
                    try:
                        txt = r.text()[:300]
                    except Exception:
                        txt = ""
                    events.append({"url": r.url, "status": r.status, "body": txt})

            page.on("response", on_resp)

            page.goto("https://zhuanlan.zhihu.com/write", timeout=60000)
            page.wait_for_timeout(6000)
            self._dismiss(page)

            if "signin" in page.url or "login" in page.url:
                return Result(self.name, "failed",
                              detail="未登录：请先跑 python -m src.local --login zhihu")

            # 标题
            ti = page.locator("textarea[placeholder*='请输入标题']").first
            ti.fill(title)
            page.wait_for_timeout(500)

            # 正文：Draft.js 富文本编辑器，**不吃 Markdown**
            # （实测：粘贴 text/html 会被降级成纯文本；逐字输入 **粗体** / ## 标题
            #   / | 表格 | 全部原样保留，不会渲染）。
            # 所以先把 Markdown 改写成「纯文本也能读」的形态再填：
            #   标题 → ▎xxx    表格 → ・字段：值    代码块 → 4 空格缩进
            # 见 src/zhihu_text.py
            from .zhihu_text import md_to_zhihu_text
            plain = md_to_zhihu_text(body)

            ed = page.locator(".public-DraftEditor-content, [data-contents=true]").first
            ed.click(timeout=15000)
            page.wait_for_timeout(400)
            # 先清空
            page.keyboard.press("Control+A")
            page.wait_for_timeout(200)
            page.keyboard.press("Delete")
            page.wait_for_timeout(300)
            # 逐行输入：每行之间按 Enter（一次 insert_text 塞全部会被当成一段）
            lines = plain.split("\n")
            for idx, line in enumerate(lines):
                if line:
                    page.keyboard.insert_text(line)
                if idx < len(lines) - 1:
                    page.keyboard.press("Enter")
            page.wait_for_timeout(2500)

            # 校验正文写进去了
            got = ed.inner_text() or ""
            if len(got) < 50:
                return Result(self.name, "failed",
                              detail=f"正文写入异常，编辑器内仅 {len(got)} 字符（正文 {len(plain)} 字符）")

            # 话题标签（知乎支持，可选）
            tag_list = [t.strip() for t in str(tags or "").split(",") if t.strip()][:5]
            if tag_list:
                try:
                    tag_btn = page.locator("text=添加话题").first
                    if tag_btn.count() > 0:
                        tag_btn.click(timeout=5000)
                        page.wait_for_timeout(800)
                        ti2 = page.locator("input[placeholder*='搜索话题'], input[placeholder*='话题']").first
                        if ti2.count() > 0 and ti2.is_visible():
                            for t in tag_list:
                                ti2.fill(t)
                                page.wait_for_timeout(900)
                                page.keyboard.press("Enter")
                                page.wait_for_timeout(700)
                except Exception:
                    pass

            # 发布
            pub_btn = None
            for b in page.locator("button:has-text('发布')").all():
                try:
                    if b.is_visible() and b.is_enabled():
                        pub_btn = b
                        break
                except Exception:
                    continue
            if pub_btn is None:
                return Result(self.name, "failed", detail="找不到可见的「发布」按钮")
            pub_btn.click(timeout=15000)
            page.wait_for_timeout(4000)

            # 发布后的确认弹窗
            for sel in ("button:has-text('确认发布')", "button:has-text('发布文章')",
                        "button:has-text('确定发布')"):
                try:
                    b = page.locator(sel).first
                    if b.count() > 0 and b.is_visible():
                        b.click(timeout=8000)
                        page.wait_for_timeout(3000)
                        break
                except Exception:
                    continue

            page.wait_for_timeout(6000)

            # 判定：URL 变成文章详情页 = 成功
            url_now = page.url
            ok = bool(re.search(r"zhuanlan\.zhihu\.com/p/\d+", url_now))
            link = url_now if ok else ""

            detail = f"最终 URL={url_now[:110]}"
            if not ok:
                body_txt = page.inner_text("body")[:600]
                if any(k in body_txt for k in ["发布成功", "已发布", "发布完成"]):
                    ok = True
                    detail = "页面出现发布成功提示"
                else:
                    detail = f"未判定成功，url={url_now[:100]}"

            # 抓接口响应做交叉验证
            for e in events:
                if "publish" in e["url"].lower() or "articles" in e["url"].lower():
                    m = re.search(r'"id"\s*:\s*(\d{6,})', e["body"])
                    if m and not link:
                        link = f"https://zhuanlan.zhihu.com/p/{m.group(1)}"
                    detail += f" | {e['url'].split('/api/')[-1][:40]} http={e['status']}"

            return Result(self.name, "published" if ok else "failed",
                          url=link, detail=detail)
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")
        finally:
            self.close()

    def publish(self, article: dict) -> Result:
        """兼容接口式调用。"""
        return self.publish_browser(article)
