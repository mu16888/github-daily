"""头条号发布器（浏览器通道）。

为什么必须走浏览器：
头条号**没有官方发文接口**（要字节开放平台单独审核，个人号拿不到），
只能驱动真实浏览器操作网页编辑器。

编辑器结构（2026-11-10 实测）：
    标题  textarea[placeholder='请输入文章标题（2～30个字）']  ← 注意限 30 个字
    正文  ProseMirror（.ProseMirror / [contenteditable=true]）
    按钮  预览 / 定时发布 / 预览并发布（byte-btn-primary）

ProseMirror 比知乎的 Draft.js 好办：可以直接用 innerHTML 写内容
（它会解析 HTML 并同步内部 state），也支持键盘输入兜底。
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from .publish import Result

TITLE_MAX_CHARS = 30          # 头条标题限制：2~30 个字


class ToutiaoBrowserPublisher:
    """头条号发布器。"""

    name = "toutiao"

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
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir()),
            channel=str(self.browser_cfg.get("channel", "msedge")),
            headless=headless,
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

    def _dismiss(self, page) -> None:
        """关掉挡路的弹窗（热点推荐引导 / 协议 / 公告）。"""
        for sel in ('.byte-modal', '.byte-dialog', '[class*=modal]',
                    '[class*=guide]', '[class*=Guide]', '.semi-modal'):
            try:
                els = page.locator(sel)
                for i in range(min(els.count(), 6)):
                    el = els.nth(i)
                    if not el.is_visible():
                        continue
                    for close_sel in (f"{sel} [class*=close]", f"{sel} [aria-label=关闭]",
                                      f"{sel} button"):
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
        """头条发布（浏览器通道）。"""
        title = title or (article.get("titles") or {}).get("toutiao") or article.get("title", "")
        body = body or article.get("markdown", "")
        tags = tags or (article.get("platform_tags") or {}).get("toutiao") or article.get("tags", "")

        if len(title) > TITLE_MAX_CHARS:
            title = title[:TITLE_MAX_CHARS]
        # 正文用知乎那套纯文本适配（表格/代码块转成可读形态），头条同样不吃 Markdown
        from .zhihu_text import md_to_zhihu_text, md_to_zhihu_html
        plain = md_to_zhihu_text(body)

        events: list[dict[str, Any]] = []
        try:
            ctx = self._launch(headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            def on_resp(r):
                if "toutiao.com" in r.url and r.request.method == "POST":
                    try:
                        txt = r.text()[:300]
                    except Exception:
                        txt = ""
                    events.append({"url": r.url, "status": r.status, "body": txt})

            page.on("response", on_resp)

            page.goto("https://mp.toutiao.com/profile_v4/graphic/publish",
                      timeout=60000)
            page.wait_for_timeout(8000)
            self._dismiss(page)

            if "login" in page.url or "auth" in page.url:
                return Result(self.name, "failed",
                              detail="未登录：请先跑 python -m src.local --login toutiao")

            # 标题
            ti = page.locator("textarea[placeholder*='请输入文章标题']").first
            ti.fill(title)
            page.wait_for_timeout(600)

            # 正文：ProseMirror。
            # ⚠️ 关键：**不能用 innerHTML 赋值** —— 那样虽然编辑器里能看到内容，
            #    但头条的「共 N 字」计数仍是 0（状态没同步），
            #    点「预览并发布」会静默无反应。必须用键盘输入，
            #    让 ProseMirror 走真实的 input 事件链。
            ed = page.locator(".ProseMirror").first
            ed.click(timeout=15000)
            page.wait_for_timeout(400)
            page.keyboard.press("Control+A")
            page.wait_for_timeout(200)
            page.keyboard.press("Delete")
            page.wait_for_timeout(300)
            lines = plain.split("\n")
            for idx, line in enumerate(lines):
                if line:
                    page.keyboard.insert_text(line)
                if idx < len(lines) - 1:
                    page.keyboard.press("Enter")
            page.wait_for_timeout(3000)

            got = ed.inner_text() or ""
            if len(got) < 50:
                return Result(self.name, "failed",
                              detail=f"正文写入异常，编辑器内仅 {len(got)} 字符")

            # 校验头条自己的字数计数（这是它认不认内容的判据）
            counted = 0
            try:
                body_txt = page.inner_text("body")
                m = re.search(r"共\s*(\d+)\s*字", body_txt)
                if m:
                    counted = int(m.group(1))
            except Exception:
                pass
            if counted < 100:
                return Result(self.name, "failed",
                              detail=f"头条字数计数只有 {counted}（应为 0 表示状态没同步），"
                                     f"编辑器内 {len(got)} 字符 —— 内容没被识别")

            # 封面：头条「展示封面」是**必填**（带红星），不传就点发布没反应
            # （2026-11-10 实测：正文标题都对，但缺封面时点「预览并发布」静默无反应，
            #  文章只存成空草稿，页面提示「还需输入 N 个字 / 请输入正文」）。
            #
            # 正确流程（实测）：
            #   1. 点 .article-cover-add（封面区的 + 方框）→ 弹出上传面板
            #   2. 点「本地上传」按钮 → 页面才注入 input[type=file][accept=image/*]
            #      ⚠️ 面板打开前查 input[type=file] 数量是 0，别提前找
            #   3. set_input_files 塞图 → 等上传完成
            cover_ok = False
            cover_path = (article.get("cover_path") or "").strip()
            if not cover_path:
                repo = (article.get("repo") or "").strip()
                if repo:
                    cover_path = str(self.root / "state" / "covers" / "toutiao-cover.jpg")
            if cover_path:
                cp = Path(cover_path)
                if not cp.is_absolute():
                    cp = self.root / cp
                if cp.exists():
                    try:
                        add = page.locator(".article-cover-add").first
                        add.scroll_into_view_if_needed()
                        page.wait_for_timeout(500)
                        add.click(timeout=8000)
                        page.wait_for_timeout(2000)
                        # 面板里的「本地上传」是 span，父元素才是 button
                        local_btn = page.locator(
                            'button:has(span:text-is("本地上传"))').first
                        if local_btn.count() > 0:
                            local_btn.click(timeout=8000)
                            page.wait_for_timeout(1500)
                        # 面板打开后 file input 才会注入
                        fis = page.locator("input[type='file']")
                        cnt = fis.count()
                        if cnt == 0:
                            page.wait_for_timeout(1500)
                            cnt = fis.count()
                        if cnt > 0:
                            fis.nth(cnt - 1).set_input_files(str(cp))
                            page.wait_for_timeout(5000)
                            cover_ok = True
                    except Exception:
                        cover_ok = False
            if not cover_ok:
                return Result(self.name, "failed",
                              detail="封面未上传成功（头条封面是必填项），"
                                     "没有封面点「预览并发布」会静默失败")

            # 「预览并发布」
            pub_btn = None
            for b in page.locator("button:has-text('预览并发布')").all():
                try:
                    if b.is_visible() and b.is_enabled():
                        pub_btn = b
                        break
                except Exception:
                    continue
            if pub_btn is None:
                return Result(self.name, "failed", detail="找不到可见的「预览并发布」按钮")
            pub_btn.click(timeout=15000)
            page.wait_for_timeout(5000)

            # 发布确认弹窗
            for sel in ("button:has-text('确定发布')", "button:has-text('确认发布')",
                        "button:has-text('发布')"):
                try:
                    b = page.locator(sel).first
                    if b.count() > 0 and b.is_visible():
                        b.click(timeout=8000)
                        page.wait_for_timeout(3500)
                        break
                except Exception:
                    continue

            page.wait_for_timeout(6000)
            url_now = page.url
            ok = bool(re.search(r"(toutiao\.com|mp\.toutiao\.com).*(publish|article|graphic)",
                                url_now))
            detail = f"最终 URL={url_now[:110]}"
            body_txt = page.inner_text("body")[:600]
            if any(k in body_txt for k in ["发布成功", "已发布", "提交成功"]):
                ok = True
                detail = "页面出现发布成功提示"

            for e in events[-6:]:
                detail += f" | {e['url'].split('toutiao.com')[-1][:38]} http={e['status']}"

            return Result(self.name, "published" if ok else "failed",
                          url=url_now if ok else "", detail=detail)
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")
        finally:
            self.close()

    def publish(self, article: dict) -> Result:
        return self.publish_browser(article)
