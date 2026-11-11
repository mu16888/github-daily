"""新结构渲染：结构原型 + FactPack -> 五平台不同的「判断 / 清单」型稿子。

跟 src/tones.py 的区别（这是本次要修的根因）：
- tones.py 是「项目说明书」结构：解决什么问题 / 这是个什么项目 / 能做什么 /
  安装教程 / 项目档案 / 常见问题。章节顺序跟着 README 走。
- rewrite.py 是「被验证过的高赞结构」：判断或冲突开场 -> 它是什么 ->
  能带走的清单 -> 最小一步 -> 边界 -> 话题标签。章节跟着读者动作走。

红线不变：事实只来自 GitHub REST API 与 README 原文；不新增体验、效果数字、
第一人称经历；不复制原文句子；不调 LLM。
事实源没有安装命令 / 功能列表时，如实改走「从哪看起」，不硬套安装框架、
不拿打分元信号冒充「能带走的清单」。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .discover import Repo
from .hooks import extract_selling_points, selling_point
from .seo import load_seo
from .tones import BANNED, PLATFORMS, _fit, _fit_bytes
from .topics import choose, guard, labels_for, load_topics

# 平台形态差异：只改「取舍 / 详略 / 口吻 / 篇幅」，不改事实。
SHAPES: dict[str, dict[str, Any]] = {
    "zhihu": {
        "sections": ["judgement", "what", "takeaway", "first_step", "boundary", "labels"],
        "code": True, "table": True, "length": [900, 2200],
        "title_max": 50, "title_bytes": False,
        # 10 组句式按 (日期, 平台) 轮换。多数句式带 {selling_point}——
        # 它是运行时从 README 抽出的可核查事实（名词短语），不是万能形容词。
        # 末尾两条是极短兜底：项目名很长时也保证标题不被硬截成半句。
        "titles": [
            "{selling_point}：{name} 值不值得花时间看",
            "{name} 凭什么被收藏 {stars} 次：{selling_point}",
            "{selling_point}，这个 {language} 项目叫 {name}",
            "先别急着装 {name}：{selling_point}",
            "{name} 解决什么麻烦：{selling_point}",
            "关于 {name}，最值得先弄清的是 {selling_point}",
            "{selling_point}，{name} 说明里写了这些",
            "{name}：{selling_point}，再看要不要装",
            "{name} 值不值得装：先看清它管什么",
            "{name} 这类工具，装之前值得先想一件事",
        ],
        # 摘要独立成句，不从导语硬裁，避免公众号被截成半句话
        "brief": "{name} 值不值得花时间，先看它管什么。",
        "lead_suffix": "值不值得花时间，先看它到底管什么。",
        "step_title": "先做哪一步",
        "step_title_alt": "从哪看起",
    },
    "juejin": {
        "sections": ["judgement", "what", "takeaway", "first_step", "labels"],
        "code": True, "table": False, "length": [700, 1600],
        "title_max": 80, "title_bytes": False,
        "titles": [
            "{name} 安装与上手：{selling_point}",
            "{selling_point}，{name} 怎么装怎么跑",
            "{name} 使用笔记：{selling_point}，附现成安装步骤",
            "先跑起来再说：{name} 的 {selling_point}",
            "{name} 怎么用，先看这一点：{selling_point}",
            "{name} 上手：{selling_point}，附安装步骤",
            "{name} 上手：{selling_point}，照着说明走",
            "{name} 能用的几条：{selling_point}",
            "{name} 怎么用：说明里能直接带走的几条",
            "{name} 上手清单：先记这几条就够了",
        ],
        "brief": "{name} 能用的几条，都从说明里挑出来了。",
        "lead_suffix": "说明里给了几条能直接用的。",
        "step_title": "先跑这条",
        "step_title_alt": "从哪看起",
    },
    "csdn": {
        "sections": ["judgement", "what", "first_step", "takeaway", "boundary", "labels"],
        "code": True, "table": True, "length": [900, 2000],
        "title_max": 50, "title_bytes": False,
        "titles": [
            # 「安装教程」「常见问题」是 guardrails.legacy_sections 里的禁用词，
            # 一旦出现在标题会让整份新结构稿被护栏判失败、静默退回旧版，别用。
            "{name} 安装步骤：{selling_point}",
            "{name} 怎么用：{selling_point}，附上手步骤",
            "{name} 功能说明与安装：{selling_point}",
            "{selling_point}，{name} 从安装到第一步",
            "{name} 使用说明：{selling_point}，附安装步骤",
            "{name} 上手教程，先看这一点：{selling_point}",
            "{name} 是什么、怎么装：{selling_point}",
            "{selling_point}：{name} 功能与安装详解",
            "{name} 怎么用：一份能带走的上手清单",
            "{name} 装之前，先看这几条能用的",
        ],
        "brief": "{name} 怎么用，先看能查到的事实。",
        "lead_suffix": "怎么用、从哪一步开始，看仓库里能查到的东西。",
        "step_title": "安装与第一步",
        "step_title_alt": "从哪里入手",
    },
    "wechat": {
        "sections": ["judgement", "what", "takeaway", "first_step", "labels"],
        "code": False, "table": False, "length": [400, 900],
        "title_max_bytes": 64, "title_bytes": True,
        "titles": [
            "{name}：{selling_point}",
            "{selling_point}，值得看一眼",
            "{name} 值不值得装",
            "这个 {language} 工具，先看能用的",
            "{name}，先弄清它管什么",
            "{name} 的 {selling_point}",
            "{name}：先想清楚它管什么",
            "这个开源工具，先别急着装",
            "{name}，值不值得花十分钟",
            "先看 {name} 能给你什么",
        ],
        "brief": "先弄清 {name} 管什么，再决定用不用。",
        "lead_suffix": "今天说个能自己试试的小工具。",
        "step_title": "怎么装",
        "step_title_alt": "怎么用",
    },
    "toutiao": {
        "sections": ["judgement", "what", "takeaway", "first_step"],
        "code": False, "table": False, "length": [300, 700],
        "title_max": 30, "title_bytes": False,
        "titles": [
            "{name}：{selling_point}",
            "{selling_point}，这个工具能干啥",
            "{name} 是干什么的，先说结论",
            "GitHub 上这个工具：{selling_point}",
            "{name}，值不值得花几分钟",
            "{selling_point}，先看懂再装",
            "关于 {name}：{selling_point}",
            "{name}：先弄清它管什么",
            "这个开源项目，先看能带走啥",
            "先看结论：{name} 管什么",
        ],
        "brief": "{name} 是干什么的，先看结论。",
        "lead_suffix": "先给结论，再看怎么弄。",
        "step_title": "怎么装",
        "step_title_alt": "怎么用",
    },
}

# 事实源没有可复制命令时，收尾不能再说「拿一条真实命令试一下」——那是自相矛盾。
NO_INSTALL_CLOSINGS = (
    "这类东西的价值在约定本身，不在装了什么。用之前先把说明读一遍。",
    "项目还在更新，具体怎么用，以仓库说明为准。",
    "说明里没有可复制的命令，先把看得懂的部分用起来就行。",
)


def _headings(readme: str, limit: int = 4) -> list[str]:
    """抽 README 里真实存在的二三级标题；不生成、不改写标题文字。"""
    out: list[str] = []
    for line in (readme or "").splitlines():
        m = re.match(r"^#{2,4}\s+(.+)$", line.strip())
        if not m:
            continue
        t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", m.group(1).strip())
        # 清掉零宽字符 / 变体选择符等格式字符，不动标题文字本身
        t = re.sub(r"[\u200b-\u200f\ufe00-\ufe0f]", "", t)
        t = t.replace("`", "").strip().rstrip("#").strip()
        if t and t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def _facts(repo: Repo) -> dict[str, Any]:
    """唯一事实源：API 字段 + README 原文摘录，不推测、不补全。"""
    return {
        "name": repo.full_name.split("/")[-1],
        "repo": repo.full_name,
        "repo_url": repo.html_url,
        "desc": repo.description or "仓库没填简介",
        "language": repo.language or "未标注",
        "stars": repo.stars,
        "license": repo.license or "未标注",
        "topics": "、".join(repo.topics[:8]) if repo.topics else "没标",
        "created": repo.created_at[:10],
        "pushed": repo.pushed_at[:10],
        "installs": list(repo.install_blocks or []),
        "quickstart": (repo.quickstart_excerpt or "").strip(),
        "features": (repo.features_excerpt or "").strip(),
        "headings": _headings(getattr(repo, "readme", "") or ""),
        "signals": list(repo.signals or []),
        # 运行时从 README 抽出的可核查事实，供标题与「能带走的清单」共用
        "selling_point": selling_point(repo),
        "selling_points": extract_selling_points(repo),
    }


def _list_items(text: str, limit: int = 3) -> list[str]:
    """从 README 原文列表里取前 N 条，不改写内容；去掉链接与行内标记避免死链。"""
    out: list[str] = []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if not m:
            continue
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", m.group(1).strip())
        s = s.replace("`", "").replace("**", "").strip()
        if len(s) > 4 and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


class _RepoProxy:
    """labels_for 只需要 .topics；避免把渲染层跟 Repo 强绑。"""
    def __init__(self, f: dict):
        self.topics = [] if f["topics"] in ("", "没标") else f["topics"].split("、")


def _blocks(f: dict, plan, cfg: dict, shape: dict, topic_zh: dict) -> dict[str, str]:
    plain = not shape["code"]
    proxy = _RepoProxy(f)
    csdn_labels = labels_for(plan, cfg, proxy, "csdn", topic_zh=topic_zh)
    hashtags = labels_for(plan, cfg, proxy, "wechat")["value"]

    what = (
        f"{f['name']} 是 GitHub 上的一个开源项目，用 {f['language']} 写，"
        f"{f['stars']} 人收藏，采用 {f['license']} 协议。"
        "作者自己写的介绍放在项目页面，点进去能看见。"
        if plain else
        f"> {f['desc']}\n\n"
        f"主要用 **{f['language']}** 写，GitHub 上攒了 **{f['stars']}** 颗星（就是收藏数），"
        f"用的是 {f['license']} 协议。仓库地址：[{f['repo']}]({f['repo_url']})。"
    )
    if shape["table"]:
        what += (
            "\n\n| 能查到的 | 值 |\n| --- | --- |\n"
            f"| 仓库 | [{f['repo']}]({f['repo_url']}) |\n"
            f"| 收藏数 | {f['stars']} |\n"
            f"| 主要语言 | {f['language']} |\n"
            f"| 协议 | {f['license']} |\n"
            f"| 建库 / 最近更新 | {f['created']} / {f['pushed']} |"
        )

    # 能带走的清单：只读运行时从 README 抽出的中文可核查信号。
    # 旧版把 README 英文列表原文整段贴进正文，中文导语配英文条目，读起来像机器抓取；
    # 现在一律输出中文短句，原文仍留在 drafts/ 归档里，随时可回查。
    # 绝不用 score() 的打分元信号（「写了说明文档」这类）冒充读者能带走的东西。
    items = list(f.get("selling_points") or [])[:3]
    if not items:
        items = [
            f"主要用 {f['language']} 写",
            f"GitHub 上 {f['stars']} 人收藏",
            f"用的是 {f['license']} 协议",
        ]
    takeaway = "\n".join("- " + s for s in items)

    if f["installs"] and shape["code"]:
        step = (
            "\n\n".join("```\n" + b + "\n```" for b in f["installs"][:2])
            + "\n\n命令是仓库说明里现成的，动手前扫一眼项目页面，作者可能改过版本。"
        )
    elif f["installs"]:
        step = "安装命令写在项目说明里，复制下来跑一遍就行。动手前去项目页面扫一眼，作者可能改过版本。"
    elif f["headings"]:
        # 规范 / 文档类事实源：没有可装的东西，就讲说明本身的组织方式
        step = (
            "项目说明里没给能复制的安装命令，它更像一份要照着写的约定。"
            + (f"说明里分了 {len(f['headings'])} 块，按上面那份清单的顺序看就行。"
               if not plain else "说明里分了几块，去项目页面按顺序看就行。")
        )
    else:
        step = "项目说明里没给能直接复制的安装命令，怎么用得去项目页面看。"

    boundary = (
        f"- {f['license']} 协议，拿去商用或者改了再发，先看条款让不让。\n"
        f"- 建库 {f['created']}，最近更新 {f['pushed']}，项目还在改。\n"
        "- 命令隔段时间可能不一样，用之前翻一眼仓库说明。"
    )
    label_line = (f"话题：{hashtags}\n标签：{csdn_labels['value']}"
                  if hashtags else f"标签：{csdn_labels['value']}")

    return {
        "judgement": plan.opening,
        "what": what,
        "takeaway": takeaway,
        "first_step": step,
        "boundary": boundary,
        "labels": label_line,
    }


SECTION_TITLES = {
    "what": "它是什么",
    "boundary": "边界在哪",
}


def _title(platform: str, shape: dict, f: dict, date: str,
           avoid: set[str] | None = None) -> tuple[str, bool]:
    """按 (date, platform) 确定性轮换；优先选放得下且完整的句式，不硬截半句。

    两点针对「标题没吸引力 / 三篇趋同」：
    1. 含真实信号 {selling_point} 的句式优先轮换，纯兜底句式只在放不下时才用；
    2. 同一天各平台按 salt 取不同的真实信号，避免三篇挂同一个钩子。
    """
    # 用 (日期, 平台) 的确定性散列代替 day % N：后者按天线性递增，
    # 模板数 N=8 时每 8 天整套标题原样复现，正是「每天一个样」的反面。
    digest = hashlib.md5(f"{date}|{platform}".encode("utf-8")).hexdigest()
    # 模板起点与钩子索引必须取散列的不同段：都取低几位时两者完全相关，
    # 组合数从 8×4 塌成 8，会出现连续几天撞同一条标题。
    seed = int(digest[:8], 16)
    point_seed = int(digest[8:16], 16)
    vals = dict(f)
    pts = [p for p in (f.get("selling_points") or []) if p]
    if pts:
        vals["selling_point"] = pts[point_seed % len(pts)]

    pats = shape["titles"]
    core = [p for p in pats if "{selling_point}" in p]
    fallback = [p for p in pats if "{selling_point}" not in p]
    ordered = ([core[(seed + i) % len(core)] for i in range(len(core))]
               if core else []) + fallback
    # 兜底一定放得下，避免长项目名把标题硬截成半句
    ordered.append("{name}")
    bytes_mode = bool(shape.get("title_bytes"))
    limit = int(shape.get("title_max_bytes") or shape.get("title_max", 50))
    for pat in ordered:
        cand = pat.format(**vals)
        if cand in (avoid or set()):   # 同一天别的平台已经用了这句，换下一条
            continue
        size = len(cand.encode("utf-8")) if bytes_mode else len(cand)
        if size <= limit:
            return cand, False
    cand = ordered[0].format(**vals)
    return (_fit_bytes(cand, limit) if bytes_mode else _fit(cand, limit)), True


def _render_one(platform: str, shape: dict, f: dict, plan,
                cfg: dict, date: str, topic_zh: dict,
                avoid: set[str] | None = None) -> dict:
    b = _blocks(f, plan, cfg, shape, topic_zh)
    # 开场 / 收尾按平台轮换，避免五份稿子只有中段不同
    local = choose(date, cfg, salt=platform)
    title, fitted = _title(platform, shape, f, date, avoid=avoid)
    lead = local.opening + shape["lead_suffix"]
    brief = shape["brief"].format(**f)
    brief = _fit_bytes(brief, 120) if shape.get("title_bytes") else _fit(brief, 100)

    step_title = shape["step_title"] if f["installs"] else shape["step_title_alt"]
    parts = [lead]
    for sec in shape["sections"]:
        body = b.get(sec, "").strip()
        if not body or sec == "judgement":  # 开场已写进 lead，不重复起一节
            continue
        if sec == "labels":
            parts.append(body)
            continue
        heading = (step_title if sec == "first_step"
                   else plan.takeaway_title if sec == "takeaway"
                   else SECTION_TITLES.get(sec, sec))
        parts.append(f"## {heading}\n\n{body}")

    day = int(date.replace("-", "")) if date.replace("-", "").isdigit() else 0
    if f["installs"]:
        closing = local.closing
    else:
        closing = NO_INSTALL_CLOSINGS[(day + sum(ord(c) for c in platform))
                                      % len(NO_INSTALL_CLOSINGS)]
    parts.append(closing)
    body = "\n\n".join(parts)

    # 篇幅收敛：只整节删除，不截半句话；至少留开场 + 两节
    _lo, hi = shape["length"]
    if len(body) > hi:
        chunks = body.split("\n\n## ")
        kept = [chunks[0]]
        for chunk in chunks[1:]:
            candidate = "\n\n## ".join(kept + [chunk])
            if len(candidate) <= hi or len(kept) < 2:
                kept.append(chunk)
        body = "\n\n## ".join(kept)

    return {
        "title": title,
        "brief": brief,
        "lead": lead,
        "body": body,
        "chars": len(body),
        "title_fitted": fitted,
        "hook_type": plan.hook_type,
        "tags": labels_for(plan, cfg, _RepoProxy(f), "csdn", topic_zh=topic_zh)["value"],
    }


def render_rewrite(repo: Repo, date: str, seo_cfg: dict | None = None,
                   topics_cfg: dict | None = None) -> dict[str, Any]:
    """返回 {articles: {platform: {...}}, topic: {...}, guard: {...}}。

    纯函数：不写文件、不发请求、不读环境变量，便于测试与本地预览。
    """
    cfg = topics_cfg or load_topics()
    topic_zh = (seo_cfg or load_seo()).get("topic_zh", {})
    plan = choose(date, cfg)
    f = _facts(repo)
    articles = {}
    used: set[str] = set()
    for platform in PLATFORMS:
        shape = SHAPES.get(platform)
        if shape:
            art = _render_one(platform, shape, f, plan, cfg, date, topic_zh,
                              avoid=used)
            articles[platform] = art
            used.add(art["title"])

    # 兜底：任何一个渲染器写错，也不能把禁用词或旧说明书节标题放出去
    banned_all = tuple(BANNED) + tuple((cfg.get("guardrails") or {}).get("legacy_sections", ()))
    for p, art in articles.items():
        for word in banned_all:
            if word in art["body"] or word in art["title"]:
                raise ValueError(f"{p} 稿出现禁用内容：{word}")

    return {
        "articles": articles,
        "topic": plan.as_dict(),
        "guard": guard(cfg, {p: a["body"] for p, a in articles.items()}),
    }
