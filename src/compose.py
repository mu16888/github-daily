"""把结构化事实拼成中文介绍文章，并产出 Markdown / HTML 两种正文。

不调用 LLM：GitHub Models 已于 2026-07-30 退役，云端没有官方免费推理。
结构化模板的好处是——安装命令、star 数、许可证全部来自 API 与 README 原文，
没有生成式改写，也就不存在「编造一个看起来能用的命令」的风险。
"""
from __future__ import annotations

import html as _html
import re
from typing import Any

from .discover import Repo, _drop_trailing_fragment
from .seo import build as seo_build, load_seo


def md_to_html(md: str) -> str:
    """够用的 Markdown→HTML：标题、段落、代码块、列表、引用、表格、行内标记。

    知乎 content.html 与 CSDN content 都要求 HTML，这里自带转换，避免多一个依赖。
    """
    def inline(s: str) -> str:
        s = _html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
        return s

    lines = md.splitlines()
    out: list[str] = []
    para: list[str] = []
    items: list[str] = []
    i = 0

    def flush_para() -> None:
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para.clear()

    def flush_items() -> None:
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            items.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_para(); flush_items()
            lang = stripped[3:].strip()
            buf: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            cls = f' class="language-{_html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>" + _html.escape("\n".join(buf)) + "</code></pre>")
            i += 1
            continue

        # 表格：| a | b |  +  |---|---|
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            flush_para(); flush_items()
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            thead = "".join(f"<th>{inline(c)}</th>" for c in header)
            tbody = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para(); flush_items()
            lvl = min(len(m.group(1)), 6)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        m = re.match(r"^[-*]\s+(.*)$", stripped)
        if m:
            flush_para()
            items.append(m.group(1)); i += 1
            continue

        if stripped.startswith("> "):
            flush_para(); flush_items()
            out.append(f"<blockquote><p>{inline(stripped[2:])}</p></blockquote>")
            i += 1
            continue

        if not stripped:
            flush_para(); flush_items()
        else:
            flush_items()
            para.append(stripped)
        i += 1

    flush_para(); flush_items()
    return "\n".join(out)


def _quote(text: str, limit: int = 1200) -> str:
    """把原文按行转成引用块；截断时丢掉末尾残句，不做任何改写。"""
    cleaned = _drop_trailing_fragment(text[:limit])
    lines = [l.rstrip() for l in cleaned.splitlines() if l.strip()][:8]
    return "\n".join("> " + l for l in lines)


def _dedup_quickstart(quick: str, install_blocks: list[str]) -> str:
    """Quick Start 里常贴着和安装章节一模一样的命令块，避免同一段代码出现两次。"""
    if not quick or not install_blocks:
        return quick

    def repl(m: re.Match) -> str:
        body = m.group(1).strip()
        return "（这条命令上面贴过了，不重复。）" if body in install_blocks else m.group(0)

    return re.sub(r"```[^\n]*\n(.*?)```", repl, quick, flags=re.S)


def compose(repo: Repo, date: str, cfg: dict, seo: dict | None = None) -> dict[str, Any]:
    name = repo.full_name.split("/")[-1]
    f = repo.facts()
    seo = seo or load_seo()
    s = seo_build(repo, date, seo)
    # H1 用统一的通用式标题：痛点词前置，再带功能 / 安装 / 使用三个搜索长尾词
    title = f"{name} 解决什么问题？功能、安装与上手"

    signals = "\n".join(f"- {s}" for s in repo.signals) or "- 说明文档里能看的东西不多"
    installs = "\n".join(f"```\n{b}\n```" for b in repo.install_blocks)
    install_note = (
        "下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。"
        if repo.install_blocks else
        "仓库说明里没给能直接复制的安装命令，怎么装得去仓库页面看。"
    )
    quick = _dedup_quickstart(repo.quickstart_excerpt.strip(), repo.install_blocks)
    # Quick Start 若只剩跟安装节重复的那条命令，整节略掉，别留一句占位话撑空节
    quick_body = quick.replace("（这条命令上面贴过了，不重复。）", "").strip()
    if quick_body:
        usage_section = "## 装完怎么上手\n\n仓库说明里 Quick Start（快速上手）那部分写了这些。\n\n" + quick_body + "\n\n"
    else:
        usage_section = ""
    topics = "、".join(repo.topics[:8]) if repo.topics else "没标"
    desc = repo.description or "（仓库没填简介）"

    # 痛点章节：只引用作者自己在 README 里写的 Why / Motivation / Problem 原文。
    # 没有这类章节就如实说明「未检出」，绝不代为编造使用场景或用户痛点。
    if repo.problem_excerpt:
        problem_block = (
            "作者在仓库说明里写了做这个东西的缘由。\n\n"
            + repo.problem_excerpt
        )
    else:
        intro_part = ""
        if repo.intro_excerpt.strip() and repo.intro_excerpt.strip() != desc:
            intro_part = "说明开头是这么写的。\n\n" + _quote(repo.intro_excerpt) + "\n\n"
        problem_block = (
            "仓库说明没专门写「为什么要做这个」，能看的只有作者自己那几句话。\n\n"
            + intro_part
            + "仓库简介就一句。\n\n> " + desc + "\n\n"
            + f"挂的标签是 {topics}，能看出它大概跟什么沾边。"
        )

    if repo.features_excerpt:
        features_block = "作者在说明里列了这些。\n\n" + repo.features_excerpt
    else:
        features_block = (
            "说明里没单列功能清单，能确认的只有仓库简介和这几项。\n\n"
            f"- 作者原话，{desc}\n"
            f"- 主要用 {repo.language} 写\n"
            f"- 标签有 {topics}\n"
        )

    faq_md = "\n".join(f"**{item['q']}**\n\n{item['a']}\n" for item in s["faq"])

    md = f"""# {title}

{s['seo_lead']}

## 它解决什么问题

{problem_block}

## 这是个什么项目

> {desc}

主要用 **{repo.language}** 写，GitHub 上攒了 **{repo.stars}** 颗星（就是收藏数），用的是 {repo.license} 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[{repo.full_name}]({repo.html_url})。

## 能做什么

{features_block}

## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

{signals}

## 安装教程

{install_note}

{installs}

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

{usage_section}## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [{repo.full_name}]({repo.html_url}) |
| 收藏数 | {repo.stars} |
| 主要用什么写 | {repo.language} |
| 开源协议 | {repo.license} |
| 标签 | {topics} |
| 创建时间 | {repo.created_at[:10]} |
| 最近更新 | {repo.pushed_at[:10]} |
| 数据记于 | {f['captured_at']} |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- {repo.license} 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

{faq_md}

---

{name} 还在改，装之前记得翻一眼仓库说明。
"""

    return {
        "repo": repo.full_name,
        "date": date,
        "title": title,                 # H1 用；发布标题见 titles[platform]
        "titles": s["titles"],           # 三个平台各自的 SEO 标题
        "brief": s["briefs"]["juejin"],  # 兼容字段
        "briefs": s["briefs"],
        "markdown": md,
        "html": md_to_html(md),
        "tags": s["csdn_tags"],
        "platform_tags": {"csdn": s["csdn_tags"]},
        "keywords": s["keywords"],
    }
