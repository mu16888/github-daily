"""五平台调性渲染：一个 FactPack -> 五份不同的标题 / 导语 / 正文。

设计要点：
- 唯一事实源是 FactPack（README 原文 + GitHub REST API 字段）。
  差异只允许来自 切入点 / 结构顺序 / 信息取舍 / 句式 / 口吻 / 篇幅，
  不允许新增事实、体验、效果数字或第一人称经历。
- 完全独立于发布链路：compose() 只是多返回一个 articles 字段，
  原有 markdown / titles / briefs 一个字不改，旧发布器与旧测试不受影响。
- 标题按 (date, platform, salt) 确定性轮换，同一天各平台走各自的变体，
  不会像旧版那样所有平台共用一个索引。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .discover import Repo
from .seo import _hook, load_seo

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS = ("zhihu", "juejin", "csdn", "wechat", "toutiao")


def load_tones() -> dict:
    return yaml.safe_load((ROOT / "config" / "tones.yaml").read_text(encoding="utf-8")) or {}


# 去 AI 味护栏：这些词一旦出现在任何一版正文里，测试会直接挂。
BANNED = (
    "本文由程序", "自动生成并发布", "GitHub Actions", "未检出", "不编造",
    "逐字摘自", "请以项目仓库为准", "仅供参考", "综合得分", "门槛 ",
    "采集脚本", "/search/repositories", "本文先讲", "下面按顺序",
    "下面按", "这篇把", "往下看", "能确认的有这些", "都写清楚",
)


def _fit(text: str, limit: int) -> str:
    """按字符裁短，优先丢尾部短语，不截出半句话。"""
    if len(text) <= limit:
        return text
    for sep in ("｜", "，", "（", "、"):
        while sep in text and len(text) > limit:
            text = text.rsplit(sep, 1)[0]
    return text[:limit].rstrip("，、｜（ ")


def _fit_bytes(text: str, limit: int) -> str:
    """公众号标题按 UTF-8 字节算；中文 1 字 3 字节。

    超限时优先按标点丢掉整个尾部短语，不硬截出「写清楚」这种半句话。
    """
    if len(text.encode("utf-8")) <= limit:
        return text
    for sep in ("，", "。", "｜", "（", "、"):
        while sep in text and len(text.encode("utf-8")) > limit:
            text = text.rsplit(sep, 1)[0]
    text = text.rstrip("，。、｜（ ")
    if len(text.encode("utf-8")) <= limit:
        return text
    out = ""
    for ch in text:
        if len((out + ch).encode("utf-8")) > limit:
            break
        out += ch
    return out.rstrip("，。、｜（ ")


def _factpack(repo: Repo, date: str, seo_result: dict, seo_cfg: dict) -> dict[str, Any]:
    """把 README + API 字段收成一个事实包。所有渲染器只读这里。"""
    name = repo.full_name.split("/")[-1]
    desc = repo.description or "仓库没填简介"
    desc_lead = desc.strip()[:60].rstrip(".。!！?？;；")
    topic_map = seo_cfg.get("topic_zh", {})
    topics_zh = "、".join(
        topic_map[t.lower()] for t in repo.topics if t.lower() in topic_map
    )[:40] or "开源工具"
    return {
        "name": name,
        "repo": repo.full_name,
        "repo_url": repo.html_url,
        "desc": desc,
        "desc_lead": desc_lead,
        "language": repo.language or "开源项目",
        "stars": repo.stars,
        "license": repo.license or "未标注",
        "topics": "、".join(repo.topics[:8]) if repo.topics else "没标",
        "topics_zh": topics_zh,
        "hook": _hook(repo, seo_cfg),
        "date": date,
        "created": repo.created_at[:10],
        "pushed": repo.pushed_at[:10],
        "captured": repo.facts().get("captured_at", date),
        "problem": (repo.problem_excerpt or "").strip(),
        "features": (repo.features_excerpt or "").strip(),
        "intro": (repo.intro_excerpt or "").strip(),
        "installs": list(repo.install_blocks or []),
        "quickstart": (repo.quickstart_excerpt or "").strip(),
        "signals": list(repo.signals or []),
        "faq": list(seo_result.get("faq", [])),
    }


def _blocks(f: dict) -> dict[str, str]:
    """内容块。每块只陈述 FactPack 里存在的事实，缺什么就少写什么。"""
    plain = not f["installs"]
    install_txt = (
        "\n\n".join("```\n" + b + "\n```" for b in f["installs"])
        if f["installs"] else ""
    )
    quick = _dedup_quick(f["quickstart"], f["installs"])

    problem = (
        f["problem"] or (f["intro"] or f["desc"])
    )
    problem_plain = (
        f"项目在 GitHub 上挂的标签是 {f['topics_zh']}，大致能看出它跟哪类活儿有关。"
        + (
            "作者还在说明里专门写了做这个的缘由，想看原话可以去项目页面翻。"
            if f["problem"] else
            "说明里没单独写为什么做这个，能依据的就是这句介绍和这些标签。"
        )
    )

    features = (
        f["features"] or
        f"- 作者原话：{f['desc']}\n- 主要用 {f['language']} 写\n- 标签有 {f['topics']}"
    )
    # 非技术读者不塞英文原文，改用 score() 已产出的中文白话信号（全部来自 README 实测）
    signal_lines = "\n".join("- " + s for s in f["signals"])
    features_plain = (
        "第一次用会不会卡住，说明里能查到的是这些。\n\n" + signal_lines
        if signal_lines else
        f"能确认的是：主要用 {f['language']} 写，标签是 {f['topics_zh']}。"
    )
    if f["installs"] and not signal_lines:
        features_plain += "\n\n说明里给了能直接复制的安装命令，不用自己把源码做成软件。"

    signals = (
        "\n".join("- " + s for s in f["signals"])
        or "- 说明文档里能看的东西不多"
    )

    archive = (
        "| 项目 | 内容 |\n| --- | --- |\n"
        f"| 仓库 | [{f['repo']}]({f['repo_url']}) |\n"
        f"| 收藏数 | {f['stars']} |\n"
        f"| 主要用什么写 | {f['language']} |\n"
        f"| 开源协议 | {f['license']} |\n"
        f"| 标签 | {f['topics']} |\n"
        f"| 创建时间 | {f['created']} |\n"
        f"| 最近更新 | {f['pushed']} |"
    )

    faq = "\n".join(
        f"**{item['q']}**\n\n{item['a']}\n" for item in f["faq"]
    )

    caveat = (
        f"- 项目还在改，命令隔段时间可能就不一样了。\n"
        f"- {f['license']} 协议。拿去商用或者改了再发，先看条款让不让。"
    )

    return {
        "problem": problem,
        "problem_plain": problem_plain,
        "what": (
            f"> {f['desc']}\n\n"
            f"主要用 **{f['language']}** 写，GitHub 上攒了 **{f['stars']}** 颗星（就是收藏数），"
            f"用的是 {f['license']} 协议。协议管的是你能不能拿去商用、改了要不要公开。"
            f"仓库地址：[{f['repo']}]({f['repo_url']})。"
        ),
        "what_plain": (
            f"{f['name']} 是 GitHub 上的一个开源项目，用 {f['language']} 写，"
            f"{f['stars']} 人收藏，采用 {f['license']} 协议。"
            f"在 GitHub 搜项目名就能找到。"
        ),
        "features": features,
        "features_plain": features_plain,
        "signals": signals,
        "install": (
            (install_txt + "\n\n装不上先别急着重试。看看说明是不是改过命令，"
             "再看电脑上装没装它要的环境、版本对不对。")
            if not plain else
            "仓库说明里没给能直接复制的安装命令，怎么装得去仓库页面看。"
        ),
        "install_plain": (
            "安装命令写在项目说明的 Install 段落里，复制下来跑一遍就行。"
            "动手前去项目页面扫一眼，作者可能改过版本。"
            if f["installs"] else
            "项目说明里没给能直接复制的安装命令，怎么装得去项目页面看。"
        ),
        "usage": (
            (quick + "\n\n这些是说明里 Quick Start（快速上手）部分的原样内容。")
            if quick else
            "说明里没写上手步骤，具体怎么用还得去仓库页面翻。"
        ),
        "usage_plain": (
            "装完之后按项目说明里的 Quick Start（快速上手）走一遍就行。"
            if quick else
            "项目说明里没写单独的上手步骤，用法得去项目页面看。"
        ),
        "archive": archive,
        "caveat": caveat,
        "faq": faq,
    }


def _dedup_quick(quick: str, installs: list[str]) -> str:
    """Quick Start 里跟安装节重复的命令不重复贴。"""
    if not quick:
        return ""
    def repl(m: re.Match) -> str:
        return "（这条命令上面贴过了，不重复。）" if m.group(1) in installs else m.group(0)
    out = re.sub(r"```[^\n]*\n(.*?)```", repl, quick, flags=re.S)
    return out.replace("（这条命令上面贴过了，不重复。）", "").strip()


def _render_one(platform: str, tone: dict, defaults: dict, f: dict, date: str) -> dict:
    pcfg = tone["platforms"][platform]
    keep = set(pcfg.get("keep", []))
    titles = {**defaults.get("section_titles", {}), **pcfg.get("section_titles", {})}
    intros = {**defaults.get("section_intros", {}), **pcfg.get("section_intros", {})}
    b = _blocks(f)
    plain = "code" not in keep

    # 无代码块的平台用白话块，避免把英文原文和命令行塞给非技术读者
    override = {
        "problem": "problem_plain" if plain else "problem",
        "what": "what_plain" if plain else "what",
        "features": "features_plain" if plain else "features",
        "install": "install_plain" if plain else "install",
        "usage": "usage_plain" if plain else "usage",
    }

    vals = dict(f)
    vals["topics_zh"] = f["topics_zh"]

    # 标题：按 (date, platform, salt) 确定性轮换，各平台独立。
    # 优先选一条「放得下且完整」的句式，而不是选一条再硬截成半句话。
    salt = sum(ord(ch) for ch in platform)
    seed = int(date.replace("-", "") or 0) + salt
    patterns = pcfg.get("title_patterns") or ["{name}：{hook}"]
    ordered = [patterns[(seed + i) % len(patterns)] for i in range(len(patterns))]
    bytes_mode = "title_max_bytes" in pcfg
    limit = int(pcfg.get("title_max_bytes") or pcfg.get("title_max", 50))

    title, title_fitted = None, False
    for pat in ordered:
        cand = pat.format(**vals)
        size = len(cand.encode("utf-8")) if bytes_mode else len(cand)
        if size <= limit:
            title = cand
            break
    if title is None:
        cand = ordered[0].format(**vals)
        title = _fit_bytes(cand, limit) if bytes_mode else _fit(cand, limit)
        title_fitted = True

    lead = pcfg.get("lead_template", "{name}，{hook}。").format(**vals)
    brief = _fit(lead.replace("**", ""), 120)
    if "brief_max_bytes" in pcfg:
        brief = _fit_bytes(brief, int(pcfg["brief_max_bytes"]))

    parts = [lead]
    for sec in pcfg.get("section_order", []):
        key = override.get(sec, sec)
        body = b.get(key, "").strip()
        if not body:
            continue
        if sec == "archive" and "table" not in keep:
            continue
        if sec == "faq" and "faq" not in keep:
            continue
        if sec == "signals" and "signals" not in keep:
            continue
        intro = (intros.get(sec) or "").strip()
        parts.append(
            f"## {titles.get(sec, sec)}\n\n" + (intro + "\n\n" if intro else "") + body
        )

    parts.append(pcfg.get("ending", "{name} 还在改，以仓库说明为准。").format(**vals))
    body = "\n\n".join(parts)

    # 篇幅收敛：只整节删除，不截半句话；至少留前两节
    lo, hi = pcfg.get("length_hint", [0, 100000])
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
        "length_hint": [lo, hi],
        "title_fitted": title_fitted,
    }


def render_all(repo: Repo, date: str, seo_result: dict,
               seo_cfg: dict | None = None, tones: dict | None = None) -> dict[str, dict]:
    """返回 {platform: {title, brief, lead, body, chars, length_hint}}。"""
    seo_cfg = seo_cfg or load_seo()
    tones = tones or load_tones()
    f = _factpack(repo, date, seo_result, seo_cfg)
    defaults = tones.get("defaults", {})
    out = {}
    for platform in PLATFORMS:
        if platform not in tones.get("platforms", {}):
            continue
        out[platform] = _render_one(platform, tones, defaults, f, date)
    return out
