"""按平台生成「吸引人且可被搜索到」的标题 / 摘要 / 标签 / FAQ。

红线：钩子只能由真实检测到的信号触发（单行安装、许可证、star 数、创建时间、topics），
不写「神器 / 必看 / 全网最全」这类无法证实的夸张词，也不虚构使用效果。
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import yaml

from .discover import Repo

ROOT = Path(__file__).resolve().parent.parent
# 「一行命令就能装好」只允许出现在：首选安装块恰好只有一条装包命令时。
# 实测踩坑：某仓库首选块有 3 行，单行的是另一条 npx skills add，
# 旧判定会把「任意块单行」当成一行装好，属于误导性宣传，必须收紧。
ONE_SHOT_RE = re.compile(
    r"^\s*(?:sudo\s+)?(?:pip3?\s+install|uv\s+pip\s+install|"
    r"npm\s+(?:i|install)(?:\s+-g)?|yarn\s+add|pnpm\s+add|"
    r"brew\s+install|cargo\s+install|go\s+install|uvx)\s+\S",
    re.I,
)


def load_seo() -> dict:
    return yaml.safe_load((ROOT / "config" / "seo.yaml").read_text(encoding="utf-8")) or {}


def _hook(repo: Repo, seo: dict) -> str:
    h = seo["hooks"]
    found: list[str] = []

    first = repo.install_blocks[0] if repo.install_blocks else ""
    lines = [l for l in first.splitlines() if l.strip() and not l.strip().startswith("#")]
    one_line = len(lines) == 1 and bool(ONE_SHOT_RE.match(lines[0]))
    # 优先级按「吸引力」排：能一行装好 > 具体 star 数 > 新项目 > 许可证。
    # 许可证几乎所有项目都有，放最后只当兜底，否则每天标题都长一个样。
    if one_line:
        found.append(h["one_command"])
    if repo.stars >= 1000:
        found.append(h["high_stars"].format(stars=repo.stars))
    try:
        days = (dt.date.today() - dt.date.fromisoformat(repo.created_at[:10])).days
        if 0 <= days <= 90:
            found.append(h["new_project"])
    except (ValueError, TypeError):
        pass
    if repo.license not in ("", "NOASSERTION", "None"):
        found.append(h["licensed"].format(license=repo.license))

    picked = found[: int(h.get("max_hooks", 2))]
    return "，".join(picked) if picked else h["fallback"]


def _fit(title: str, max_len: int) -> str:
    """超长时优先按分隔符丢掉尾部短语，尽量不截出半句话。"""
    if len(title) <= max_len:
        return title
    for sep in ("｜", "，", "（", "、"):
        while sep in title and len(title) > max_len:
            title = title.rsplit(sep, 1)[0]
    return title[:max_len].rstrip("，、｜（ ")


def _topics_zh(repo: Repo, seo: dict) -> list[str]:
    m = seo.get("topic_zh", {})
    return [m[t.lower()] for t in repo.topics if t.lower() in m][:4]


def build(repo: Repo, date: str, seo: dict) -> dict[str, Any]:
    name = repo.full_name.split("/")[-1]
    hook = _hook(repo, seo)
    desc_short = (repo.description or "仓库没填简介").strip()[:60]
    # 英文简介常自带句号，后面再补「。」会变成 ".。"，单独给一个去尾标点的版本
    desc_lead = desc_short.rstrip(".。!！?？;；")
    kw = _topics_zh(repo, seo)
    vals = {
        "name": name, "language": repo.language, "hook": hook, "stars": repo.stars,
        "license": repo.license, "desc_short": desc_short, "desc_lead": desc_lead,
    }
    # 用日期做确定性轮换：同一天所有平台用同一变体，跨天自动换样式
    variant = int(date.replace("-", "")) if date.replace("-", "").isdigit() else 0

    titles, briefs = {}, {}
    for platform, pcfg in seo["platforms"].items():
        tpls = pcfg["templates"]
        tpl = tpls[variant % len(tpls)]
        titles[platform] = _fit(tpl.format(**vals), int(pcfg["title_max"]))
        briefs[platform] = pcfg["brief_template"].format(**vals)[: int(pcfg["brief_max"])]

    tags = seo["csdn_tag_template"].format(**vals).split(",")
    faq = [
        {"q": item["q"].format(**vals), "a": item["a"].format(**vals)}
        for item in seo.get("faq", [])
    ]
    lead = (
        f"{name} 在 GitHub 上给自己的简介是「{desc_lead}」，{hook}。"
        + (f"仓库标签里有 {'、'.join(kw)}。" if kw else "")
        + "要不要装，先看它解决什么问题跟你对不对得上。"
    )
    return {
        "titles": titles,
        "briefs": briefs,
        "csdn_tags": ",".join(tags[: int(seo["csdn_tag_max"])]),
        "keywords": kw,
        "faq": faq,
        "seo_lead": lead,
    }
