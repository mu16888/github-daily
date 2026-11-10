"""本机模式护栏测试。

重点盯四类事故：
1. 凭据缺失时必须 skipped / dry_run，绝不假报 published
2. 本机台账不能污染云端台账
3. 去重必须合并云端已发项目（否则同一个项目发两遍）
4. 字节限额（微信标题/摘要按 UTF-8 字节算，不是字数）
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.local import (build_publishers, ledger_path, load_ledger, load_yaml,
                       local_cfg, quota_used, seen_repos)
from src.local_publish import (BrowserPublisher, WechatPublisher, fit_bytes,
                               md_to_wechat_html, _plain_for_editor)
from src.local_secrets import load_local_secrets, secrets_status
from src.publish import Result


class TestLocalSecrets(unittest.TestCase):
    def test_env_overrides_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.json"
            f.write_text(json.dumps({"JUEJIN_COOKIE": "from-file",
                                     "CSDN_COOKIE": "csdn-file"}), encoding="utf-8")
            import os
            os.environ["JUEJIN_COOKIE"] = "from-env"
            try:
                s = load_local_secrets(f)
                self.assertEqual(s["JUEJIN_COOKIE"], "from-env")   # 环境变量优先
                self.assertEqual(s["CSDN_COOKIE"], "csdn-file")    # 文件补充
            finally:
                os.environ.pop("JUEJIN_COOKIE", None)

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            s = load_local_secrets(Path(d) / "nope.json")
            # 环境里可能真有值，只断言不报错
            self.assertIsInstance(s, dict)

    def test_status_never_leaks_values(self):
        st = secrets_status()
        blob = json.dumps(st, ensure_ascii=False)
        for probe in ("sessionid=", "passport_csrf_token=", "secret="):
            self.assertNotIn(probe, blob)


class TestLocalLedger(unittest.TestCase):
    def test_local_ledger_separate_from_cloud(self):
        lcfg = local_cfg()
        p = ledger_path(lcfg)
        self.assertNotEqual(p.name, "published.json")
        self.assertIn("local", p.name)

    def test_ledger_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "l.json"
            self.assertEqual(load_ledger(f)["seen"], {})
            f.write_text(json.dumps({"version": 1, "seen": {
                "a/b": {"first_date": "2026-11-10", "platforms": {}}}}), encoding="utf-8")
            self.assertIn("a/b", load_ledger(f)["seen"])

    def test_seen_merges_cloud_ledger(self):
        """云端发过的项目必须进去重集合，否则同一个项目发两遍。"""
        state = {"seen": {}}
        cloud = {"seen": {"x/y": {"first_date": dt_today(), "platforms": {}}}}
        got = seen_repos(state, 120, cloud)
        self.assertIn("x/y", got)

    def test_seen_respects_window(self):
        old = {"seen": {"old/p": {"first_date": "2020-01-01", "platforms": {}}}}
        self.assertNotIn("old/p", seen_repos({}, 120, old))

    def test_quota_counts_today(self):
        st = {"seen": {"a/b": {"platforms": {"juejin": {
            "at": "2026-11-10T02:00:00+00:00", "status": "published"}}}}}
        self.assertEqual(quota_used(st, "juejin", "2026-11-10"), 1)
        self.assertEqual(quota_used(st, "juejin", "2026-11-11"), 0)
        self.assertEqual(quota_used(st, "csdn", "2026-11-10"), 0)


def dt_today() -> str:
    import datetime as dt
    return dt.date.today().isoformat()


class TestWechatPublisher(unittest.TestCase):
    def test_byte_limits_not_char_limits(self):
        """微信按 UTF-8 字节算：10 个中文 = 30 字节。"""
        s = "中" * 30
        out = fit_bytes(s, 20)
        self.assertLessEqual(len(out.encode("utf-8")), 20)
        self.assertEqual(len(out), 6)      # 6 字 = 18 字节，下一字就超

    def test_missing_wechat_config_is_skipped(self):
        pub = WechatPublisher({}, {}, {}, True, wechat_cfg={})
        # 本机沐风博客配置存在时不算缺；这里只断言「缺就 skipped」
        if pub.missing():
            r = pub.publish({"repo": "a/b", "markdown": "x", "titles": {}, "briefs": {}})
            self.assertEqual(r.status, "skipped")

    def test_dry_run_never_calls_api(self):
        pub = WechatPublisher({}, {}, {}, True, wechat_cfg={})
        r = pub.publish({"repo": "a/b", "markdown": "# t\n\n正文",
                         "titles": {"wechat": "标题"}, "briefs": {"wechat": "摘要"}})
        self.assertEqual(r.status, "dry_run")
        self.assertIn("未实际发送", r.detail)

    def test_html_has_inline_styles(self):
        html = md_to_wechat_html("# 标题\n\n正文内容\n\n```bash\npip install x\n```")
        self.assertIn("style=", html)
        self.assertIn("font-size", html)

    def test_html_escapes_html_in_source(self):
        html = md_to_wechat_html("<script>alert(1)</script>")
        self.assertNotIn("<script>", html)

    def test_result_detail_redacted(self):
        r = Result("wechat", "failed", detail="cookie: a=1; b=2; c=3; d=4")
        self.assertNotIn("a=1", r.detail)


class TestBrowserPublisher(unittest.TestCase):
    def test_login_url_required(self):
        pub = BrowserPublisher("zhihu", {}, {}, {}, True, browser_cfg={})
        self.assertFalse(pub.login())     # 没配 login_url 直接返回 False，不抛异常

    def test_dry_run_does_not_open_browser(self):
        pub = BrowserPublisher("zhihu", {}, {}, {}, True, browser_cfg={})
        r = pub.publish({"repo": "a/b", "markdown": "x", "titles": {}, "briefs": {}})
        self.assertEqual(r.status, "dry_run")

    def test_plain_text_strips_markdown(self):
        out = _plain_for_editor("# 标题\n\n**粗体** 和 `代码`\n\n- 项目一\n")
        self.assertNotIn("#", out)
        self.assertNotIn("**", out)
        self.assertIn("粗体", out)
        self.assertIn("项目一", out)


class TestLocalPublishers(unittest.TestCase):
    def test_build_respects_platform_switches(self):
        lcfg = local_cfg()
        settings = load_yaml(Path("config/settings.yaml"))
        platforms = load_yaml(Path("config/platforms.yaml"))
        pubs = build_publishers(lcfg, settings, platforms, True)
        names = {p.name for p in pubs}
        for want in ("juejin", "csdn", "wechat"):
            self.assertIn(want, names)

    def test_disabled_platform_not_built(self):
        lcfg = dict(local_cfg())
        lcfg["platforms"] = {**lcfg.get("platforms", {}), "toutiao": {"enabled": False}}
        settings = load_yaml(Path("config/settings.yaml"))
        platforms = load_yaml(Path("config/platforms.yaml"))
        pubs = build_publishers(lcfg, settings, platforms, True)
        self.assertNotIn("toutiao", {p.name for p in pubs})

    def test_no_credentials_means_skipped_not_published(self):
        """缺 Cookie 时发布器必须 skipped，绝不能报成功。"""
        from src.publish import JuejinPublisher
        platforms = load_yaml(Path("config/platforms.yaml"))
        pub = JuejinPublisher(platforms["platforms"]["juejin"], {}, {}, False)
        r = pub.publish({"repo": "a/b", "markdown": "x", "titles": {}, "briefs": {}})
        self.assertEqual(r.status, "skipped")
        self.assertIn("缺少", r.detail)


class TestBrowserCreds(unittest.TestCase):
    """浏览器登录态自动导出：拼装与隔离逻辑。"""

    FAKE = [
        {"domain": ".juejin.cn", "name": "sessionid", "value": "abc123"},
        {"domain": "api.juejin.cn", "name": "sid_guard", "value": "xyz"},
        {"domain": ".juejin.cn", "name": "passport_csrf_token", "value": "tok"},
        {"domain": ".bing.com", "name": "other", "value": "SHOULD_NOT_APPEAR"},
        {"domain": ".juejin.cn", "name": "Hm_lvt_xxx", "value": "BAIDU_STAT"},
        {"domain": ".zhihu.com", "name": "z_c0", "value": "ZHIHU_ONLY"},
    ]

    def test_only_target_domain_included(self):
        from src.browser_creds import _cookie_header, COOKIE_DOMAINS
        h = _cookie_header(self.FAKE, COOKIE_DOMAINS["juejin"])
        self.assertIn("sessionid=abc123", h)
        self.assertIn("sid_guard=xyz", h)
        self.assertIn("passport_csrf_token=tok", h)

    def test_cross_domain_cookie_not_leaked(self):
        """跨域 cookie 绝不能混进来 —— 掘金的请求带上别人的 cookie 是安全事故。"""
        from src.browser_creds import _cookie_header, COOKIE_DOMAINS
        h = _cookie_header(self.FAKE, COOKIE_DOMAINS["juejin"])
        self.assertNotIn("SHOULD_NOT_APPEAR", h)
        self.assertNotIn("ZHIHU_ONLY", h)

    def test_analytics_cookie_filtered(self):
        from src.browser_creds import _cookie_header, COOKIE_DOMAINS
        h = _cookie_header(self.FAKE, COOKIE_DOMAINS["juejin"])
        self.assertNotIn("BAIDU_STAT", h)

    def test_uuid_extracted_from_url(self):
        from src.browser_creds import _find_uuid
        self.assertEqual(
            _find_uuid("https://juejin.cn/post/123?uuid=7706396623119189504&x=1"),
            "7706396623119189504")

    def test_uuid_absent_returns_empty(self):
        from src.browser_creds import _find_uuid
        self.assertEqual(_find_uuid("https://juejin.cn/post/123"), "")

    def test_csrf_token_kept_in_export(self):
        """passport_csrf_token 必须保留 —— 云端实测跑通的掘金 Cookie 里就有它，
        导出发文请求头时剔掉可能导致鉴权失败。"""
        from src.browser_creds import _cookie_header, COOKIE_DOMAINS
        fake = [{"domain": ".juejin.cn", "name": "passport_csrf_token", "value": "tok"}]
        h = _cookie_header(fake, COOKIE_DOMAINS["juejin"])
        self.assertIn("passport_csrf_token=tok", h)

    def test_analytics_cookies_dropped(self):
        from src.browser_creds import _cookie_header, COOKIE_DOMAINS
        fake = [
            {"domain": ".juejin.cn", "name": "Hm_lvt_98", "value": "x"},
            {"domain": ".juejin.cn", "name": "_tea_utm_cache_2608", "value": "x"},
            {"domain": ".juejin.cn", "name": "sessionid", "value": "keep"},
        ]
        h = _cookie_header(fake, COOKIE_DOMAINS["juejin"])
        self.assertNotIn("Hm_lvt", h)
        self.assertNotIn("_tea_utm_cache", h)
        self.assertIn("sessionid=keep", h)

    def test_auth_cookie_names_exclude_anonymous(self):
        """登录判据不能包含匿名 cookie。

        实测：未登录时掘金已经有 passport_csrf_token / csrf_session_id /
        s_v_web_id，用它们判登录会误报「已登录」。
        """
        from src.browser_creds import AUTH_COOKIE_NAMES
        juejin = set(AUTH_COOKIE_NAMES["juejin"])
        for bad in ("passport_csrf_token", "csrf_session_id", "s_v_web_id"):
            self.assertNotIn(bad, juejin)
        self.assertIn("sessionid", juejin)

    def test_phone_login_config_for_juejin(self):
        from src.browser_creds import PHONE_LOGIN
        self.assertIn("juejin", PHONE_LOGIN)
        cfg = PHONE_LOGIN["juejin"]
        for key in ("phone", "code", "get_code"):
            self.assertIn(key, cfg)

    def test_field_map_covers_platforms(self):
        from src.browser_creds import FIELD_MAP
        for p in ("juejin", "csdn", "zhihu", "toutiao"):
            self.assertIn(p, FIELD_MAP)
        self.assertEqual(FIELD_MAP["juejin"]["cookie"], "JUEJIN_COOKIE")
        self.assertEqual(FIELD_MAP["juejin"]["uuid"], "JUEJIN_UUID")
        # 每个平台的 cookie 字段名必须各不相同，否则登录结果的校验会串台
        # （2026-11-10 bug：local.py 里用 if/else 三元判断，头条走 else 去找
        #  ZHIHU_COOKIE，而它实际写 TOUTIAO_COOKIE → 明明登录成功却误报失败）
        cookie_keys = [FIELD_MAP[p]["cookie"] for p in FIELD_MAP]
        self.assertEqual(len(cookie_keys), len(set(cookie_keys)),
                         f"cookie 字段名重复：{cookie_keys}")

    def test_toutiao_cookie_domains_include_static_host(self):
        """头条的登录票据 bd_sso_hi3jfd 在 .toutiaostatic.com，
        域名表漏了它就导不出登录态。"""
        from src.browser_creds import COOKIE_DOMAINS
        doms = COOKIE_DOMAINS["toutiao"]
        self.assertIn(".toutiaostatic.com", doms)
        self.assertIn(".toutiao.com", doms)

    def test_toutiao_auth_cookie_is_sso_ticket(self):
        """头条登录判据必须是 bd_sso_hi3jfd（不是字节通用的 sessionid）。"""
        from src.browser_creds import AUTH_COOKIE_NAMES
        self.assertIn("bd_sso_hi3jfd", AUTH_COOKIE_NAMES["toutiao"])

    def test_all_cookies_passes_urls(self):
        """ctx.cookies() 不带参数只返回当前页可见的 cookie，
        必须显式传多个域的 URL，否则跨域票据拿不到。"""
        import inspect
        from src import browser_creds
        src = inspect.getsource(browser_creds._all_cookies)
        self.assertIn("ctx.cookies(urls)", src)
        self.assertIn("COOKIE_DOMAINS", src)

    def test_secrets_file_is_gitignored(self):
        """本机凭据文件绝不能进仓库。"""
        import subprocess
        r = subprocess.run(["git", "check-ignore", "-q", "config/local_secrets.json"],
                           cwd=str(Path(__file__).resolve().parent.parent))
        self.assertEqual(r.returncode, 0, "local_secrets.json 未被 gitignore 挡住")


if __name__ == "__main__":
    unittest.main()
