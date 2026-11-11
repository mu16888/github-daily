"""真实信号钩子库：从 README / API 字段里抽「可核查的具体卖点」。

红线（与 topics.py 一致）：
- 只输出「原文里确实出现的数字、技术名词、格式后缀」+ 中文白话句式；
- 不推测效果、不编造体验、不调 LLM、不新增事实；
- 抽不到时退回 API 字段（收藏数 / 语言），保证标题永远有内容。

用途：标题从「X 解决什么问题？」这种万能句式，换成带具体事实的判断式短句。
"""
from __future__ import annotations

import re

from .discover import Repo

# 单条钩子的长度上限。超长的会被标题选择器按平台字数限制自然筛掉。
_MAX_LEN = 32


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_selling_points(repo: Repo) -> list[str]:
    """返回 1~4 条中文短句；每条都能在原文里找到触发词。"""
    # 优先扫结构化的章节摘录，最后才扫整篇 README，减少徽章/代码块误命中。
    text = "\n".join(
        t for t in (
            getattr(repo, "features_excerpt", "") or "",
            getattr(repo, "intro_excerpt", "") or "",
            getattr(repo, "problem_excerpt", "") or "",
            getattr(repo, "description", "") or "",
            getattr(repo, "readme", "") or "",
        ) if t
    )
    out: list[str] = []

    def add(s: str) -> None:
        s = _clean(s)
        if s and len(s) <= _MAX_LEN and s not in out:
            out.append(s)

    # ① 具体数字：命令数、文档页数 + 重排耗时
    m = re.search(r"\b(\d{2,6})\s+commands?\b", text, re.I)
    if m:
        add(f"{m.group(1)} 个可调用命令")
    m = re.search(r"\b(\d{2,5})[- ]page\b", text, re.I)
    if m:
        ms = re.search(r"\b(\d+(?:\.\d+)?)\s*ms\b", text[m.end(): m.end() + 300], re.I)
        if ms:
            add(f"{m.group(1)} 页约 {ms.group(1)} ms 的重排")

    # ② 明确的技术取舍（"No Electron, no Tauri" 这类原文否定式）
    m = re.search(
        r"\bNo\s+([A-Za-z][\w.-]{1,20})(?:,?\s+no\s+([A-Za-z][\w.-]{1,20}))?",
        text,
    )
    if m:
        add(f"不用 {m.group(1)} 与 {m.group(2)}" if m.group(2)
            else f"不用 {m.group(1)} 的实现")

    # ③ 支持的文件格式（至少 3 种才算一条可核查的卖点）
    exts: list[str] = []
    for e in re.findall(
        r"\.(docx|odt|rtf|html|md|tex|txt|pdf|csv|json|yaml|toml)\b", text, re.I
    ):
        if e.lower() not in exts:
            exts.append(e.lower())
    if len(exts) >= 3:
        add(" / ".join(exts[:3]) + " 格式支持")

    # ④ 能力 / 实现方式关键词
    # 一律输出「名词短语」而非完整句子：标题模板要把它当定语/宾语拼接，
    # 用句子会出现「从 422 个操作都做成了命令 说起」这种语病。
    if re.search(r"\boffline\b", text, re.I):
        add("离线可用")
    if re.search(r"\bclean[- ]room\b", text, re.I):
        add("干净室实现")
    m = re.search(r"\bin pure ([A-Za-z][\w+#.-]{1,15})\b", text, re.I)
    if m:
        add(f"纯 {m.group(1)} 实现")
    if re.search(r"\bMCP\s+server\b", text, re.I):
        add("MCP server 接口")
    if re.search(r"macOS.{0,24}Windows.{0,24}Linux", text, re.I | re.S):
        add("三端一套代码")

    # ⑤ 兜底：API 字段，永远可核查
    if len(out) < 2 and repo.stars:
        add(f"{repo.stars} Star")
    if not out:
        add(f"{repo.language or '开源'} 写的开源项目")
    return out[:4]


def selling_point(repo: Repo) -> str:
    """标题用的单个最强钩子，保证非空。"""
    pts = extract_selling_points(repo)
    return pts[0] if pts else (repo.language or "开源项目")
