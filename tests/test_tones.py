"""五平台调性渲染的护栏测试。

锁住三件事：五份稿子真的不同、各平台形态符合各自调性、任何一版都不退回机器腔。
"""
import unittest
from pathlib import Path

from src.compose import compose
from src.discover import Repo, extract_install_blocks, extract_quickstart, score
from src.main import load_yaml
from src.seo import load_seo
from src.tones import BANNED, PLATFORMS

ROOT = Path(__file__).resolve().parent.parent

README = """# agent-desktop

Computer use for AI agents: see and operate desktop apps through the OS accessibility tree.

## Why

Doing computer use with screenshots is brittle. Pixels move, themes change, and a model has to guess where to click. We wanted a stable, machine-readable handle on every element instead.

## Install

```bash
brew install agent-desktop
```

## Quick Start

```bash
agent-desktop snapshot --app Safari
```

## Features

- Reads the OS accessibility tree, no screenshots or pixel matching
- Returns every actionable element as JSON with a stable ref
- Ships as a CLI and a C library
"""


def make_repo() -> Repo:
    r = Repo(
        full_name="vercel-labs/agent-desktop",
        html_url="https://github.com/vercel-labs/agent-desktop",
        description="Computer use CLI for AI agents",
        stars=19919,
        language="Rust",
        license="Apache-2.0",
        topics=["ai-agents", "automation", "cli", "computer-use", "accessibility"],
        created_at="2026-08-01T00:00:00Z",
        pushed_at="2026-11-08T00:00:00Z",
        default_branch="main",
        readme=README,
    )
    r.install_blocks = extract_install_blocks(README)
    r.quickstart_excerpt = extract_quickstart(README)
    r.problem_excerpt = (
        "Doing computer use with screenshots is brittle. "
        "Pixels move, themes change, and a model has to guess where to click."
    )
    r.features_excerpt = (
        "- Reads the OS accessibility tree, no screenshots or pixel matching\n"
        "- Returns every actionable element as JSON with a stable ref\n"
        "- Ships as a CLI and a C library"
    )
    r.intro_excerpt = (
        "Computer use for AI agents: see and operate desktop apps "
        "through the OS accessibility tree."
    )
    cfg = load_yaml(ROOT / "config" / "settings.yaml")
    r.score, r.signals = score(r, cfg["score_weights"])
    return r


def articles():
    cfg = load_yaml(ROOT / "config" / "settings.yaml")
    result = compose(make_repo(), "2026-11-10", cfg, load_seo())
    return result, result["articles"]


class TestFiveTones(unittest.TestCase):
    def test_five_platforms_present_without_error(self):
        result, arts = articles()
        self.assertEqual(result["articles_error"], "")
        self.assertEqual(set(arts), set(PLATFORMS))

    def test_titles_all_distinct(self):
        _, arts = articles()
        titles = [a["title"] for a in arts.values()]
        self.assertEqual(len(set(titles)), len(PLATFORMS), titles)
        for p, a in arts.items():
            self.assertTrue(a["title"].strip(), p)

    def test_bodies_all_distinct(self):
        _, arts = articles()
        bodies = [a["body"] for a in arts.values()]
        self.assertEqual(len(set(bodies)), len(PLATFORMS))

    def test_no_unified_template_leak(self):
        """不能五个平台又是同一句「解决什么问题？」换尾巴。"""
        _, arts = articles()
        titles = [a["title"] for a in arts.values()]
        shared = sum("解决什么问题？" in t for t in titles)
        self.assertLess(shared, 3, titles)

    def test_leads_all_distinct(self):
        _, arts = articles()
        leads = [a["lead"] for a in arts.values()]
        self.assertEqual(len(set(leads)), len(PLATFORMS))

    def test_platform_shapes_differ(self):
        """知乎保留代码块与表格，公众号/头条都不带。"""
        _, arts = articles()
        self.assertIn("```", arts["zhihu"]["body"])
        self.assertIn("| 项目 |", arts["zhihu"]["body"])
        for p in ("wechat", "toutiao"):
            self.assertNotIn("```", arts[p]["body"], p)
            self.assertNotIn("| 项目 |", arts[p]["body"], p)

    def test_mass_audience_versions_are_plain_chinese(self):
        """公众号 / 头条：不塞英文原文、不留空引导和元叙述，但要讲清怎么装。"""
        _, arts = articles()
        for p in ("wechat", "toutiao"):
            body = arts[p]["body"]
            for word in ("往下看", "能确认的有这些", "作者在项目说明里写了缘由",
                         "ai-agents", "```", "| 项目 |"):
                self.assertNotIn(word, body, f"{p} 不该出现：{word}")
            self.assertIn("怎么装", body, p)

    def test_no_title_hard_truncated(self):
        """不能为了塞进字数上限，把标题截成「写清楚」这种半句话。"""
        _, arts = articles()
        for p, a in arts.items():
            self.assertFalse(a["title_fitted"], f"{p} 标题被硬截：{a['title']}")

    def test_wechat_title_within_64_utf8_bytes(self):
        _, arts = articles()
        self.assertLessEqual(
            len(arts["wechat"]["title"].encode("utf-8")), 64
        )
        self.assertLessEqual(
            len(arts["wechat"]["brief"].encode("utf-8")), 120
        )

    def test_all_titles_within_limits(self):
        from src.tones import load_tones
        tones = load_tones()
        _, arts = articles()
        for p, a in arts.items():
            pcfg = tones["platforms"][p]
            if "title_max_bytes" in pcfg:
                self.assertLessEqual(
                    len(a["title"].encode("utf-8")), pcfg["title_max_bytes"], p
                )
            else:
                self.assertLessEqual(len(a["title"]), pcfg["title_max"], p)

    def test_no_machine_tone_in_any_body(self):
        _, arts = articles()
        for p, a in arts.items():
            for word in BANNED:
                self.assertNotIn(word, a["body"], f"{p} 出现机器腔词：{word}")

    def test_deterministic_per_day(self):
        """同一天重跑结果一致，跨天标题会轮换。"""
        cfg = load_yaml(ROOT / "config" / "settings.yaml")
        seo = load_seo()
        a = compose(make_repo(), "2026-11-10", cfg, seo)["articles"]
        b = compose(make_repo(), "2026-11-10", cfg, seo)["articles"]
        self.assertEqual(a, b)

    def test_compose_backward_compatible(self):
        """原有字段一个不少，旧发布器 / 旧测试不受影响。"""
        result, _ = articles()
        for key in ("repo", "date", "title", "titles", "brief", "briefs",
                    "markdown", "html", "tags", "platform_tags", "keywords"):
            self.assertIn(key, result)
        self.assertIn("# agent-desktop", result["markdown"])


if __name__ == "__main__":
    unittest.main()
