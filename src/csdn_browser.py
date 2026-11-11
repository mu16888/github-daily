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
import os
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
        self._inject_cookie(self._ctx)
        return self._ctx

    def _inject_cookie(self, ctx) -> None:
        """云端没有本机 profile 登录态：把 CSDN_COOKIE 注入浏览器上下文。

        本机 profile 里已有登录态时环境变量为空，注入逻辑自动跳过；
        GitHub Actions 每次都是干净 runner，靠 secrets.CSDN_COOKIE 注入。
        实测 cookie 有效期约半年（UserToken/UserName 到 2027-05），不是几小时。
        """
        raw = (os.environ.get("CSDN_COOKIE") or "").strip()
        if not raw:
            return
        cookies = []
        for part in raw.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, _, value = part.partition("=")
            if not name.strip():
                continue
            cookies.append({"name": name.strip(), "value": value.strip(),
                            "domain": ".csdn.net", "path": "/"})
        if cookies:
            try:
                ctx.add_cookies(cookies)
                print(f"[csdn] 已注入 {len(cookies)} 个 Cookie（云端登录态）")
            except Exception as e:
                print(f"[csdn] Cookie 注入失败：{type(e).__name__}: {e}")

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

    def _dismiss_modals(self, page, keep_publish_panel: bool = False) -> None:
        """关掉挡住编辑器的各种弹窗。

        ⚠️ keep_publish_panel=True 用在「发布文章」面板已打开之后：
        此时 `.el-dialog__headerbtn` 就是面板自己的右上角 ×，点它等于关掉面板；
        按「模版库」文字删 div 也可能删到面板的祖先容器（innerText 会包含后代文本）。
        2026-11-11 实测：不设这个保护时封面组件会从 DOM 里消失，导致上传永远失败。

        CSDN 编辑器会弹两类：
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
        if keep_publish_panel:
            sels = [s for s in sels if s not in
                    (".ant-modal-close", ".el-dialog__headerbtn")]
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
                // 「模版库 / 我的模版」浮层（新手引导）：class 不固定，按内容特征识别。
                // 2026-11-11 实测它盖住发布面板，是「只存成草稿」的真正原因。
                document.querySelectorAll('div').forEach(el => {
                  const t = (el.innerText || '');
                  if ((t.includes('模版库') || t.includes('模板库') || t.includes('我的模版'))
                      && (t.includes('添加到正文') || t.includes('我的模版'))
                      && t.length < 800) {
                    // innerText 含后代文本，祖先 div 也会匹配；绝不能删含
                    // 发布面板 / 编辑器 的容器，否则封面组件一起消失。
                    if (el.querySelector('.publish-article-modal__body') ||
                        el.querySelector('.editor__inner')) return;
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) { el.remove(); n++; }
                  }
                });
                return n;
            }""")
            if not left:
                break
            page.wait_for_timeout(300)

    def _upload_cover(self, page, cover_path: str) -> tuple[bool, str]:
        """发布面板里「添加封面」带红色星号 = 必填项。

        2026-11-11 抓包实测，两个此前一直踩的坑：
          1) 封面真正的 input 是 `.el-upload__input`（accept=.png,.jpg,.jpeg,.gif），
             包在 `.el-upload > button.upload-img-box`「从本地上传」里。
             旧代码按 accept*='image' 找 → 命中的是 `.cfw-file-input`（正文插图），
             再兜底就打到 `.md` 导入框，所以封面从来没被喂给正确的控件。
          2) 选完文件 CSDN 会弹「图片裁剪」对话框，必须点右下角「确认上传」
             才会真正上传并回填封面。旧代码 set_input_files 后只等 8 秒就判定，
             封面区自然一直显示「暂无内容图片」→ 点发布只存草稿。
        """
        p = Path(cover_path)
        if not cover_path or not p.exists():
            return False, f"封面文件不存在: {cover_path or '(空)'}"

        # 抓上传接口响应：封面没回填时能看到是 200、4xx 还是根本没发请求
        uploads: list[str] = []

        def _cap(r):
            try:
                if r.request.method == "POST" and any(
                        k in r.url.lower() for k in ("upload", "img", "image", "oss", "picture")):
                    try:
                        body = r.text()[:180]
                    except Exception:
                        body = ""
                    uploads.append(f"{r.status} {r.url[:80]} {body[:140]}")
            except Exception:
                pass

        page.on("response", _cap)

        def dump_state() -> str:
            """失败时把页面真实 DOM 与上传响应带出来，避免下一次还要靠猜。"""
            try:
                d = page.evaluate("""() => ({
                    inputs: Array.from(document.querySelectorAll('input[type=file]'))
                        .map(e => (e.className||'') + '|' + (e.accept||'')),
                    panel: ((document.querySelector('.publish-article-modal__body')
                             || document.body).innerText || '').slice(0, 220)
                })""")
                return (f" | inputs={d['inputs']} panel={d['panel']!r}"
                        f" | uploads={uploads[-4:]}")
            except Exception:
                return f" | uploads={uploads[-4:]}"

        # ⚠️ 一律用 page 全页定位：不能绑死在 .publish-article-modal__body 上。
        #    新建文章时该容器可能为空（打开已有草稿时才有内容），scope 里什么都找不到。
        # 若发布面板被浮层/快捷键误关，重新点「发布」打开。
        try:
            m = page.locator(".publish-article-modal__body")
            if m.count() == 0 or not m.first.is_visible():
                for b in page.locator("button:has-text('发布')").all():
                    try:
                        if b.is_visible() and b.is_enabled():
                            b.click(timeout=10000)
                            break
                    except Exception:
                        continue
                page.wait_for_timeout(2500)
                self._dismiss_modals(page)
        except Exception:
            pass

        # 封面区异步渲染：新建文章比打开已有草稿慢，最多等 15 秒。
        try:
            page.wait_for_function("""() =>
                !!document.querySelector('input.el-upload__input[type=file]') ||
                !!document.querySelector('button.upload-img-box')""", timeout=15000)
        except Exception:
            pass

        def confirm_crop() -> bool:
            """点「图片编辑」弹窗的「确认上传」；没弹就返回 False。

            ⚠️ 选择器不能写成 `"button:has-text('x'), text=x"` —— Playwright 把逗号
            当成组合 CSS 解析，`text=` 里的 `=` 会直接抛 Unexpected token。
            必须逐个 selector 单独试（2026-11-11 实测踩过）。
            """
            for sel in ("button:has-text('确认上传')", "text=确认上传"):
                try:
                    btn = page.locator(sel).first
                    btn.wait_for(state="visible", timeout=8000)
                    for _ in range(12):
                        if btn.is_enabled():
                            btn.click(timeout=12000, force=True)
                            return True
                        page.wait_for_timeout(500)
                except Exception:
                    continue
            return False

        try:
            # 主路径：直接给封面 input 喂文件 —— 不点任何按钮，彻底避开浮层遮挡。
            cropped = False
            fi = page.locator("input.el-upload__input[type=file]")
            if fi.count() > 0:
                try:
                    fi.first.set_input_files(str(p), timeout=25000)
                    cropped = confirm_crop()
                except Exception:
                    pass

            # 退路：按真实交互点「从本地上传」用 filechooser（抓包实测能拉起裁剪框）
            if not cropped:
                last_err = ""
                for sel in ("button.upload-img-box", ".el-upload--text button",
                            "text=从本地上传"):
                    try:
                        btn = page.locator(sel).first
                        btn.wait_for(state="attached", timeout=6000)
                        with page.expect_file_chooser(timeout=12000) as fc:
                            btn.click(timeout=8000, force=True)
                        fc.value.set_files(str(p))
                        if confirm_crop():
                            cropped = True
                            break
                    except Exception as e2:
                        last_err = f"{type(e2).__name__}: {str(e2)[:80]}"
                        continue
                if not cropped:
                    return False, ("封面选文件失败：" + last_err + dump_state())

            page.wait_for_timeout(12000)
            txt = ""
            try:
                m = page.locator(".publish-article-modal__body")
                txt = (m.first.inner_text() if m.count()
                       else page.locator("body").inner_text()) or ""
            except Exception:
                pass
            # 「暂无内容图片」是封面为空时的专属提示，它消失即代表封面已回填。
            ok = "暂无内容图片" not in txt
            return ok, ("封面已上传" if ok
                        else "上传后封面区仍显示「暂无内容图片」" + dump_state())
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:100]}" + dump_state()

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

        ⚠️ 2026-11-11 实测：headless 下面板也能完整渲染，早前「必须可视窗口」的结论已过时。
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

        # 标签：这里**故意不碰**。
        # 编辑器顶部（publish() 第 393 行起）已经填过标签，面板里会自带；
        # 标签不是必填，而「添加封面」才是红星必填。
        # 2026-11-11 实测：点开面板内的「添加文章标签」会拉出一个推荐标签浮层，
        # 它挂在面板容器内、遮住封面区和底部「发布文章」按钮；按 Escape 又会
        # 把整个面板关掉。两条路都会让封面上传失败 → 只存草稿。
        # 结论：面板内只填摘要，标签交给编辑器顶部，不打开任何下拉。

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
                        brief: str = "", tags: str = "", cover: str = "") -> Result:
        """供流水线调用：浏览器通道发布。

        与接口版的 publish() 分开，因为浏览器通道需要自己管标题/正文/摘要/标签/封面。
        云端 Linux runner 无显示器，默认 headless=True（2026-11-11 实测发布面板在无头下
        也能完整渲染，此前「必须可视窗口」的结论已过时）；本机要看交互时可设
        CSDN_HEADLESS=false。
        """
        headless = os.environ.get("CSDN_HEADLESS", "true").lower() not in ("false", "0", "no")
        return self.publish(article, headless=headless, title=title, body=body,
                            brief=brief, tags=tags, cover=cover)

    def publish(self, article: dict, headless: bool = True,
                title: str = "", body: str = "", brief: str = "",
                tags: str = "", cover: str = "") -> Result:
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

            # ⚠️ 点「发布」后 CSDN 会弹「模版库 / 我的模版」新手引导浮层，
            #    它盖住真正的发布面板 → 后面点不到面板里的「发布文章」→ 文章只存成草稿。
            #    （2026-11-11 实测：面板里那个「发布文章」按钮 visible=False，
            #      截图确认当时浮在页面上的正是模版库。）
            #    必须先清掉这类浮层，再进面板。
            self._dismiss_modals(page, keep_publish_panel=True)

            # 「发布文章」面板：文章标签 / 摘要 / 封面 / 可见范围 / 文章类型。
            # 2026-11-11 实测：headless 下面板也能完整渲染，早前「必须可视窗口」结论已过时。
            panel = self._fill_publish_panel(page, tags, brief)
            if panel.get("error"):
                return Result(self.name, "failed", detail=panel["error"])

            # 封面是必填（面板里「添加封面」带红星）：不传封面点「发布文章」只存草稿。
            # 2026-11-11 手动发一篇验证：传封面 → 发布成功（审核中）；不传 → 只存草稿。
            if not cover:
                return Result(self.name, "failed",
                              detail="未提供封面：CSDN 发布面板「添加封面」是红星必填项，"
                                     "不传封面点「发布文章」只会存成草稿（2026-11-11 实测）")
            ok_cover, cover_detail = self._upload_cover(page, cover)
            if not ok_cover:
                return Result(self.name, "failed", detail=f"封面上传失败：{cover_detail}")
            page.wait_for_timeout(1500)

            # 面板底部红色「发布文章」按钮。
            # ⚠️ 页面上不止一个「发布文章」按钮（编辑器工具栏也有一个），
            #    旧代码取第一个 → 可能点错、只存草稿。面板底部那个在 DOM 里排最后，倒序优先。
            cands = []
            for b in page.locator("button:has-text('发布文章')").all():
                try:
                    if b.is_visible() and b.is_enabled():
                        cands.append(b)
                except Exception:
                    continue
            submitted = False
            for b in reversed(cands):
                try:
                    # force：面板里可能有浮层盖住按钮，普通 click 会一直超时
                    b.click(timeout=15000, force=True)
                    submitted = True
                    break
                except Exception:
                    continue
            if not submitted:
                return Result(self.name, "failed", detail="发布面板里找不到「发布文章」按钮")
            page.wait_for_timeout(6000)

            # CSDN 免费号每天发文额度有限（实测提示「今日发文额度已用完」）。
            # 撞到额度要如实报 skipped，不能当成发布失败，更不能假报成功。
            # ⚠️ 这里必须用本方法的局部变量：早前误用了 _fill_publish_panel 里的
            #    out → NameError: name 'out' is not defined，浏览器通道整条挂掉。
            quota_hit = False
            quota_msg = ""
            for sel in ('[class*=tip]', '.el-message', '[class*=toast]'):
                try:
                    els = page.locator(sel)
                    for i in range(els.count()):
                        el = els.nth(i)
                        if not el.is_visible():
                            continue
                        txt = el.inner_text() or ""
                        # ⚠️ 实测提示是「今日发文额度还有 2 篇，可去这里提升额度」——
                        #    这是「有额度」，不是撞额度。旧判断只要含「发文额度」就当撞满，
                        #    把有额度也判成 skipped。这里只认耗尽类措辞，并显式排除「还有」。
                        if "还有" in txt or "可提升" in txt:
                            continue
                        if ("额度已用完" in txt or "额度用尽" in txt
                                or "已达限制" in txt or "达到限制" in txt
                                or "数量已达" in txt):
                            quota_hit = True
                            quota_msg = txt.strip()[:80]
                            break
                except Exception:
                    continue
                if quota_hit:
                    break
            if quota_hit:
                return Result(self.name, "skipped",
                              detail=f"今日发文额度已用完（CSDN 免费号每天 2 篇）："
                                     f"{quota_msg}")

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
                        # 失败留证据（截图），别再靠猜
                        try:
                            shot = (Path(__file__).resolve().parent.parent
                                    / "state" / "csdn_last_fail.png")
                            shot.parent.mkdir(parents=True, exist_ok=True)
                            page.screenshot(path=str(shot))
                            detail = (f"未判定成功，当前 url={url_now[:100]}"
                                      f"（截图 state/{shot.name}）")
                        except Exception:
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
