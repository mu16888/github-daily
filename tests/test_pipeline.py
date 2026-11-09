"""离线单测：不联网、不读 Secrets、不调用任何发布端点。"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from src import schedule as sched  # noqa: E402
from src.compose import compose, md_to_html  # noqa: E402
from src.discover import (  # noqa: E402
    Repo, extract_features, extract_install_blocks, extract_intro, extract_quickstart, score,
)
from src.main import load_yaml, quota_used, seen_repos  # noqa: E402
from src.publish import CsdnPublisher, ZhihuPublisher, all_publishers  # noqa: E402
from src.seo import build as seo_build, load_seo  # noqa: E402

SETTINGS = load_yaml(ROOT / "config" / "settings.yaml")
PLATFORMS = load_yaml(ROOT / "config" / "platforms.yaml")
SEO = load_seo()
W = SETTINGS["score_weights"]

README = """# TinyTool

A tiny CLI that does one thing well.

## Quick Start

```bash
pip install tinytool
tinytool --help
```

## Install

```bash
brew install tinytool
```

## Notes

Works offline. No API key required.
"""

WIP_README = "# Beta\n\nWIP, experimental.\n\n```bash\npip install beta-tool\n```\n"


def make_repo(**kw) -> Repo:
    base = dict(
        full_name="someone/tinytool", html_url="https://github.com/someone/tinytool",
        description="A tiny CLI that does one thing well.", stars=1200,
        language="Python", license="MIT", topics=["cli", "tool"],
        created_at="2026-09-01T00:00:00Z", pushed_at="2026-11-08T00:00:00Z",
        default_branch="main", readme=README,
    )
    base.update(kw)
    r = Repo(**base)
    r.install_blocks = extract_install_blocks(r.readme)
    r.quickstart_excerpt = extract_quickstart(r.readme)
    return r


class TestExtraction(unittest.TestCase):
    def test_install_blocks_are_verbatim(self):
        blocks = extract_install_blocks(README)
        self.assertEqual(len(blocks), 2)
        self.assertIn("pip install tinytool", blocks[0])
        self.assertIn("brew install tinytool", blocks[1])
        # 必须逐字来自 README，不能被改写或补全
        for b in blocks:
            self.assertIn(b, README)

    def test_quickstart_excerpt_from_readme(self):
        q = extract_quickstart(README)
        self.assertIn("tinytool --help", q)
        self.assertNotIn("## Notes", q)

    def test_no_false_install_command(self):
        self.assertEqual(extract_install_blocks("# X\n\nNo commands here.\n"), [])

    def test_comment_mentioning_pip_is_not_an_install_block(self):
        # 回归：README 注释里 "use 'uv pip install' rather than pip install" 曾让
        # 环境准备代码块被当成安装步骤。只有行首的真命令才算。
        md = ("# X\n\n```bash\nuv venv --python=3.12 .venv\n"
              "# NOTE: use 'uv pip install' rather than just 'pip install'\n```\n")
        self.assertEqual(extract_install_blocks(md), [])

    def test_direct_install_ranked_before_git_clone(self):
        md = ("# X\n\n```bash\ngit clone https://example.com/x.git\n```\n\n"
              "```bash\npip install xtool\n```\n")
        blocks = extract_install_blocks(md)
        self.assertEqual(len(blocks), 2)
        self.assertIn("pip install xtool", blocks[0])

    def test_intro_extraction_strips_badges_and_stops_at_next_heading(self):
        md = ('# X\n\nA tool that solves Y.\n\n'
              '<p><a href="#"><img src="badge.svg"></a></p>\n\nMore intro text.\n\n## Install\n')
        intro = extract_intro(md)
        self.assertIn("A tool that solves Y.", intro)
        self.assertIn("More intro text.", intro)
        self.assertNotIn("badge.svg", intro)
        self.assertNotIn("## Install", intro)

    def test_section_strips_relative_image_blocks(self):
        md = ('# X\n\n## How it works\n\n'
              '<picture><img src="assets/architecture.png"></picture>\n\n'
              'Real explanation here.\n\n## Next\n')
        s = extract_features(md)
        self.assertIn("Real explanation here.", s)
        self.assertNotIn("<picture>", s)
        self.assertNotIn("assets/architecture.png", s)

    def test_drop_trailing_fragment(self):
        from src.discover import _drop_trailing_fragment
        self.assertEqual(_drop_trailing_fragment("A full sentence. It ships as a"), "A full sentence.")
        self.assertEqual(_drop_trailing_fragment("Already complete."), "Already complete.")

    def test_intro_truncation_does_not_cut_mid_sentence(self):
        md = "# X\n\n" + ("This is a complete sentence with enough words. " * 30) + "\n\n## Install\n"
        intro = extract_intro(md, limit=300)
        self.assertTrue(intro.rstrip().endswith("."), repr(intro[-80:]))

    def test_quickstart_truncation_keeps_balanced_fences(self):
        md = "# X\n\n## Quick Start\n\n" + ("intro line\n" * 200) + "```bash\necho hi\n```\n"
        q = extract_quickstart(md, limit=300)
        self.assertEqual(q.count("```") % 2, 0)


class TestScoring(unittest.TestCase):
    def test_friendly_repo_scores_above_threshold(self):
        r = make_repo()
        s, signals = score(r, W)
        self.assertGreaterEqual(s, SETTINGS["daily"]["min_score"])
        self.assertTrue(any("安装命令" in x for x in signals))
        self.assertTrue(any("Quick Start" in x for x in signals))

    def test_wip_is_penalized(self):
        clean = make_repo()
        wip = make_repo(readme=WIP_README)
        s1, _ = score(clean, W)
        s2, sig = score(wip, W)
        self.assertLess(s2, s1)
        self.assertTrue(any("WIP" in x for x in sig))

    def test_no_readme_no_install_bonus(self):
        r = make_repo(readme="", install_blocks=[])
        s, _ = score(r, W)
        self.assertLess(s, SETTINGS["daily"]["min_score"])


class TestHtml(unittest.TestCase):
    def test_headings_code_and_escape(self):
        h = md_to_html("# T\n\n```bash\n<p>echo</p>\n```\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n")
        self.assertIn("<h1>T</h1>", h)
        self.assertIn("&lt;p&gt;echo&lt;/p&gt;", h)   # 代码块内必须转义
        self.assertIn("<table>", h)
        self.assertIn("<td>1</td>", h)

    def test_inline_link_and_bold(self):
        h = md_to_html("See [repo](https://example.com) and **bold**.\n")
        self.assertIn('href="https://example.com"', h)
        self.assertIn("<strong>bold</strong>", h)


class TestCompose(unittest.TestCase):
    def test_article_contains_only_real_facts(self):
        r = make_repo()
        a = compose(r, "2026-11-09", SETTINGS)
        self.assertIn("pip install tinytool", a["markdown"])
        self.assertIn("1200", a["markdown"])
        self.assertIn("MIT", a["markdown"])
        self.assertIn("<h1>", a["html"])
        self.assertLessEqual(len(a["title"]), PLATFORMS["platforms"]["juejin"]["title_max"])
        self.assertLessEqual(len(a["brief"]), PLATFORMS["platforms"]["juejin"]["brief_max"])
        self.assertNotIn("TODO", a["markdown"])


class TestPublishers(unittest.TestCase):
    def test_missing_secrets_is_skipped_not_published(self):
        pubs = all_publishers(PLATFORMS, SETTINGS)
        article = {"title": "t", "html": "<p>x</p>", "markdown": "x", "brief": "b"}
        results = [p.publish(article) for p in pubs]
        self.assertTrue(all(r.status in ("skipped", "dry_run") for r in results))
        self.assertEqual(sum(r.status == "published" for r in results), 0)

    def test_zhihu_requires_standing_consent(self):
        secrets = {"ZHIHU_APP_KEY": "k", "ZHIHU_APP_SECRET": "s"}
        pub = ZhihuPublisher(PLATFORMS["platforms"]["zhihu"], SETTINGS, secrets, dry_run=False)
        r = pub.publish({"title": "t", "html": "<p>x</p>"})
        self.assertEqual(r.status, "skipped")   # 不联网，直接被官方确认约束挡住

    def test_zhihu_signature_matches_headers(self):
        cfg = dict(PLATFORMS["platforms"]["zhihu"])
        settings = json.loads(json.dumps(SETTINGS))
        settings["zhihu"]["standing_consent"] = True
        pub = ZhihuPublisher(cfg, settings, {"ZHIHU_APP_KEY": "mykey", "ZHIHU_APP_SECRET": "mysecret"}, dry_run=False)
        url, headers, body = pub.build({"title": "标题", "html": "<p>正文</p>"})
        self.assertEqual(url, "https://openapi.zhihu.com/openapi/publish")
        self.assertEqual(body["content"]["html"], "<p>正文</p>")
        self.assertNotIn("markdown", json.dumps(body, ensure_ascii=False))
        sign_string = (
            f"app_key:{headers['X-App-Key']}|ts:{headers['X-Timestamp']}|"
            f"logid:{headers['X-Log-Id']}|extra_info:{headers['X-Extra-Info']}"
        )
        expected = base64.b64encode(
            hmac.new(b"mysecret", sign_string.encode(), hashlib.sha256).digest()
        ).decode()
        self.assertEqual(headers["X-Sign"], expected)
        self.assertNotIn("mysecret", json.dumps(body, ensure_ascii=False))

    def test_csdn_payload_html_and_no_secret_override(self):
        pub = CsdnPublisher(PLATFORMS["platforms"]["csdn"], SETTINGS, {"CSDN_COOKIE": "c"}, dry_run=False)
        _url, headers, body = pub.build({
            "title": "t", "html": "<h1>t</h1>", "markdown": "# t", "brief": "b",
        })
        self.assertIn("<h1>t</h1>", body["content"])
        self.assertEqual(body["markdowncontent"], "# t")
        self.assertEqual(body["readType"], "public")
        self.assertEqual(body["type"], "original")
        self.assertEqual(headers["x-ca-signature-headers"], "x-ca-key,x-ca-nonce")
        self.assertIn("x-ca-signature", headers)


class TestSeo(unittest.TestCase):
    def test_titles_are_platform_specific_and_within_limits(self):
        r = make_repo()
        s = seo_build(r, "2026-11-09", SEO)
        self.assertEqual(set(s["titles"]), {"zhihu", "juejin", "csdn"})
        for p, t in s["titles"].items():
            self.assertIn("tinytool", t, f"{p} 标题必须含项目名（核心搜索词）")
            self.assertLessEqual(len(t), SEO["platforms"][p]["title_max"])
        # 三个平台风格应有差异，不是同一句通稿
        self.assertEqual(len(set(s["titles"].values())), 3)

    def test_titles_contain_search_intent_words(self):
        s = seo_build(make_repo(), "2026-11-09", SEO)
        joined = "".join(s["titles"].values())
        self.assertTrue(any(w in joined for w in ("安装", "上手", "怎么用")))

    def test_hook_only_uses_detected_signals(self):
        # 无任何可证实信号时，只能用兜底事实，不能冒出「一行命令 / 神器 / 必看」
        r = make_repo(stars=200, license="NOASSERTION", created_at="2020-01-01T00:00:00Z")
        r.install_blocks = []
        s = seo_build(r, "2026-11-09", SEO)
        joined = "".join(s["titles"].values())
        self.assertNotIn("一行命令", joined)
        self.assertNotIn("神器", joined)
        self.assertIn(SEO["hooks"]["fallback"], joined)

    def test_hook_prefers_concrete_numbers_over_generic_license(self):
        r = make_repo()
        r.install_blocks = ["pip install tinytool\ntinytool --help"]  # 两行，不触发「一行命令」
        s = seo_build(r, "2026-11-09", SEO)
        joined = "".join(s["titles"].values())
        self.assertNotIn("一行命令", joined)
        self.assertIn("1200 Star 的开源项目", joined)

    def test_license_hook_used_when_no_stronger_signal(self):
        r = make_repo(stars=200, license="MIT", created_at="2020-01-01T00:00:00Z")
        r.install_blocks = ["echo hi"]
        s = seo_build(r, "2026-11-09", SEO)
        self.assertIn("MIT 开源协议", "".join(s["titles"].values()))

    def test_one_command_hook_requires_first_block_to_be_single_package_command(self):
        # 回归：首选安装块 3 行、另一个块 1 行 npx skills add 时，
        # 不能声称「一行命令就能装好」。
        r = make_repo()
        r.install_blocks = [
            "npm install -g agent-desktop\nagent-desktop status\nagent-desktop permissions --guide",
            "npx skills add https://github.com/x/y --skill z",
        ]
        s = seo_build(r, "2026-11-09", SEO)
        self.assertNotIn("一行命令", "".join(s["titles"].values()))

    def test_one_command_hook_fires_for_true_single_install(self):
        r = make_repo()
        r.install_blocks = ["pip install tinytool"]
        s = seo_build(r, "2026-11-09", SEO)
        self.assertIn("一行命令就能装好", "".join(s["titles"].values()))

    def test_every_platform_title_contains_hook(self):
        s = seo_build(make_repo(), "2026-11-09", SEO)
        for p, t in s["titles"].items():
            self.assertTrue(any(k in t for k in ("一行命令", "开源协议", "Star", "近期新项目", "现成安装命令")),
                            f"{p} 标题缺少真实钩子: {t}")

    def test_article_has_seo_lead_and_faq(self):
        a = compose(make_repo(), "2026-11-09", SETTINGS, SEO)
        self.assertIn("安装教程", a["markdown"])
        self.assertIn("常见问题", a["markdown"])
        self.assertIn("tinytool 怎么安装？", a["markdown"])
        self.assertIn("tinytool,GitHub开源项目", a["tags"])

    def test_publisher_uses_platform_title(self):
        a = compose(make_repo(), "2026-11-09", SETTINGS, SEO)
        z = ZhihuPublisher(PLATFORMS["platforms"]["zhihu"], SETTINGS,
                           {"ZHIHU_APP_KEY": "k", "ZHIHU_APP_SECRET": "s"}, dry_run=False)
        _u, _h, body = z.build(a)
        self.assertEqual(body["content"]["title"], a["titles"]["zhihu"])


class TestStructure(unittest.TestCase):
    def test_pain_point_before_features_and_install(self):
        md = compose(make_repo(), "2026-11-09", SETTINGS, SEO)["markdown"]
        i_pain = md.find("## 一、")
        i_what = md.find("## 二、")
        i_feat = md.find("## 三、")
        i_inst = md.find("## 五、")
        self.assertTrue(0 < i_pain < i_what < i_feat < i_inst)
        self.assertIn("解决什么问题", md[i_pain:i_what])
        self.assertIn("核心功能", md[i_feat:i_inst])

    def test_missing_problem_section_is_honest_not_fabricated(self):
        r = make_repo(problem_excerpt="", features_excerpt="")
        md = compose(r, "2026-11-09", SETTINGS, SEO)["markdown"]
        self.assertIn("没有检出", md)
        self.assertIn("不编造痛点", md)
        self.assertIn("不代为罗列功能", md)

    def test_author_problem_and_features_are_quoted_verbatim(self):
        r = make_repo(
            problem_excerpt="We built this because doing X by hand is painful.",
            features_excerpt="- feature A\n- feature B",
        )
        md = compose(r, "2026-11-09", SETTINGS, SEO)["markdown"]
        self.assertIn("We built this because doing X by hand is painful.", md)
        self.assertIn("- feature A\n- feature B", md)
        self.assertIn("原文摘录", md)

    def test_faq_and_lead_cover_pain_point(self):
        md = compose(make_repo(), "2026-11-09", SETTINGS, SEO)["markdown"]
        self.assertIn("tinytool 解决什么问题？", md)
        self.assertIn("先讲 **tinytool** 解决什么问题", md)

    def test_intro_original_text_quoted_when_no_why_section(self):
        r = make_repo(problem_excerpt="",
                      intro_excerpt="Computer use for AI agents: see and operate desktop apps.\nSecond line.")
        md = compose(r, "2026-11-09", SETTINGS, SEO)["markdown"]
        self.assertIn("README 开头原文", md)
        self.assertIn("> Computer use for AI agents: see and operate desktop apps.", md)

    def test_quoted_intro_has_no_trailing_fragment(self):
        r = make_repo(problem_excerpt="", features_excerpt="",
                      intro_excerpt="First complete sentence. It ships as a")
        md = compose(r, "2026-11-09", SETTINGS, SEO)["markdown"]
        self.assertIn("First complete sentence.", md)
        self.assertNotIn("It ships as a", md)

    def test_all_title_variants_lead_with_pain_point_question(self):
        for p, pcfg in SEO["platforms"].items():
            for tpl in pcfg["templates"]:
                self.assertIn("解决什么问题", tpl, f"{p} 模板缺少痛点词: {tpl}")


class TestQuota(unittest.TestCase):
    def test_quota_counts_only_today_success(self):
        today = __import__("datetime").date.today().isoformat()
        state = {"seen": {
            "a/b": {"platforms": {"zhihu": {"at": today + "T01:00:00+00:00"}}},
            "c/d": {"platforms": {"zhihu": {"at": "2020-01-01T01:00:00+00:00"}}},
            "e/f": {"platforms": {"juejin": {"at": today + "T01:00:00+00:00"}}},
        }}
        self.assertEqual(quota_used(state, "zhihu", today, "calendar_day"), 1)
        self.assertEqual(quota_used(state, "juejin", today, "calendar_day"), 1)
        self.assertEqual(quota_used(state, "csdn", today, "calendar_day"), 0)

    def test_config_caps_every_platform_at_one(self):
        self.assertEqual(set(SETTINGS["quota"]["per_day"].values()), {1})


class TestDedup(unittest.TestCase):
    def test_recent_repo_is_seen(self):
        today = __import__("datetime").date.today().isoformat()
        state = {"seen": {"a/b": {"first_date": today, "platforms": {}}}}
        self.assertIn("a/b", seen_repos(state, 120))

    def test_old_repo_can_be_picked_again(self):
        state = {"seen": {"old/repo": {"first_date": "2020-01-01", "platforms": {}}}}
        self.assertNotIn("old/repo", seen_repos(state, 120))


class TestSchedule(unittest.TestCase):
    """仿人工发布时间：确定性 + 每天错位 + 闸门不重发。"""
    CFG = SETTINGS["schedule"]
    TZ = sched.local_tz(CFG)
    DAY0 = dt.date(2026, 11, 9)

    def test_same_day_same_target(self):
        d = self.DAY0
        self.assertEqual(sched.target_for(d, self.CFG), sched.target_for(d, self.CFG))

    def test_two_weeks_are_not_fixed_times(self):
        seen = set()
        for i in range(14):
            t = sched.target_for(self.DAY0 + dt.timedelta(days=i), self.CFG).astimezone(self.TZ)
            seen.add(t.strftime("%H:%M:%S"))
        self.assertGreaterEqual(len(seen), 13, "14 天里几乎每天都要落在不同的时刻")

    def test_target_stays_inside_window_and_avoids_round_minutes(self):
        start = sched._hhmm(self.CFG["window_start"])
        end = sched._hhmm(self.CFG["window_end"])
        for i in range(14):
            d = self.DAY0 + dt.timedelta(days=i)
            shift = self.CFG["weekend_delay_minutes"] if d.weekday() >= 5 else 0
            t = sched.target_for(d, self.CFG).astimezone(self.TZ)
            minute = t.hour * 60 + t.minute
            self.assertGreaterEqual(minute, start + shift)
            self.assertLessEqual(minute, end + shift)
            self.assertNotEqual(t.minute % 5, 0, f"{d} 落在整 5 分刻度上")
            self.assertNotEqual(t.second, 0)

    def test_salt_changes_the_whole_series(self):
        cfg = dict(self.CFG, salt="another-salt")
        a = [sched.target_for(self.DAY0 + dt.timedelta(days=i), self.CFG) for i in range(5)]
        b = [sched.target_for(self.DAY0 + dt.timedelta(days=i), cfg) for i in range(5)]
        self.assertNotEqual(a, b)

    def test_gate_wait_sleep_run_and_done(self):
        target = sched.target_for(self.DAY0, self.CFG)
        tz = self.TZ
        action, _, _ = sched.decide(target - dt.timedelta(minutes=60), self.CFG, {})
        self.assertEqual(action, "wait", "离目标还很远，这一棒应空跑退出")
        action, wait, _ = sched.decide(target - dt.timedelta(minutes=5), self.CFG, {})
        self.assertEqual(action, "sleep")
        self.assertAlmostEqual(wait, 300, delta=2)
        action, _, _ = sched.decide(target + dt.timedelta(minutes=5), self.CFG, {})
        self.assertEqual(action, "run", "错过目标要能补发，不能漏一天")
        state = {"seen": {}, "schedule": {"last_dispatched": self.DAY0.isoformat()}}
        action, _, _ = sched.decide(target + dt.timedelta(minutes=5), self.CFG, state)
        self.assertEqual(action, "done", "当天已派发，后续唤醒必须空跑")

    def test_force_and_off(self):
        target = sched.target_for(self.DAY0, self.CFG)
        state = {"schedule": {"last_dispatched": self.DAY0.isoformat()}}
        self.assertEqual(sched.decide(target, self.CFG, state, force=True)[0], "run")
        self.assertEqual(sched.decide(target, dict(self.CFG, enabled=False), {})[0], "off")

    def test_stagger_is_monotonic_deterministic_and_bounded(self):
        names = ["zhihu", "juejin", "csdn"]
        p1 = sched.stagger_plan(self.DAY0, self.CFG, names)
        p2 = sched.stagger_plan(self.DAY0, self.CFG, names)
        self.assertEqual(p1, p2)
        self.assertEqual(p1["zhihu"], 0)
        self.assertLess(p1["juejin"], p1["csdn"])
        lo, hi = self.CFG["stagger_min_seconds"], self.CFG["stagger_max_seconds"]
        self.assertGreaterEqual(p1["juejin"], lo)
        self.assertLessEqual(p1["csdn"], 2 * hi)

    def test_mark_dispatched_keeps_ledger_intact(self):
        state = {"version": 1, "seen": {"a/b": {"first_date": "2026-11-01", "platforms": {}}}}
        sched.mark_dispatched(state, "2026-11-09")
        self.assertEqual(state["schedule"]["last_dispatched"], "2026-11-09")
        self.assertIn("a/b", state["seen"])
        self.assertEqual(state["seen"]["a/b"]["first_date"], "2026-11-01")


if __name__ == "__main__":
    unittest.main()
