import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestTracks(unittest.TestCase):
    """赛道划分（2026-11-10 锋哥定）：
    赛道 A 技术/AI → CSDN、知乎、掘金
    赛道 B 餐饮 + 餐饮AI → 头条、公众号、微博、百家号
    """

    def _cfg(self):
        from src.main import load_yaml
        return load_yaml(ROOT / "config" / "tracks.yaml")

    def test_two_tracks_defined(self):
        t = self._cfg()
        self.assertIn("tech", t["tracks"])
        self.assertIn("restaurant", t["tracks"])

    def test_platform_assignment_matches_fengge_decision(self):
        """平台归属必须严格按锋哥定的来，不能错位。"""
        t = self._cfg()["tracks"]
        self.assertEqual(sorted(t["tech"]["platforms"]), ["csdn", "juejin", "zhihu"])
        self.assertEqual(sorted(t["restaurant"]["platforms"]),
                         ["baijiahao", "toutiao", "wechat", "weibo"])

    def test_tracks_do_not_overlap(self):
        """两个赛道的平台不能重叠（否则内容会串）。"""
        t = self._cfg()["tracks"]
        a = set(t["tech"]["platforms"])
        b = set(t["restaurant"]["platforms"])
        self.assertEqual(a & b, set(), f"平台同时属于两个赛道: {a & b}")

    def test_manual_only_platforms_have_reason(self):
        """微博/百家号/公众号是「人工发」，必须写清原因和产出方式。"""
        t = self._cfg()
        for name in ("weibo", "baijiahao", "wechat"):
            self.assertIn(name, t["manual_only"])
            self.assertTrue(t["manual_only"][name].get("reason"))
            self.assertTrue(t["manual_only"][name].get("output"))

    def test_local_yaml_platform_track_fields(self):
        """local.yaml 里每个平台都要声明 track，且要跟 tracks.yaml 对得上。"""
        from src.local import local_cfg
        lcfg = local_cfg()
        tcfg = self._cfg()["tracks"]      # tracks.yaml 顶层就有 tracks 段
        valid = {p for t in tcfg.values() for p in t["platforms"]}
        for name, pc in (lcfg.get("platforms") or {}).items():
            self.assertIn(name, valid, f"{name} 不在任何赛道里")
            self.assertIn(pc.get("track"), ("tech", "restaurant"),
                          f"{name} 的 track 字段不合法")

    def test_local_cfg_merges_tracks(self):
        """local_cfg() 要把 tracks.yaml 合并进来。"""
        from src.local import local_cfg
        cfg = local_cfg()
        self.assertIn("tracks", cfg)
        self.assertIn("tech", cfg["tracks"]["tracks"])
        self.assertIn("restaurant", cfg["tracks"]["tracks"])

    def test_github_daily_only_in_tech_track(self):
        """GitHub 开源项目稿只属于赛道 A。"""
        t = self._cfg()["tracks"]
        self.assertTrue(t["tech"]["include_github_daily"])
        self.assertFalse(t["restaurant"]["include_github_daily"])


class TestBlogSource(unittest.TestCase):
    """赛道 B 的内容源：沐风博客的餐饮线。"""

    def test_load_restaurant_posts_finds_drafts(self):
        from src.blog_source import load_restaurant_posts
        posts = load_restaurant_posts(["餐饮经营"])
        self.assertGreater(len(posts), 0, "读不到餐饮线文章")
        for p in posts:
            self.assertIn("餐饮经营", p["tags"])
            self.assertTrue(p["body"].strip())

    def test_tags_are_unquoted(self):
        """tags 解析要剥掉引号，否则 ['\"餐饮经营\"'] 匹配不上。"""
        from src.blog_source import _tags_of
        self.assertEqual(_tags_of({"tags": '["餐饮经营", "菜单"]'}), ["餐饮经营", "菜单"])

    def test_to_article_fills_platform_titles(self):
        from src.blog_source import to_article
        post = {"slug": "x", "title": "原标题", "body": "正文",
                "wechat_title": "短标题", "wechat_digest": "摘要",
                "description": "描述", "tags": ["餐饮经营"]}
        art = to_article(post, ["wechat", "toutiao"])
        self.assertEqual(art["titles"]["wechat"], "短标题")
        self.assertEqual(art["titles"]["toutiao"], "短标题")
        self.assertEqual(art["briefs"]["toutiao"], "摘要")
        self.assertEqual(art["markdown"], "正文")


if __name__ == "__main__":
    unittest.main()
