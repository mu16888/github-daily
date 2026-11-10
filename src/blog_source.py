"""赛道 B 的内容源：从沐风博客取「餐饮经营」线的文章。

背景（2026-11-10 锋哥定的赛道划分）：
    赛道 A「技术/AI 效率」  → CSDN / 知乎 / 掘金
    赛道 B「餐饮经营 + 餐饮 AI」→ 头条 / 公众号 / 微博 / 百家号

赛道 A 的内容由 github-daily 产出（GitHub 开源项目介绍），
赛道 B 的内容来自沐风博客 content/posts/ 里餐饮线（tags 含「餐饮经营」）
的成稿 —— 那些文章本来就已经写好了，只是 draft: true 没发。

本模块只做「取稿 → 转成平台可发格式」，不负责发布。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

BLOG_ROOT = Path(r"E:\workbuddy工作台\沐风博客")
POSTS_DIR = BLOG_ROOT / "content" / "posts"


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm: dict[str, str] = {}
    for line in parts[1].splitlines():
        m = re.match(r"^([A-Za-z_][\w\-]*):\s*(.*)$", line.strip())
        if m:
            v = m.group(2).strip()
            if v.startswith(('"', "'")) and v.endswith(('"', "'")):
                v = v[1:-1]
            fm[m.group(1)] = v
    return fm


def _tags_of(fm: dict[str, str]) -> list[str]:
    raw = fm.get("tags", "") or ""
    raw = raw.replace("[", "").replace("]", "")
    out = []
    for t in raw.split(","):
        t = t.strip().strip('"').strip("'").strip()
        if t:
            out.append(t)
    return out


def load_restaurant_posts(track_tags: list[str] | None = None,
                          only_draft: bool = True) -> list[dict[str, Any]]:
    """取餐饮线文章。

    only_draft=True 时只取 draft: true 的（还没发过的），
    False 时取全部（补发用）。
    """
    track_tags = track_tags or ["餐饮经营"]
    out: list[dict[str, Any]] = []
    if not POSTS_DIR.exists():
        return out
    for p in sorted(POSTS_DIR.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = _frontmatter(text)
        if not fm:
            continue
        tags = _tags_of(fm)
        if not any(t in tags for t in track_tags):
            continue
        is_draft = (fm.get("draft", "false").strip().lower() == "true")
        if only_draft and not is_draft:
            continue
        parts = text.split("---", 2)
        body = parts[2] if len(parts) >= 3 else text
        out.append({
            "slug": p.stem,
            "title": fm.get("title", ""),
            "date": fm.get("date", ""),
            "draft": is_draft,
            "tags": tags,
            "description": fm.get("description", ""),
            "wechat_title": fm.get("wechat_title", ""),
            "wechat_digest": fm.get("wechat_digest", ""),
            "image": fm.get("image", ""),
            "body": body.strip(),
            "path": str(p),
        })
    return out


def to_article(post: dict[str, Any], platforms: list[str]) -> dict[str, Any]:
    """把一篇博客文章转成流水线用的 article 结构。"""
    md = post["body"]
    titles = {}
    briefs = {}
    for plat in platforms:
        t = post.get("wechat_title") or post.get("title", "")
        titles[plat] = t
        briefs[plat] = post.get("wechat_digest") or post.get("description", "")
    return {
        "repo": f"blog/{post['slug']}",
        "title": post.get("title", ""),
        "markdown": md,
        "titles": titles,
        "briefs": briefs,
        "keywords": post.get("tags", []),
        "platform_tags": {p: "、".join(post.get("tags", [])) for p in platforms},
        "tags": "、".join(post.get("tags", [])),
        "blog_slug": post["slug"],
        "blog_image": post.get("image", ""),
    }


def pick_for_track(track_cfg: dict, platforms: list[str],
                    limit: int = 1, only_draft: bool = True) -> list[dict[str, Any]]:
    """按赛道配置挑内容。"""
    posts = load_restaurant_posts(track_cfg.get("blog_tags"), only_draft=only_draft)
    return [to_article(p, platforms) for p in posts[:limit]]
