"""CSDN 浏览器发布器：用 CSDN 自己的编辑器发文章。

为什么不走 saveArticle 接口：
实测（2026-11-10）用 Cookie + x-ca 签名调 `blog-console-api/v3/mdeditor/saveArticle`
永远返回 `code=400 博主不存在`，即使登录态完整（UserToken/UserName 都在）。
根因不是凭据也不是签名 —— 是 CSDN 的账号冷启动门槛：
    GET /blog/phoenix/console/v1/article/is-zero-article-user → data=true
零发文账号（从未发过文章）不允许通过该接口建新文章。
而 CSDN 网页编辑器走的是另一条链路（/blog/phoenix/console/v1/... 系列），
不受这个门槛限制。

所以：账号的第一篇文章走浏览器发，之后接口就能用了。
这个发布器就是用来做「第一篇」以及任何网页链路更可靠的场景。

流程：
    1. 打开 https://editor.csdn.net/md/
    2. 填标题 → 填正文（Markdown 原文）→ 填摘要
    3. 点「发布」→ 处理可能的确认弹窗
    4. 从页面反馈 / 网络响应里判断是否真的发布成功（不靠猜）

安全边界：只对本机锋哥自己的账号操作自己写的文章，不抓取、不批量互动。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .publish import Result


class CsdnBrowserPublisher:
    """CSDN 网页编辑器发布器。"""

    name = "csdn"

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
            viewport={"width": 1600, "height": 1000},
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

    def _dismiss_modals(self, page) -> None:
        """关掉挡住编辑器的各种弹窗。

        实测 CSDN 编辑器会弹两类：
        - `.modal_outer`（公告 / 隐私协议）
        - `.beginnerGuide-box`（新手引导，class 带 show-beginnerGuide-box）
        不关掉的话后续所有点击都被它拦下（pointer events intercepted）。
        """
        sels = [
            ".beginnerGuide-box [class*='close']", ".beginnerGuide-box .close",
            ".beginnerGuide-box [class*='icon']", ".beginnerGuide-box button",
            ".beginnerGuide-box .middle",
            ".modal_outer .modal-close", ".modal_outer .icon-close",
            ".modal_outer [class*='close']", ".modal_outer button",
            ".ant-modal-close", ".el-dialog__headerbtn",
            "[class*='guide'] [class*='close']", "[class*='popup'] [class*='close']",
        ]
        for _ in range(6):
            found = False
            for sel in sels:
                try:
                    els = page.locator(sel)
                    n = els.count()
                    for i in range(n):
                        el = els.nth(i)
                        if not el.is_visible():
                            continue
                        el.click(timeout=2500)
                        page.wait_for_timeout(400)
                        found = True
                        break
                    if found:
                        break
                except Exception:
                    continue
            if not found:
                break
            page.wait_for_timeout(300)

        # 兜底：还有弹窗就按 ESC / 直接把容器从 DOM 里摘掉
        for _ in range(3):
            left = page.evaluate("""() => {
                const sels = ['.modal_outer', '.beginnerGuide-box',
                              '[class*=modal_outer]', '[class*=beginnerGuide]'];
                let n = 0;
                for (const s of sels) {
                  document.querySelectorAll(s).forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) { el.remove(); n++; }
                  });
                }
                return n;
            }""")
            if not left:
                break
            page.wait_for_timeout(300)

    def _fill_publish_panel(self, page, tags: str, brief: str) -> dict:
        """填「发布文章」面板：标签、摘要、可见范围。

        面板结构（2026-11-10 实测）：
            文章标签  [ + 添加文章标签 ]
            添加封面  [ + 从本地上传 ]
            文章摘要  [textarea]
            分类专栏  [ + 新建分类专栏 ]
            文章类型  原创 / 转载 / 翻译
            可见范围  全部可见 / 仅我可见 / 粉丝可见 / VIP可见
            文章模板  默认模板 / 简洁模板 / 廓桥模板
        底部：[取消] [保存为草稿] [定时发布] [发布文章]

        ⚠️ 关键：这个面板在 headless 下不渲染（只有标题和两个空按钮），
        必须用可视窗口（headless=False）。
        """
        out: dict = {"error": "", "tags_set": False, "brief_set": False}

        # 面板可能需要一点时间才出现。
        # 真实容器（2026-11-10 实测）：
        #   .modal__inner-1.modal__publish-article
        #   .modal__content.publish-article-modal__body
        #   .form-entry.form-tag-box.required  ← 文章标签
        #   .tag__btn-tag                     ← 标签下拉按钮
        panel = None
        for _ in range(12):
            for sel in ('.publish-article-modal__body',
                        '.modal__publish-article',
                        '.modal__inner-2',
                        '.modal'):
                els = page.locator(sel)
                for i in range(els.count()):
                    el = els.nth(i)
                    try:
                        if el.is_visible() and ("文章标签" in (el.inner_text() or "")):
                            panel = el
                            break
                    except Exception:
                        continue
                if panel is not None:
                    break
            if panel is not None:
                break
            page.wait_for_timeout(800)

        if panel is None:
            out["error"] = ("发布面板未渲染（文章标签区域不可见）。"
                            "headless 下 CSDN 不渲染该面板，需要用可视窗口运行。")
            return out

        # 标签：点「+ 添加文章标签」，弹出标签搜索框，输名字回车添加。
        # 实测（2026-11-10）：
        #   触发按钮  .tag__btn-tag（文案「添加文章标签」）
        #   搜索输入框 placeholder = 「请输入文字搜索，Enter键入可添加自定义标签」
        #   面板自带推荐标签（开源 / 开发工具 / Git / 人工智能 …），输入即过滤
        try:
            tag_list = [t.strip() for t in str(tags or "").split(",") if t.strip()][:5]
            if tag_list:
                add = panel.locator(".tag__btn-tag").first
                if add.count() == 0:
                    add = page.locator("text=添加文章标签").first
                add.click(timeout=8000)
                page.wait_for_timeout(1200)

                ti = page.locator(
                    "input[placeholder*='搜索，Enter键入可添加自定义标签'], "
                    "input[placeholder*='Enter键入']").first
                if ti.count() == 0:
                    ti = page.locator(
                        "input[placeholder*='搜索'], input[placeholder*='请输入文字']").first
                if ti.count() > 0 and ti.is_visible():
                    for t in tag_list:
                        ti.click()
                        ti.fill(t)
                        page.wait_for_timeout(700)   # 等推荐标签过滤出来
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(700)
                    out["tags_set"] = True
                    # 关掉标签下拉，避免遮挡后续按钮
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(400)
        except Exception:
            pass

        # 摘要：文章摘要 textarea（面板内的第一个可见 textarea）
        try:
            tas = panel.locator("textarea")
            for i in range(tas.count()):
                ta = tas.nth(i)
                if ta.is_visible():
                    ta.fill(brief[:256])
                    page.wait_for_timeout(400)
                    out["brief_set"] = True
                    break
        except Exception:
            pass

        return out

    def publish_browser(self, article: dict, title: str = "", body: str = "",
                        brief: str = "", tags: str = "") -> Result:
        """供流水线调用：浏览器通道发布。

        与接口版的 publish() 分开，因为浏览器通道需要自己管标题/正文/摘要/标签，
        而且必须用可视窗口（headless 下 CSDN 不渲染发布面板）。
        """
        return self.publish(article, headless=False, title=title, body=body,
                            brief=brief, tags=tags)

    def publish(self, article: dict, headless: bool = True,
                title: str = "", body: str = "", brief: str = "",
                tags: str = "") -> Result:
        """在 CSDN 编辑器里写一篇并发布。"""
        title = title or (article.get("titles") or {}).get("csdn") or article.get("title", "")
        body = body or article.get("markdown", "")
        brief = brief or (article.get("briefs") or {}).get("csdn") or article.get("brief", "")
        tags = tags or (article.get("platform_tags") or {}).get("csdn") or article.get("tags", "")

        # 采集发布相关请求，用来判定真实结果
        events: list[dict[str, Any]] = []

        try:
            ctx = self._launch(headless=headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            def on_resp(r):
                if "bizapi.csdn.net" in r.url and r.request.method == "POST":
                    try:
                        txt = r.text()[:400]
                    except Exception:
                        txt = ""
                    events.append({"url": r.url, "status": r.status, "body": txt})

            page.on("response", on_resp)

            page.goto("https://editor.csdn.net/md/", timeout=60000)
            page.wait_for_timeout(5000)
            self._dismiss_modals(page)

            if "login" in page.url or "passport" in page.url:
                return Result(self.name, "failed",
                              detail="未登录：请先跑 python -m src.local --login csdn")

            # 标题：CSDN 是「可见 display + 隐藏 input」双元素。
            # 直接点 display 会把「【无标题】」默认值和新标题拼在一起，
            # 所以用原生 setter 写值 + 派发 input 事件（React 能收到）。
            # 注意 setter 必须用 .call(input, value)，直接调用会 Illegal invocation。
            ok_title = page.evaluate("""(t) => {
                const inp = document.querySelector("input[placeholder*='标题']");
                if (!inp) return false;
                const proto = window.HTMLInputElement.prototype;
                const desc = Object.getOwnPropertyDescriptor(proto, 'value');
                if (!desc || !desc.set) return false;
                desc.set.call(inp, t);
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
            }""", title)
            page.wait_for_timeout(600)
            if not ok_title:
                # 兜底：点可见 display 后全选覆盖
                try:
                    disp = page.locator(".article-bar__title-display").first
                    disp.click()
                    page.wait_for_timeout(200)
                    page.keyboard.press("Control+A")
                    page.keyboard.type(title, delay=8)
                except Exception:
                    pass
            page.wait_for_timeout(400)

            # 正文：编辑器是 <pre contenteditable="true">（CSDN 自研，非 CodeMirror）。
            # 必须先清空（编辑器默认带一份「欢迎使用Markdown编辑器」样板），
            # 再 insert_text 写入。
            self._dismiss_modals(page)
            ed = page.locator(".editor__inner").first
            ed.click(timeout=15000)
            page.wait_for_timeout(300)
            page.keyboard.press("Control+A")
            page.wait_for_timeout(200)
            page.keyboard.press("Delete")
            page.wait_for_timeout(500)
            # 用 type 而不是 insert_text：type 会对 \n 发回车，段落结构才对。
            # insert_text 模拟粘贴，会把换行吃掉，Markdown 会变成一坨。
            page.keyboard.type(body, delay=1)
            page.wait_for_timeout(2000)

            # 校验：正文确实写进去了
            got = ed.inner_text() or ""
            if len(got) < 50:
                return Result(self.name, "failed",
                              detail=f"正文写入异常，编辑器内仅 {len(got)} 字符（正文 {len(body)} 字符）")

            # 标签：CSDN 编辑器里有「标签」输入框，用逗号分隔填
            try:
                tag_input = page.locator(
                    "input[placeholder*='标签'], input[placeholder*='多个标签']").first
                if tag_input.count() > 0:
                    for t in [x.strip() for x in str(tags).split(",") if x.strip()][:5]:
                        tag_input.fill(t)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(200)
            except Exception:
                pass      # 标签填不了不影响发布

            # 点发布：页面里有多个「发布」按钮（含隐藏的 simulation-button），
            # 必须挑可见的那个，否则 click 会一直等不到可点状态。
            pub_btn = None
            for btn in page.locator("button:has-text('发布')").all():
                try:
                    if btn.is_visible() and btn.is_enabled():
                        pub_btn = btn
                        break
                except Exception:
                    continue
            if pub_btn is None:
                return Result(self.name, "failed", detail="找不到可见的「发布」按钮，页面结构可能已变")
            pub_btn.click(timeout=15000)
            page.wait_for_timeout(2500)

            # 「发布文章」面板：文章标签 / 摘要 / 封面 / 可见范围 / 文章类型。
            # ⚠️ 这个面板在 headless 下不渲染（内容为空），必须用可视窗口。
            panel = self._fill_publish_panel(page, tags, brief)
            if panel.get("error"):
                return Result(self.name, "failed", detail=panel["error"])

            # 面板底部红色「发布文章」按钮
            submitted = False
            for b in page.locator("button:has-text('发布文章')").all():
                try:
                    if b.is_visible() and b.is_enabled():
                        b.click(timeout=15000)
                        submitted = True
                        break
                except Exception:
                    continue
            if not submitted:
                return Result(self.name, "failed", detail="发布面板里找不到「发布文章」按钮")
            page.wait_for_timeout(6000)

            # CSDN 免费号每天发文额度有限（实测提示「今日发文额度已用完」）。
            # 撞到额度要如实报 skipped，不能当成发布失败，更不能假报成功。
            quota_hit = False
            for sel in ('[class*=tip]', '.el-message', '[class*=toast]'):
                try:
                    els = page.locator(sel)
                    for i in range(els.count()):
                        el = els.nth(i)
                        if not el.is_visible():
                            continue
                        txt = el.inner_text() or ""
                        if "发文额度" in txt or "额度已用完" in txt:
                            quota_hit = True
                            out["quota_msg"] = txt.strip()[:80]
                            break
                except Exception:
                    continue
                if quota_hit:
                    break
            if quota_hit:
                return Result(self.name, "skipped",
                              detail=f"今日发文额度已用完（CSDN 免费号每天 1 篇）："
                                     f"{out.get('quota_msg', '')}")

            # 可能出现二次确认弹窗
            for sel in ("button:has-text('确认发布')", ".el-button--primary:has-text('发布')",
                        "button.Button--primary:has-text('发布')"):
                try:
                    b = page.locator(sel)
                    if b.count() > 0:
                        b.first.click()
                        page.wait_for_timeout(2500)
                        break
                except Exception:
                    continue

            page.wait_for_timeout(4000)

            # 判定结果：优先看发布接口的响应
            ok = False
            detail = ""
            for e in events:
                if "publish" in e["url"].lower() and "get" not in e["url"].lower():
                    body_txt = e["body"]
                    try:
                        d = json.loads(body_txt)
                        code = d.get("code")
                        if code == 200:
                            ok = True
                            data = d.get("data") or {}
                            url = ""
                            if isinstance(data, dict):
                                url = str(data.get("url") or data.get("articleUrl") or "")
                            detail = f"发布接口返回 code=200 {url[:80]}"
                            break
                        detail = f"发布接口 code={code} {body_txt[:120]}"
                    except Exception:
                        if e["status"] == 200:
                            ok = True
                            detail = "发布接口返回 http=200"
                            break
                        detail = f"发布接口 http={e['status']} {body_txt[:100]}"

            if not ok and not detail:
                # 退而求其次：看页面是否跳到了文章页 / 出现成功提示
                url_now = page.url
                if "blog.csdn.net" in url_now and "/phoenix" not in url_now:
                    ok = True
                    detail = f"页面已跳转到文章页 {url_now[:100]}"
                else:
                    body_txt = page.inner_text("body")[:600]
                    if any(k in body_txt for k in ["发布成功", "发表成功", "审核中"]):
                        ok = True
                        detail = "页面出现发布成功提示"
                    else:
                        detail = f"未判定成功，当前 url={url_now[:100]}"

            link = ""
            if ok:
                for e in events:
                    if "publish" in e["url"].lower():
                        m = re.search(r'"url"\s*:\s*"([^"]+)"', e["body"])
                        if m:
                            link = m.group(1)
                            break
                if not link:
                    link = "https://blog.csdn.net/phoenix_9"

            return Result(self.name, "published" if ok else "failed",
                          url=link, detail=detail)
        except Exception as e:
            return Result(self.name, "failed",
                          detail=f"{type(e).__name__}: {e}")
        finally:
            self.close()
