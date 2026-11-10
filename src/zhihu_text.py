"""知乎 Markdown → 适配富文本编辑器的 HTML。

背景（2026-11-10 实测）：
知乎编辑器是 Draft.js 富文本，**不吃 Markdown**：
- 粘贴 text/html → Draft.js 的 paste handler 会转成**纯文本**（格式全丢，
  但段落结构、链接文字保留）
- 逐字输入 `**粗体**` / `## 标题` / `| 表格 |` → **原样保留**，不会渲染

所以正确做法是：把 Markdown 转成 HTML，**并在转换阶段就把
表格和代码块改写成「纯文本也能读」的形态**，再交给 paste。

这样即使 Draft.js 把 HTML 降级成纯文本，读者看到的仍然是有结构的正文：
- 标题 → 用「▎」前缀的独立行（比 `#` 干净）
- 表格 → 「字段：值」逐行（比 `| a | b |` 干净）
- 代码块 → 缩进 4 空格 + 语言标注行（比 ``` 围栏干净）
- 粗体/链接 → 去掉标记，链接保留完整 URL（读者能复制）
"""
from __future__ import annotations

import re


def md_to_zhihu_text(md: str) -> str:
    """把 Markdown 改写成「纯文本也能读」的形态（用于 Draft.js 降级场景）。"""
    out: list[str] = []
    lines = md.split("\n")
    i = 0
    in_code = False
    code_lang = ""

    while i < len(lines):
        line = lines[i]

        # 代码块
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line.strip().lstrip("`").strip()
                out.append(f"【{code_lang or '代码'}】" if code_lang else "【代码】")
            else:
                in_code = False
                code_lang = ""
            i += 1
            continue

        if in_code:
            out.append("    " + line if line.strip() else "")
            i += 1
            continue

        # 表格：连续的 | 行
        if line.strip().startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip().strip("|")
                cells = [c.strip() for c in raw.split("|")]
                # 跳过分隔行 | --- | --- |
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                header = rows[0]
                # ⚠️ 不用启发式猜列方向（试过"含数字/含链接/长度"都不靠谱：
                # 「数据记于 | 2026-11-10」第一列才是字段名，「标签 | ai-agent…」
                # 第一列反而很长）。
                # 按 Markdown 表格通行约定：**第一列=字段名，第二列=值**。
                # 表头是占位词（项目/内容/字段…）时也按这个约定。
                h0 = header[0].strip()
                placeholder = h0 in ("项目", "内容", "字段", "项", "名称", "属性",
                                     "key", "Key", "value", "Value")
                two_col = len(header) == 2

                for r in rows[1:]:
                    if two_col:
                        a = _clean_inline(r[0]) if r else ""
                        b = _clean_inline(r[1]) if len(r) > 1 else ""
                        if not a and not b:
                            continue
                        if b:
                            out.append(f"・{a}：{b}" if a else f"・{b}")
                        else:
                            out.append(f"・{a}")
                        continue
                    parts = []
                    for idx, cell in enumerate(r):
                        key = header[idx] if idx < len(header) else ""
                        cell = _clean_inline(cell)
                        if not cell:
                            continue
                        parts.append(f"{key}：{cell}" if key and not placeholder
                                     else cell)
                    if parts:
                        out.append("・" + "；".join(parts))
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            title = _clean_inline(m.group(2))
            prefix = "▎" if level <= 2 else "· "
            out.append(f"{prefix}{title}")
            out.append("")
            i += 1
            continue

        # 引用：连续的 > 行合并成一个引用块（原文里的长引用会被拆成多段）
        if line.strip().startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(_clean_inline(lines[i].strip().lstrip(">").strip()))
                i += 1
            # 引用块内的列表项还原成 ・ 前缀
            fixed = []
            for ql in quote_lines:
                m2 = re.match(r"^[-*+]\s+(.*)$", ql)
                fixed.append("· " + m2.group(1) if m2 else ql)
            out.append("「" + " ".join(x for x in fixed if x) + "」")
            continue

        # 水平线
        if re.match(r"^-{3,}$", line.strip()):
            out.append("————————")
            i += 1
            continue

        # 列表
        m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if m:
            indent = len(m.group(1))
            out.append("　" * indent + "· " + _clean_inline(m.group(2)))
            i += 1
            continue

        # 有序列表
        m = re.match(r"^(\s*)\d+[.)]\s+(.*)$", line)
        if m:
            out.append("　" * len(m.group(1)) + m.group(0).strip().split(" ")[0]
                       + " " + _clean_inline(m.group(2)))
            i += 1
            continue

        out.append(_clean_inline(line))
        i += 1

    # 去掉多余空行（最多留 1 个）
    cleaned: list[str] = []
    for ln in out:
        if not ln.strip() and cleaned and not cleaned[-1].strip():
            continue
        cleaned.append(ln.rstrip())

    # 去掉首尾空行
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    return "\n".join(cleaned)


def _clean_inline(s: str) -> str:
    """去掉行内 Markdown 标记，但保留链接的可读形式。"""
    s = s.replace("**", "").replace("__", "")
    s = s.replace("`", "")
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1（\2）", s)
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    return s.strip()


def md_to_zhihu_html(md: str) -> str:
    """转成 HTML（给能吃 HTML 的场景用；本模块主路径是 md_to_zhihu_text）。"""
    import markdown
    return markdown.markdown(md, extensions=["tables", "fenced_code", "nl2br",
                                             "sane_lists"])
