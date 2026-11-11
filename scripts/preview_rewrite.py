"""本机预览新结构稿：不联网、不发布、不烧云端额度。

用法：
    python scripts/preview_rewrite.py                 # 用内置的离线样例数据
    python scripts/preview_rewrite.py --date 2026-11-12   # 看另一天的轮换结果

数据来源：drafts/2026-11-10/storytold__wordcraft.md 里已归档的 wordcraft 真实字段
与 README 原文摘录。这是**样稿**，不是已发布文章，也不代表今天会选中这个项目。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.discover import Repo  # noqa: E402
from src.hooks import extract_selling_points  # noqa: E402
from src.rewrite import render_rewrite  # noqa: E402

# 以下是 2026-11-10 归档里存过的 README 原文摘录，逐句来自项目说明，不是新写的事实。
README_EXCERPT = """\
- **Familiar.** Ribbon tabs, groups, shortcuts and behaviour.
- **Your files.** Opens and saves .docx (OOXML), and also .odt, .rtf, .html, .md, .tex (LaTeX), .txt; opens legacy 97-2003 .doc; exports PDF with real, selectable text.
- **Fast.** Paragraph layout is cached, so typing in a 188-page document re-lays it out in about 1.4 ms; pages render on demand.
- **Everywhere.** One Rust codebase for macOS, Windows, Linux, BSD and the web. No Electron, no Tauri: native egui on the GPU.
- **Built for agents.** Every action is a command with an id. The same 422 commands drive the ribbon, keyboard shortcuts, the command search, a command-line tool, a JSON control channel and an MCP server.
- **Private.** Spelling, grammar and everything else work offline.
- **Open.** MIT OR Apache-2.0. Clean-room: built from public specifications and observation.
"""

INSTALL_BLOCKS = [
    "git clone https://github.com/storytold/wordcraft\n"
    "cd wordcraft\n"
    "cargo run --release -p wordcraft -- --sample\n"
    "cargo run --release -p wordcraft -- report.docx",
]


def build_repo() -> Repo:
    return Repo(
        full_name="storytold/wordcraft",
        html_url="https://github.com/storytold/wordcraft",
        description="WordCraft: an open-source, clean-room word processor in pure Rust",
        stars=17741,
        language="Rust",
        license="Apache-2.0",
        topics=[],
        created_at="2026-10-07T00:00:00Z",
        pushed_at="2026-11-10T00:00:00Z",
        default_branch="main",
        readme=README_EXCERPT,
        install_blocks=INSTALL_BLOCKS,
        quickstart_excerpt="Command line: cargo run --release -p wordcraft -- --sample",
        problem_excerpt="",
        features_excerpt=README_EXCERPT,
        intro_excerpt="",
        score=15,
        signals=[],
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    repo = build_repo()
    points = extract_selling_points(repo)
    result = render_rewrite(repo, args.date)
    arts = result["articles"]

    out = [
        f"# 新结构稿样稿 · {args.date}",
        "",
        "> 这是本机预览，**未发布**。项目字段与 README 摘录来自 "
        "`drafts/2026-11-10/storytold__wordcraft.md` 归档；",
        "> 实际每天发哪个项目由 GitHub 选题决定，这里只是展示标题与正文的新形态。",
        "",
        "## 从 README 抽到的真实信号（标题钩子）",
        "",
    ]
    out += [f"- {p}" for p in points]
    out += ["", "## 五平台标题（同一天，各不相同）", "",
            "| 平台 | 标题 |", "| --- | --- |"]
    for p, a in arts.items():
        out.append(f"| {p} | {a['title']} |")

    out += ["", "---", "", "## 知乎（云端实发通道）", ""]
    out += [f"**标题**：{arts['zhihu']['title']}", "", arts["zhihu"]["body"], "",
            "---", "", "## 掘金（云端实发通道）", "",
            f"**标题**：{arts['juejin']['title']}", "", arts["juejin"]["body"]]

    out += ["", "---", "", "## 其余平台开头预览", ""]
    for p in ("csdn", "wechat", "toutiao"):
        a = arts[p]
        out += [f"### {p} — {a['title']}", "", a["body"][:500], ""]

    target = ROOT / "drafts" / f"sample_{args.date}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out), encoding="utf-8")
    print(f"样稿已生成：{target}")
    print(f"防洗稿校验：{'通过' if result['guard']['ok'] else '未通过'}")
    for p, a in arts.items():
        print(f"  {p:8s} | {a['title']}")


if __name__ == "__main__":
    main()
