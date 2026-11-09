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
        return "（这段安装命令已在上一节原样给出，此处不再重复。）" if body in install_blocks else m.group(0)

    return re.sub(r"```[^\n]*\n(.*?)```", repl, quick, flags=re.S)


def compose(repo: Repo, date: str, cfg: dict, seo: dict | None = None) -> dict[str, Any]:
    name = repo.full_name.split("/")[-1]
    f = repo.facts()
    seo = seo or load_seo()
    s = seo_build(repo, date, seo)
    # H1 用统一的通用式标题：痛点词前置，再带功能 / 安装 / 使用三个搜索长尾词
    title = f"{name} 解决什么问题？功能、安装与使用完整介绍"

    signals = "\n".join(f"- {s}" for s in repo.signals) or "- （未检测到明确的加分信号）"
    installs = "\n".join(f"```\n{b}\n```" for b in repo.install_blocks)
    install_note = (
        "以下命令**逐字摘自该仓库 README**，未做任何改写。执行前请先到仓库页面确认是否有更新。"
        if repo.install_blocks else
        "README 中未检出可直接复制的安装命令，本文不代为猜测，请到仓库页面查看安装说明。"
    )
    quick = _dedup_quickstart(repo.quickstart_excerpt.strip(), repo.install_blocks)
    quick_section = (
        "以下同样摘自 README 的 Quick Start / 用法 章节原文：\n\n" + quick
        if quick else
        "README 里没有检出明确的 Quick Start 章节。本文不编写未经证实的上手步骤，建议直接看仓库 README。"
    )
    topics = "、".join(repo.topics[:8]) if repo.topics else "未标注"
    desc = repo.description or "（仓库未填写 description）"

    # 痛点章节：只引用作者自己在 README 里写的 Why / Motivation / Problem 原文。
    # 没有这类章节就如实说明「未检出」，绝不代为编造使用场景或用户痛点。
    if repo.problem_excerpt:
        problem_block = (
            "**作者在 README 里怎么说的（原文摘录，未改写）：**\n\n"
            + repo.problem_excerpt
            + "\n\n> 以上为仓库原文。具体痛点以作者表述为准，本文不额外补充未经写明的使用效果。"
        )
    else:
        intro_part = ""
        if repo.intro_excerpt.strip() and repo.intro_excerpt.strip() != desc:
            intro_part = "**README 开头原文：**\n\n" + _quote(repo.intro_excerpt) + "\n\n"
        problem_block = (
            "README 里**没有检出**作者明确写的 Why / Motivation / Problem / 背景 章节，"
            "所以这里不编造痛点。下面引用的都是仓库里的原话，请据此先判断它对不对口：\n\n"
            + intro_part
            + "**仓库描述（原文）：**\n\n> " + desc + "\n\n"
            f"把上面的自述换个说法：{name} 面向的是「{desc}」这件事。"
            "这只是复述，不是作者原话，也不代表任何未写明的成效。\n\n"
            f"能查证的领域标签（GitHub topics）：{topics}。"
        )

    if repo.features_excerpt:
        features_block = (
            "以下内容**逐字摘自 README 的 Features / How it works / 功能 章节原文**：\n\n"
            + repo.features_excerpt
        )
    else:
        features_block = (
            "README 里没有检出独立的 Features / 功能 章节，本文不代为罗列功能。"
            "能确认的只有仓库自述与元数据：\n\n"
            f"- 仓库自述：{desc}\n"
            f"- 主要语言：{repo.language}\n"
            f"- GitHub topics：{topics}\n"
            "- 可复制的安装命令见下一节（同样来自 README 原文）"
        )

    faq_md = "\n".join(f"**{item['q']}**\n\n{item['a']}\n" for item in s["faq"])

    md = f"""# {title}

{s['seo_lead']}

> 本文由程序自动生成，所有事实来自 GitHub REST API 与项目 README 原文，采集日期 {date}。
> 文中不添加任何未经证实的安装方式、版本号或使用效果。

## 一、{name} 解决什么问题（先看痛点）

{problem_block}

**先判断对不对口，再往下看功能与安装。** 如果上面说的并不是你要解决的问题，这个项目再热门也不用装。

## 二、{name} 是什么

仓库自述（原文）：

> {desc}

用大白话说：这是一个主要用 **{repo.language}** 写的开源项目，托管在 GitHub，
目前有 **{repo.stars}** 颗 star，开源许可证是 **{repo.license}**。
项目地址：[{repo.full_name}]({repo.html_url})。

## 三、核心功能（README 原文）

{features_block}

## 四、为什么说它适合新手

打分依据全部来自 README 与仓库元数据中**实际检测到**的信号，不是主观推荐：

{signals}

综合得分 **{repo.score}** 分（门槛 {cfg['daily']['min_score']} 分）。
评分只看「有没有写清楚怎么装、要不要自己编译、有没有许可证、是否依赖额外服务」这类客观信号，
不看项目热度排名，也不代表功能强弱评价。

## 五、{name} 安装教程（README 原文命令）

{install_note}

{installs}

如果命令跑不通，优先检查三件事：README 是否已更新、本机是否装了对应语言的运行时、
以及项目是否要求特定版本。这些都请以仓库页面为准。

## 六、{name} 怎么上手

{quick_section}

## 七、项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [{repo.full_name}]({repo.html_url}) |
| Star 数 | {repo.stars} |
| 主要语言 | {repo.language} |
| 许可证 | {repo.license} |
| 话题标签 | {topics} |
| 创建时间 | {repo.created_at[:10]} |
| 最近更新 | {repo.pushed_at[:10]} |
| 数据采集时间 | {f['captured_at']} |

## 八、需要注意

- 本文只做介绍，**不是安装教程的替代品**；项目随时可能改安装方式，一切以仓库 README 为准。
- 许可证是 {repo.license}，商用或二次分发前请自行确认条款。
- star 数是采集瞬间的快照，会变化。
- 本文由程序按模板生成，未使用大模型改写，因此读起来偏「说明书」风格；好处是数字和命令不会被编造。

## 九、常见问题（{name} FAQ）

{faq_md}

## 十、信息来源

- GitHub REST API：`/repos/{repo.full_name}` 与 `/search/repositories`
- 项目 README 原文：`{repo.html_url}/blob/{repo.default_branch}/README.md`
- 采集脚本：[github-daily](https://github.com/mu16888/github-daily)

---

*本文由 GitHub Actions 自动生成并发布。若信息有误，请以项目仓库为准。*
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
