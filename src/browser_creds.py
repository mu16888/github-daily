"""浏览器登录态自动导出。

要解决的问题：
云端时代拿掘金/CSDN 的 Cookie，只能让锋哥手工去 DevTools 复制 ——
又慢又容易漏字段，还容易贴错。搬到本机后这条路可以彻底自动化：
本机有浏览器，让浏览器自己带着登录态跑一次，再把 Cookie 导出来喂给接口。

流程（锋哥只做一次）：
    1. 程序用 Playwright 打开本机 Edge（独立 profile），停在掘金登录页
    2. 锋哥扫码登录，程序检测到登录成功
    3. 程序从浏览器上下文里读出 .juejin.cn / api.juejin.cn 的全部 Cookie，
       拼成标准 Cookie 请求头，写进 config/local_secrets.json
    4. 再从页面 URL 或接口响应里抓出 uuid（掘金接口必需的用户级常量）

关键点：
- 用的是**独立 profile**（state/browser-profile），不碰锋哥日常 Edge 的登录态
- 登录一次长期有效：Cookie 存进 profile，之后每天跑都直接复用
- 导出的 Cookie 只写本机文件（已被 .gitignore 挡住），不进对话、不进 git
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from .publish import clean_cookie

ROOT = Path(__file__).resolve().parent.parent

# 每个平台要导出哪些域名的 cookie
COOKIE_DOMAINS = {
    "juejin": [".juejin.cn", "juejin.cn", "api.juejin.cn"],
    "csdn": [".csdn.net", "csdn.net", "www.csdn.net", "blog.csdn.net"],
    "zhihu": [".zhihu.com", "zhihu.com", "www.zhihu.com", "zhuanlan.zhihu.com"],
    # 头条：登录票据 bd_sso_hi3jfd 在 .toutiaostatic.com（不是 .toutiao.com！），
    # 少了这个域就导不出登录态，会误判成「登录成功但没读到 Cookie」。
    # 2026-11-10 实测：头条的 cookie 分布在 mp.toutiao.com / .toutiao.com /
    # .toutiaostatic.com / .bytedance.com 四个域上。
    "toutiao": [".toutiao.com", "toutiao.com", "mp.toutiao.com",
                ".toutiaostatic.com", "toutiaostatic.com",
                ".bytedance.com", "bytedance.com"],
}

# 登录成功的判据：页面上出现用户信息元素
LOGIN_MARKERS = {
    "juejin": [
        'text=创作中心', 'text=写文章', '.avatar', '[class*="user-info"]',
        '[class*="avatar"]', 'text=我的主页', 'text=退出登录',
    ],
    "csdn": [
        'text=写文章', '[class*="user-info"]', '[class*="user-name"]',
        'text=创作中心', '.user-info', 'text=退出',
    ],
    "zhihu": [
        'text=写文章', '.Avatar', '[class*="Avatar"]', 'text=创作中心',
        'text=退出登录',
    ],
    "toutiao": [
        'text=发布文章', 'text=内容管理', '[class*="avatar"]',
    ],
}

LOGIN_URLS = {
    "juejin": "https://juejin.cn/login",
    "csdn": "https://passport.csdn.net/login?code=public",
    "zhihu": "https://www.zhihu.com/signin",
    "toutiao": "https://mp.toutiao.com/auth/page/login",
}

# 手机号验证码登录：程序自动填手机号，锋哥只填验证码
# 查到「获取验证码」按钮就说明是这种登录方式。
PHONE_LOGIN = {
    "juejin": {
        "phone": 'input[placeholder*="手机号"]',
        "code": 'input[placeholder*="验证码"]',
        "get_code": 'button:has-text("获取验证码")',
        "submit": 'button:has-text("登录")',
    },
}


def _try_phone_login(page, platform: str) -> bool:
    """自动填手机号并点「获取验证码」。

    剩下的（填验证码、点登录）由锋哥在浏览器里完成 —— 程序碰不到短信，
    也不该碰。成功返回 True 表示已进入「等验证码」状态。
    """
    cfg = PHONE_LOGIN.get(platform)
    if not cfg:
        return False
    try:
        phone_input = page.locator(cfg["phone"])
        if phone_input.count() == 0:
            return False
        btn = page.locator(cfg["get_code"])
        if btn.count() == 0:
            return False
    except Exception:
        return False

    print("[login] 检测到手机号验证码登录")
    # 手机号从本机凭据文件里读（如果之前录过），否则让锋哥自己填。
    # 存了就能自动填好 + 自动点「获取验证码」，锋哥只填短信验证码。
    try:
        from .local_secrets import SECRETS_FILE
        phone = ""
        if SECRETS_FILE.exists():
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            phone = str(data.get("JUEJIN_PHONE", "") or "").strip()
    except Exception:
        phone = ""

    try:
        if phone:
            page.locator(cfg["phone"]).fill(phone)
            print("[login] 已自动填入手机号")
            time.sleep(0.5)
            page.locator(cfg["get_code"]).click()
            print("[login] 已点「获取验证码」")
        else:
            print("[login] 请在浏览器里填手机号 → 点「获取验证码」→ 填短信验证码 → 点登录")
    except Exception as e:
        print(f"[login] 自动填手机号失败（{type(e).__name__}），请手动在浏览器里操作")
    return True


# 登录成功的硬判据：真正的登录态一定有这些 cookie 之一。
#
# 特别注意：passport_csrf_token / csrf_session_id / s_v_web_id 在**未登录**
# 时也存在（实测），不能拿来当登录判据。掘金真正的会话 cookie 是
# sessionid / sessionid_ss / sid_guard / sid_tt。
AUTH_COOKIE_NAMES = {
    # 掘金：真正的会话 cookie（未登录时只有 s_v_web_id / passport_csrf_token / csrf_session_id）
    "juejin": ["sessionid", "sessionid_ss", "sid_guard", "sid_tt"],
    # CSDN：实测未登录时只有 dc_session_id / uuid_tt_dd / bc_bot_session / hide_login=1。
    # hide_login=1 是「已登录」的显式标志（未登录时为 0 或没有），
    # 但更可靠的是 UserToken / UserName / UserNick。
    "csdn": ["UserToken", "UserName", "UserNick", "UserLevel", "UserId"],
    "zhihu": ["z_c0", "__zse_ck"],
    # 头条：登录票据是 bd_sso_hi3jfd（域 .toutiaostatic.com），
    # sessionid/sid_tt 是字节通用票据但未登录时也可能出现，
    # 所以以 bd_sso_hi3jfd 为准。
    "toutiao": ["bd_sso_hi3jfd"],
}


def _cookie_header(cookies: list[dict], domains: list[str]) -> str:
    """把 Playwright 的 cookie 列表拼成标准 Cookie 请求头。

    只取指定域名的；同名 cookie 取路径更具体的（/ 优先于 /xxx）。

    只剔除纯统计类 cookie（百度 HMACCOUNT / Hm_lvt、字节 _tea_*）：
    它们对发文毫无作用，只会污染请求头。

    刻意**保留** passport_csrf_token 这类 CSRF token ——
    云端实测跑通的掘金 Cookie 里就有它，剔掉可能反而导致鉴权失败。
    （它不能用来判断「是否已登录」，那是另一回事，见 AUTH_COOKIE_NAMES。）
    """
    picked: dict[str, str] = {}
    for c in cookies:
        domain = (c.get("domain") or "").lstrip(".")
        if not any(domain == d.lstrip(".") or domain.endswith("." + d.lstrip("."))
                   for d in domains):
            continue
        name = c.get("name") or ""
        value = c.get("value") or ""
        if not name or name.startswith("Hm_lvt") or name.startswith("HMACCOUNT"):
            continue                       # 百度统计类，无关
        if name.startswith("_tea_utm_cache") or name.startswith("__tea_cookie_tokens"):
            continue                       # 字节统计类，无关
        picked[name] = value
    return "; ".join(f"{k}={v}" for k, v in picked.items())


def _find_uuid(text: str) -> str:
    """从任意文本里抓 uuid= 的值。"""
    m = re.search(r"uuid=([0-9A-Za-z_-]{6,})", text)
    return m.group(1) if m else ""


def _all_cookies(ctx, platform: str) -> list[dict]:
    """取该平台全部域的 cookie。

    ⚠️ Playwright 的 `ctx.cookies()` 不带参数时**只返回当前页面可见的 cookie**。
    头条的登录票据 `bd_sso_hi3jfd` 在 `.toutiaostatic.com`，
    当前页是 mp.toutiao.com，所以取不到 → 会误判成「登录成功但没读到 Cookie」。

    解决办法：把该平台所有相关域都作为 URL 参数传进去。
    """
    urls = []
    for d in COOKIE_DOMAINS.get(platform, []):
        d = d.lstrip(".")
        urls.append(f"https://{d}/")
        urls.append(f"https://www.{d}/")
    try:
        return ctx.cookies(urls) if urls else ctx.cookies()
    except Exception:
        return ctx.cookies()


def capture(platform: str, browser_cfg: dict, timeout: int = 240,
            headless: bool = False) -> dict[str, Any]:
    """打开浏览器让锋哥登录，登录成功后导出 cookie。

    返回 {"cookie": str, "uuid": str, "logged_in": bool, "cookies_found": int}
    """
    from playwright.sync_api import sync_playwright

    # 实时输出：后台运行时 stdout 是块缓冲的，不加这行会等到结束才看到提示
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    profile = ROOT / str(browser_cfg.get("profile_dir", "state/browser-profile"))
    profile.mkdir(parents=True, exist_ok=True)
    domains = COOKIE_DOMAINS.get(platform, [f".{platform}.cn"])

    pw = sync_playwright().start()
    ctx = None
    try:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            channel=str(browser_cfg.get("channel", "msedge")),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 监听页面自身的 API 请求：掘金的 uuid 就是请求参数里的 uuid=，
        # 登录后页面一加载就会带上，比让锋哥手工从地址栏抠靠谱得多。
        seen_urls: list[str] = []
        page.on("response", lambda r: seen_urls.append(r.url)
                if "api.juejin.cn" in r.url and "uuid=" in r.url else None)

        page.goto(LOGIN_URLS.get(platform, "https://www.baidu.com"),
                  timeout=60000)
        print(f"[login] 已打开 {LOGIN_URLS.get(platform)}")

        # 手机号验证码登录：程序先把手机号填好并点「获取验证码」，
        # 剩下填短信验证码、点登录由锋哥在浏览器里完成。
        _try_phone_login(page, platform)

        print(f"[login] 请在弹出的 Edge 窗口里完成登录（最多等 {timeout} 秒）")

        markers = LOGIN_MARKERS.get(platform, [])
        deadline = time.time() + timeout
        logged_in = False
        # 硬校验：真正的登录态一定有这些 cookie 之一。
        # 只看页面元素会误判 —— 掘金登录页本身也有 .avatar（登录头像）。
        auth_names = AUTH_COOKIE_NAMES.get(platform, [])
        while time.time() < deadline:
            time.sleep(2)
            try:
                # 先看 cookie 硬信号
                ck = {c.get("name", "") for c in _all_cookies(ctx, platform)}
                cookie_ok = any(n in ck for n in auth_names) if auth_names else True
                # 再看页面元素
                ui_ok = False
                for m in markers:
                    try:
                        if page.locator(m).count() > 0:
                            ui_ok = True
                            break
                    except Exception:
                        continue
                # cookie 是充分条件（登录态 cookie 一出现就是登上了）；
                # 页面元素只用来「提前」结束等待，不作为必要条件 ——
                # 否则页面结构一变就永远判不出登录成功。
                ck = {c.get("name", "") for c in _all_cookies(ctx, platform)}
                cookie_ok = any(n in ck for n in auth_names) if auth_names else False
                if cookie_ok:
                    logged_in = True
                    break
                # cookie 还没到，但页面已经出现用户元素（部分站点 cookie 名字会变）
                ui_ok = False
                for m in markers:
                    try:
                        if page.locator(m).count() > 0:
                            ui_ok = True
                            break
                    except Exception:
                        continue
                if ui_ok and not auth_names:
                    logged_in = True
                    break
            except Exception:
                continue

        # 登录后把首页打开一次，让登录态 cookie 落全、并触发带 uuid 的请求
        if logged_in:
            try:
                page.goto(LOGIN_URLS.get(platform, "https://www.baidu.com").split("/login")[0],
                          timeout=30000)
                time.sleep(3)
            except Exception:
                pass

        cookies = _all_cookies(ctx, platform)
        header = clean_cookie(_cookie_header(cookies, domains))
        uuid = ""
        # uuid 优先从页面 API 请求里找（登录后页面自己会带）
        for u in seen_urls:
            uuid = _find_uuid(u)
            if uuid:
                break
        if not uuid:
            # 其次从 cookie 里找
            for c in cookies:
                if c.get("name") == "uuid" and c.get("value"):
                    uuid = str(c["value"])
                    break
        if not uuid:
            try:
                uuid = _find_uuid(page.url)
            except Exception:
                pass

        n = len([c for c in header.split(";") if c.strip()])
        return {
            "cookie": header,
            "uuid": uuid,
            "logged_in": logged_in,
            "cookies_found": n,
            "total_cookies": len(cookies),
        }
    finally:
        try:
            if ctx:
                ctx.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def save_to_secrets(values: dict[str, str]) -> Path:
    """写进本机凭据文件（已被 .gitignore 挡住）。"""
    from .local_secrets import SECRETS_FILE
    data: dict = {}
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    data.update(values)
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    return SECRETS_FILE


# 平台 → 凭据字段映射
FIELD_MAP = {
    "juejin": {"cookie": "JUEJIN_COOKIE", "uuid": "JUEJIN_UUID"},
    "csdn": {"cookie": "CSDN_COOKIE"},
    "zhihu": {"cookie": "ZHIHU_COOKIE"},
    "toutiao": {"cookie": "TOUTIAO_COOKIE"},
}
