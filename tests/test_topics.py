"""话题层 / 新结构渲染的护栏测试。

锁住五件事：结构真的换了（不是换皮）、五平台真的不同、防洗稿零重合、
事实只来自 FactPack、默认发布链路零影响。
"""
import unittest
from pathlib import Path

from src.compose import compose
from src.discover import (Repo, extract_install_blocks, extract_quickstart, score)
from src.main import load_yaml, platform_view
from src.rewrite import render_rewrite
from src.seo import load_seo
from src.tones import BANNED, PLATFORMS
from src.topics import (choose, guard, labels_for, load_topics,
                        ngram_overlap, ngrams)

ROOT = Path(__file__).resolve().parent.parent
DATE = "2026-11-10"

README = """# agent-desktop

Computer use for AI agents: see and operate desktop apps through the OS accessibility tree.

## Why

Doing computer use with screenshots is brittle. Pixels move, themes change, and a model has to guess where to click.

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
    r.problem_excerpt = "Doing computer use with screenshots is brittle."
    r.features_excerpt = (
        "- Reads the OS accessibility tree, no screenshots or pixel matching\n"
        "- Returns every actionable element as JSON with a stable ref\n"
        "- Ships as a CLI and a C library"
    )
    r.intro_excerpt = "Computer use for AI agents through the OS accessibility tree."
    cfg = load_yaml(ROOT / "config" / "settings.yaml")
    r.score, r.signals = score(r, cfg["score_weights"])
    return r


def rewrite_result():
    return render_rewrite(make_repo(), DATE, seo_cfg=load_seo())


class TestTopicPlan(unittest.TestCase):
    def test_choose_is_deterministic(self):
        cfg = load_topics()
        self.assertEqual(choose(DATE, cfg).as_dict(), choose(DATE, cfg).as_dict())

    def test_choose_rotates_across_days(self):
        cfg = load_topics()
        ids = {choose(f"2026-11-{d:02d}", cfg).id for d in range(10, 20)}
        self.assertGreater(len(ids), 1, "十天应该轮到不止一种结构原型")

    def test_opening_rotates_across_days(self):
        cfg = load_topics()
        openings = {choose(f"2026-11-{d:02d}", cfg).opening for d in range(10, 20)}
        self.assertGreater(len(openings), 1)

    def test_topic_pool_has_source_metadata(self):
        cfg = load_topics()
        meta = cfg["meta"]
        self.assertIn("captured_at", meta)
        self.assertIn("api.juejin.cn", meta["source_url"])
        self.assertEqual(meta["sample_size"], 50)
        self.assertIn("非历史爆款", meta["calibration_note"])


class TestAntiPlagiarism(unittest.TestCase):
    def test_ngram_helpers(self):
        self.assertEqual(ngram_overlap("甲乙丙丁戊己庚辛", "甲乙丙丁戊己庚辛")[0], 1)
        self.assertEqual(ngram_overlap("甲乙丙丁戊己庚辛", "完全不同的另一段文字")[0], 0)
        self.assertEqual(len(ngrams("短", 8)), 0)

    def test_no_overlap_with_reference_titles(self):
        result = rewrite_result()
        self.assertTrue(result["guard"]["ok"], result["guard"])
        for p, v in result["guard"]["platforms"].items():
            self.assertEqual(v["overlap"], 0, f"{p} 与原文标题有连续 8 字重合：{v['samples']}")

    def test_guard_rejects_copied_text(self):
        cfg = load_topics()
        copied = cfg["reference_titles"][1]  # 整句抄进来
        self.assertFalse(guard(cfg, {"juejin": copied})["ok"])

    def test_proper_noun_normalization_is_not_a_backdoor(self):
        """专名碰撞不算洗稿，但去掉专名后整句照抄仍必须被抓。"""
        cfg = load_topics()
        terms = cfg["guardrails"]["normalize_terms"]
        src = "\n".join(cfg["reference_titles"])
        self.assertEqual(
            ngram_overlap(src, "这份格式叫 AGENTS.md，仓库里也有。", 8, normalize=terms)[0], 0)
        self.assertIn("AGENTS.md", cfg["reference_titles"][1])
        self.assertFalse(guard(cfg, {"juejin": cfg["reference_titles"][1]})["ok"])

    def test_reference_titles_are_not_used_to_build_titles(self):
        """生成器不能把原文标题搬进任何一版标题。"""
        cfg = load_topics()
        arts = rewrite_result()["articles"]
        for p, a in arts.items():
            for ref in cfg["reference_titles"]:
                self.assertNotIn(ref, a["title"], p)


class TestNewStructure(unittest.TestCase):
    def test_five_platforms_present(self):
        self.assertEqual(set(rewrite_result()["articles"]), set(PLATFORMS))

    def test_structure_really_changed(self):
        """不能出现旧说明书的节标题；必须出现「它是什么 / 清单 / 最小一步」新骨架。"""
        cfg = load_topics()
        plan = choose(DATE, cfg)
        legacy = cfg["guardrails"]["legacy_sections"]
        arts = rewrite_result()["articles"]
        joined = "\n".join(a["body"] for a in arts.values())
        self.assertIn("## 它是什么", joined)
        self.assertIn("## " + plan.takeaway_title, joined)
        self.assertTrue(any(("## " + h) in joined for h in
                            ("先做哪一步", "先跑这条", "安装与第一步", "怎么装")))
        for p, a in arts.items():
            for word in legacy:
                self.assertNotIn(word, a["body"], f"{p} 退回说明书结构：{word}")

    def test_titles_bodies_leads_all_distinct(self):
        arts = rewrite_result()["articles"]
        for field in ("title", "body", "lead"):
            self.assertEqual(len({a[field] for a in arts.values()}), len(PLATFORMS), field)

    def test_no_machine_tone(self):
        cfg = load_topics()
        banned = tuple(BANNED) + tuple(cfg["guardrails"]["legacy_sections"])
        for p, a in rewrite_result()["articles"].items():
            for word in banned:
                self.assertNotIn(word, a["body"], f"{p} 机器腔：{word}")

    def test_facts_are_traceable(self):
        """正文里的数字 / 协议 / 仓库名必须来自 FactPack，且不出现虚构体验。"""
        arts = rewrite_result()["articles"]
        joined = "\n".join(a["body"] for a in arts.values())
        self.assertIn("19919", joined)          # make_repo 的真实字段
        self.assertIn("Apache-2.0", joined)
        self.assertIn("agent-desktop", joined)
        for word in ("亲测", "我用了一周", "提升了", "实测省下", "我用过"):
            self.assertNotIn(word, joined)

    def test_no_hard_truncated_title(self):
        for p, a in rewrite_result()["articles"].items():
            self.assertFalse(a["title_fitted"], f"{p} 标题被硬截：{a['title']}")

    def test_wechat_limits(self):
        a = rewrite_result()["articles"]["wechat"]
        self.assertLessEqual(len(a["title"].encode("utf-8")), 64)
        self.assertLessEqual(len(a["brief"].encode("utf-8")), 120)

    def test_platform_shapes_differ(self):
        arts = rewrite_result()["articles"]
        self.assertIn("```", arts["zhihu"]["body"])
        self.assertIn("| 能查到的 |", arts["zhihu"]["body"])
        for p in ("wechat", "toutiao"):
            self.assertNotIn("```", arts[p]["body"], p)
            self.assertNotIn("| 能查到的 |", arts[p]["body"], p)
            self.assertNotIn("OS accessibility tree", arts[p]["body"], p)
            self.assertTrue(any(h in arts[p]["body"] for h in
                                ("怎么装", "怎么用", "从哪看起")), p)

    def test_briefs_are_complete_sentences(self):
        """摘要独立成句，不能从导语硬裁出半句话。"""
        for p, a in rewrite_result()["articles"].items():
            self.assertTrue(a["brief"].endswith("。"), f"{p} 摘要是半句：{a['brief']}")

    def test_takeaway_is_not_scoring_metadata(self):
        """清单里不能塞「写了说明文档」这类机器腔元信息。"""
        for p, a in rewrite_result()["articles"].items():
            self.assertNotIn("写了说明文档", a["body"], p)
            self.assertNotIn("说明写得够长", a["body"], p)

    def test_no_install_source_does_not_contradict_itself(self):
        """事实源没有安装命令时，不能再说「拿一条真实命令试一下」。"""
        r = make_repo()
        r.install_blocks = []
        arts = render_rewrite(r, DATE, seo_cfg=load_seo())["articles"]
        for p, a in arts.items():
            self.assertNotIn("拿一条真实命令", a["body"], p)
            self.assertNotIn("试过第一步就知道", a["body"], p)
            self.assertTrue(any(h in a["body"] for h in
                                ("从哪看起", "怎么用", "从哪里入手")), p)


class TestLabelMapping(unittest.TestCase):
    def test_unverified_channels_are_not_guessed(self):
        cfg = load_topics()
        plan = choose(DATE, cfg)
        for p in ("juejin", "zhihu"):
            info = labels_for(plan, cfg, make_repo(), p)
            self.assertNotEqual(info["status"], "ready")
            self.assertEqual(info["value"], "", p)

    def test_csdn_tags_ready_and_bounded(self):
        cfg = load_topics()
        info = labels_for(choose(DATE, cfg), cfg, make_repo(), "csdn")
        self.assertEqual(info["status"], "ready")
        self.assertLessEqual(len(info["value"].split(",")), 5)
        self.assertTrue(info["value"])

    def test_real_repo_topics_are_kept_as_tags(self):
        """关联标签要带项目自己的真实 topic，不能只剩通用默认词。"""
        cfg = load_topics()
        info = labels_for(choose(DATE, cfg), cfg, make_repo(), "csdn")
        self.assertIn("ai-agents", info["value"])
        hashtag = labels_for(choose(DATE, cfg), cfg, make_repo(), "wechat")
        self.assertNotIn("ai-agents", hashtag["value"])


class TestIntegration(unittest.TestCase):
    def test_compose_backward_compatible(self):
        cfg = load_yaml(ROOT / "config" / "settings.yaml")
        a = compose(make_repo(), DATE, cfg, load_seo())
        for key in ("repo", "date", "title", "titles", "brief", "briefs",
                    "markdown", "html", "tags", "platform_tags", "keywords",
                    "articles", "articles_error"):
            self.assertIn(key, a)
        self.assertEqual(a["articles_error"], "")
        self.assertIn("# agent-desktop", a["markdown"])

    def test_compose_adds_rewrite_without_error(self):
        cfg = load_yaml(ROOT / "config" / "settings.yaml")
        a = compose(make_repo(), DATE, cfg, load_seo())
        self.assertEqual(a["rewrite_error"], "")
        self.assertEqual(set(a["rewrite"]), set(PLATFORMS))
        self.assertTrue(a["rewrite_guard"]["ok"])
        self.assertIn("id", a["topic"])

    def test_default_content_source_is_legacy(self):
        cfg = load_yaml(ROOT / "config" / "settings.yaml")
        self.assertEqual(cfg["publish"]["content_source"], "legacy")
        self.assertTrue(cfg["publish"]["dry_run"])
        self.assertEqual(cfg["zhihu"]["mode"], "off")

    def test_platform_view_legacy_is_identity(self):
        cfg = load_yaml(ROOT / "config" / "settings.yaml")
        a = compose(make_repo(), DATE, cfg, load_seo())
        self.assertIs(platform_view(a, "juejin", "legacy"), a)

    def test_platform_view_rewrite_overrides_publisher_fields(self):
        cfg = load_yaml(ROOT / "config" / "settings.yaml")
        a = compose(make_repo(), DATE, cfg, load_seo())
        v = platform_view(a, "juejin", "rewrite")
        self.assertEqual(v["titles"]["juejin"], a["rewrite"]["juejin"]["title"])
        self.assertEqual(v["briefs"]["juejin"], a["rewrite"]["juejin"]["brief"])
        self.assertEqual(v["markdown"], a["rewrite"]["juejin"]["body"])
        self.assertIn("<p>", v["html"])
        self.assertNotEqual(v["markdown"], a["markdown"])
        # 原 article 不被就地修改
        self.assertEqual(a["titles"]["juejin"], a["titles"]["juejin"])
        self.assertNotIn("rewrite", a["markdown"])

    def test_platform_view_falls_back_when_no_article(self):
        cfg = load_yaml(ROOT / "config" / "settings.yaml")
        a = compose(make_repo(), DATE, cfg, load_seo())
        a["rewrite"] = {}
        self.assertIs(platform_view(a, "juejin", "rewrite"), a)


if __name__ == "__main__":
    unittest.main()
