"""候选发现、事实抽取与「小白友好」打分。

原则：所有写进文章的事实只来自 GitHub REST API 与 README 原文。
本模块不生成、不补全、不推测任何安装命令、版本号或数字。
"""
from __future__ import annotations

import base64
import datetime as dt
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

GITHUB_API = "https://api.github.com"

FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
# 必须匹配「行首的安装命令」，不能用 \b 全块搜索：
# README 注释里一句 "use 'pip install' rather than..." 曾让环境准备代码块被误当成安装步骤。
INSTALL_LINE_RE = re.compile(
    r"^\s*(?:sudo\s+)?(?:"
    r"pip3?\s+install|uv\s+pip\s+install|npm\s+(?:i|install)|yarn\s+add|pnpm\s+add|"
    r"brew\s+install|docker\s+run|uvx|npx|cargo\s+install|go\s+install|"
    r"git\s+clone|curl\s+-fsSL|wget\s+"
    r")\b",
    re.I,
)
# 直接安装（装包）优先于「clone 源码再装」
DIRECT_INSTALL_RE = re.compile(
    r"^\s*(?:sudo\s+)?(?:pip3?\s+install|uv\s+pip\s+install|npm\s+(?:i|install)|"
    r"yarn\s+add|pnpm\s+add|brew\s+install|cargo\s+install|go\s+install|uvx|npx)\b",
    re.I,
)
COMPILE_RE = re.compile(r"\b(make build|go build|cargo build|cmake|./configure|compile from source)\b", re.I)
HEAVY_DEP_RE = re.compile(
    r"(requires? (?:an? )?(?:api key|postgres|mysql|redis|docker|kubernetes)|"
    r"paid plan|subscription|需要 .{0,6}(?:API|密钥|付费))",
    re.I,
)
WIP_RE = re.compile(r"\b(WIP|work in progress|experimental|not production[- ]ready|alpha stage)\b", re.I)
# 话题框架 v3（2026-11-14）：4 个「判断力」文本代理指标。
# 只匹配 README 里真实出现的词，不推测项目价值；用于排序，不用于硬筛。
LIMITATION_RE = re.compile(
    r"\b(limitations?|caveats?|known issues?|not suitable|constraints?)\b|"
    r"(已知问题|不适用场景|使用限制|适用边界)", re.I)
COMPARISON_RE = re.compile(
    r"\b(benchmarks?|compared (?:to|with)|vs\.?|alternatives?|trade-?offs?)\b|"
    r"(对比|横评|性能实测|替代方案|同类方案)", re.I)
CHANGE_RE = re.compile(
    r"\b(breaking changes?|migration guide|deprecated|changelog|release notes|"
    r"upgrade guide|no longer supported)\b|(迁移指南|版本变动|弃用|不兼容|升级说明)", re.I)
WHY_RE = re.compile(
    r"\b(why|design decisions?|rationale|motivation|architecture decisions?)\b|"
    r"(设计取舍|为什么做|原理|设计动机)", re.I)
QUICKSTART_RE = re.compile(
    r"(?im)^#{1,4}\s*(?:[0-9.]*\s*)?"
    r"(quick\s*start|getting started|installation|install|usage|how to use|"
    r"快速开始|安装|上手|用法|使用)\b[^\n]*\n"
)
HEADING_RE = re.compile(r"(?m)^#{1,4}\s+\S")
# 真正的「上手」章节。QUICKSTART_RE 里含 install，只配给打分用；抽正文时若直接拿它，
# 排在前面的 ## Install 会把 ## Quick Start 的内容抢走，导致「上手」一节空掉。
USAGE_RE = re.compile(
    r"(?im)^#{1,4}\s*(?:[0-9.]*\s*)?"
    r"(?:(?:quick\s*start|getting\s+started|usage|how\s+to\s+use)\b|"
    r"(?:快速开始|快速上手|上手|用法|使用方法|使用说明))"
    r"[^\n]*\n"
)
# 作者自己写的「为什么做 / 解决什么」与「功能」章节：痛点只能引用原文，不能代为编造
PROBLEM_RE = re.compile(
    r"(?im)^#{1,4}\s*(?:[0-9.]*\s*)?"
    r"(?:why\b|why\s+\w+|motivation\b|problem\b|the problem\b|background\b|rationale\b|"
    r"为什么|背景|痛点|解决什么问题|要解决什么问题|项目缘起)[^\n]*\n"
)
FEATURES_RE = re.compile(
    r"(?im)^#{1,4}\s*(?:[0-9.]*\s*)?"
    r"(?:features\b|key features\b|what it does\b|capabilities\b|highlights\b|"
    r"how it works\b|overview\b|about\b|"
    r"功能|特性|核心功能|主要功能|能做什么|工作原理)[^\n]*\n"
)
# README 里的徽章、架构图块与相对路径图片：发到第三方平台会变成死链，引用时一律剔除
BADGE_BLOCK_RE = re.compile(
    r"<p\b.*?</p>|<div\b.*?</div>|<picture\b.*?</picture>", re.S | re.I
)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HTML_TAG_RE = re.compile(r"<[^>]+>")


def _drop_trailing_fragment(text: str) -> str:
    """丢掉末尾没写完的半句（例如 "It ships as a"），避免把残句当原文引用出去。"""
    t = text.rstrip()
    if not t or t[-1] in ".。!?！:：;；)）`\"'":
        return t
    for sep in (". ", "。 ", "! ", "！ ", "? ", "？ "):
        pos = t.rfind(sep)
        if pos > 0:
            return t[: pos + 1].rstrip()
    lines = t.splitlines()
    return "\n".join(lines[:-1]).rstrip() if len(lines) > 1 else ""


def _truncate_clean(text: str, limit: int) -> str:
    """截断原文时回退到段落 / 句子边界，并保证代码围栏成对，不切出半句话。"""
    if len(text) <= limit:
        return _drop_trailing_fragment(text)
    cut = text[:limit]
    for sep in ("\n\n", ". ", "。 ", "\n"):
        pos = cut.rfind(sep)
        if pos > limit * 0.6:
            cut = cut[: pos + len(sep)]
            break
    if cut.count("```") % 2 == 1:
        cut = cut[: cut.rfind("```")]
    return _drop_trailing_fragment(cut.rstrip())


def _session() -> requests.Session:
    """不读系统代理环境变量：CI 里应直连，本机也不该被代理悄悄劫持。"""
    s = requests.Session()
    s.trust_env = False
    return s


_GH_TOKEN_CACHE: str | None = None
_GH_TOKEN_TRIED = False


def _github_token() -> str:
    """CI 用注入的 GITHUB_TOKEN；本地优先复用已登录 gh 的凭据，避免撞未认证 60 次/小时限额。"""
    global _GH_TOKEN_CACHE, _GH_TOKEN_TRIED
    if _GH_TOKEN_TRIED:
        return _GH_TOKEN_CACHE or ""
    _GH_TOKEN_TRIED = True
    t = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not t:
        try:
            import subprocess
            r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=8)
            if r.returncode == 0:
                t = r.stdout.strip()
        except Exception:
            pass
    _GH_TOKEN_CACHE = t
    return t


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-daily/0.1",
    }
    token = _github_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def api_get(session: requests.Session, path: str, params: dict | None = None, retries: int = 3) -> Any:
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = session.get(url, headers=_headers(), params=params, timeout=25)
        except requests.RequestException as e:  # 网络抖动
            last = e
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (403, 429):
            wait = int(r.headers.get("retry-after") or 5)
            time.sleep(min(wait, 30))
            hint = "" if _github_token() else "（未认证请求上限 60 次/小时；请设置 GITHUB_TOKEN 或 gh auth login）"
            last = RuntimeError(f"rate limited: HTTP {r.status_code} {hint}")
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"GitHub API failed after {retries} attempts: {last}")


@dataclass
class Repo:
    full_name: str
    html_url: str
    description: str
    stars: int
    language: str
    license: str
    topics: list[str]
    created_at: str
    pushed_at: str
    default_branch: str
    readme: str = ""
    install_blocks: list[str] = field(default_factory=list)
    quickstart_excerpt: str = ""
    problem_excerpt: str = ""
    features_excerpt: str = ""
    intro_excerpt: str = ""
    score: int = 0
    signals: list[str] = field(default_factory=list)

    def slug(self) -> str:
        return self.full_name.replace("/", "__")

    def facts(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "html_url": self.html_url,
            "description": self.description,
            "stars": self.stars,
            "language": self.language,
            "license": self.license,
            "topics": self.topics,
            "created_at": self.created_at,
            "pushed_at": self.pushed_at,
            "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }


def _repo_from_api(item: dict) -> Repo:
    lic = item.get("license") or {}
    return Repo(
        full_name=item["full_name"],
        html_url=item["html_url"],
        description=item.get("description") or "",
        stars=int(item.get("stargazers_count") or 0),
        language=item.get("language") or "未标注",
        license=(lic.get("spdx_id") or "NOASSERTION") if isinstance(lic, dict) else "NOASSERTION",
        topics=item.get("topics") or [],
        created_at=item.get("created_at") or "",
        pushed_at=item.get("pushed_at") or "",
        default_branch=item.get("default_branch") or "main",
    )


def fetch_readme(session: requests.Session, full_name: str) -> str:
    """走 /repos/{name}/readme，返回 README 原文；取不到就返回空串。"""
    data = api_get(session, f"/repos/{full_name}/readme")
    if isinstance(data, dict) and data.get("content"):
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def extract_install_blocks(readme: str, limit: int = 2) -> list[str]:
    """原样返回 README 中真正含安装命令的代码块，一个字符都不改。

    过滤注释行、只认行首命令，并把「直接装包」的块排在「clone 源码」之前。
    """
    scored: list[tuple[int, int, str]] = []
    for idx, block in enumerate(FENCE_RE.findall(readme)):
        text = block.strip()
        if not (8 <= len(text) <= 1200):
            continue
        code_lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not any(INSTALL_LINE_RE.match(l) for l in code_lines):
            continue
        direct = any(DIRECT_INSTALL_RE.match(l) for l in code_lines)
        scored.append((0 if direct else 1, idx, text))
    scored.sort(key=lambda x: (x[0], x[1]))
    out: list[str] = []
    for _priority, _idx, text in scored:
        if text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _section_after(readme: str, heading_re: re.Pattern, limit: int = 1200) -> str:
    """抽取某个标题下、到下一个标题之前的原文，并保证代码围栏成对。"""
    m = heading_re.search(readme)
    if not m:
        return ""
    rest = readme[m.end():]
    nxt = HEADING_RE.search(rest)
    section = (rest[: nxt.start()] if nxt else rest).strip()
    section = BADGE_BLOCK_RE.sub("", section)
    section = IMAGE_RE.sub("", section)
    return _truncate_clean(section.strip(), limit)


def extract_quickstart(readme: str, limit: int = 1200) -> str:
    # 优先取真正的 Quick Start / Usage / 用法 章节；没有才退回含 Install 的宽匹配
    section = _section_after(readme, USAGE_RE, limit)
    return section or _section_after(readme, QUICKSTART_RE, limit)


def extract_problem(readme: str, limit: int = 1200) -> str:
    return _section_after(readme, PROBLEM_RE, limit)


def extract_features(readme: str, limit: int = 1200) -> str:
    return _section_after(readme, FEATURES_RE, limit)


def extract_intro(readme: str, limit: int = 800) -> str:
    """取 README 第一个标题之后、下一个标题之前的开头原文（去掉徽章 / 图片 / HTML）。

    很多项目没有独立的 Why 章节，但开头那一两句往往就是「它解决什么」的最准表述。
    引用原文而不是自己改写，才能在不编造的前提下把痛点讲清楚。
    """
    first = HEADING_RE.search(readme)
    if not first:
        return ""
    line_end = readme.find("\n", first.start())
    rest = readme[line_end + 1:] if line_end >= 0 else ""
    nxt = HEADING_RE.search(rest)
    block = rest[: nxt.start()] if nxt else rest
    block = BADGE_BLOCK_RE.sub("", block)
    block = IMAGE_RE.sub("", block)
    block = HTML_TAG_RE.sub("", block)
    lines = [l.strip() for l in block.splitlines()
             if l.strip() and not l.strip().startswith("|") and not l.strip().startswith("[!")]
    return _truncate_clean("\n".join(lines).strip(), limit)


def score(repo: Repo, w: dict) -> tuple[int, list[str]]:
    """只依据 README / API 里真实出现的信号打分，返回分数与可解释的依据。"""
    total, signals = 0, []
    readme = repo.readme
    low = readme.lower()

    def add(key: str, ok: bool, note: str) -> None:
        nonlocal total
        weight = int(w.get(key, 0))
        # 权重置 0 的信号不再写进 signals：否则日志里会出现「免编译」
        # 这类看似加了分、实际 0 分的说明，误导排查。
        if ok and weight:
            total += weight
            signals.append(note)

    add("readme_present", bool(readme), "写了说明文档")
    add("readme_substantial", len(readme) >= 800, "说明写得够长，不是三两句就完事")
    add("quickstart_section", bool(QUICKSTART_RE.search(readme)), "写了 Quick Start（快速上手）和怎么装")
    add("one_command_install", bool(repo.install_blocks), "有能直接复制的安装命令")
    add("has_license", repo.license not in ("", "NOASSERTION", "None"), f"标了 {repo.license} 协议，用起来有规矩")
    add("no_compile_required", bool(readme) and not COMPILE_RE.search(readme), "不用自己把源码做成软件")
    add("low_dependency", bool(readme) and not HEAVY_DEP_RE.search(low), "不用另外配数据库、账号或者付费服务")
    add("sweet_spot_stars", 500 <= repo.stars <= 20000, f"{repo.stars} 颗星，不算冷门")
    # 判断力信号：README 明确写了边界 / 对比 / 变动 / 取舍，说明值得展开判断
    add("has_limitations", bool(LIMITATION_RE.search(readme)), "写明了限制或不适用场景")
    add("has_comparison", bool(COMPARISON_RE.search(readme)), "有对比或基准测试")
    add("has_change_signal", bool(CHANGE_RE.search(readme)), "有版本变动或迁移说明")
    add("has_why_section", bool(WHY_RE.search(readme)), "讲了设计取舍或为什么做")

    if readme and len(readme) < 400:
        total += int(w.get("penalty_tiny_readme", 0))
        signals.append("说明太短，可能讲不清楚")
    if WIP_RE.search(readme):
        total += int(w.get("penalty_wip", 0))
        signals.append("作者自己标了 WIP / experimental，还在改")
    if HEAVY_DEP_RE.search(low):
        total += int(w.get("penalty_paid_or_key", 0))
        signals.append("还得另外配服务或密钥才能跑")

    return total, signals


def search_candidates(session: requests.Session, queries: list[str], cfg: dict) -> list[Repo]:
    today = dt.date.today()
    since = (today - dt.timedelta(days=int(cfg["daily"]["since_days"]))).isoformat()
    recent = (today - dt.timedelta(days=7)).isoformat()
    vals = {
        "since": since,
        "recent": recent,
        "stars_min": cfg["daily"]["stars_min"],
        "stars_max": cfg["daily"]["stars_max"],
    }
    per_page = min(30, max(1, int(cfg["daily"]["candidate_pool"]) // max(1, len(queries))))
    seen: dict[str, Repo] = {}
    for tpl in queries:
        q = tpl.format(**vals)
        data = api_get(session, "/search/repositories", {"q": q, "per_page": per_page, "sort": "stars", "order": "desc"})
        if not isinstance(data, dict):
            continue
        for item in data.get("items", []):
            repo = _repo_from_api(item)
            seen.setdefault(repo.full_name, repo)
        time.sleep(1)  # 搜索接口有独立且更严的限额，主动节流
    return list(seen.values())


def enrich(session: requests.Session, repo: Repo, w: dict) -> Repo:
    repo.readme = fetch_readme(session, repo.full_name)
    repo.install_blocks = extract_install_blocks(repo.readme)
    repo.quickstart_excerpt = extract_quickstart(repo.readme)
    repo.problem_excerpt = extract_problem(repo.readme)
    repo.features_excerpt = extract_features(repo.readme)
    repo.intro_excerpt = extract_intro(repo.readme)
    repo.score, repo.signals = score(repo, w)
    return repo


def pick(session: requests.Session, cfg: dict, already: set[str], limit: int = 1) -> list[Repo]:
    """返回本次要出稿的项目；已发布过的项目直接跳过，保证跨天不重复。"""
    candidates = search_candidates(session, cfg["queries"], cfg)
    pool: list[Repo] = []
    min_score = int(cfg["daily"]["min_score"])
    # 话题框架 v3：旧逻辑硬写 `and repo.install_blocks`，等于「没安装命令就不许入选」，
    # 正是每天只推出陌生小工具说明书的机制性根因。改由配置开关控制，
    # 缺省 True 保持旧行为（向后兼容），本机/云端 settings.yaml 已设 false。
    require_install = bool(cfg["daily"].get("require_install_blocks", True))
    for repo in candidates:
        if repo.full_name in already:
            continue
        if repo.full_name.startswith("."):
            continue
        enrich(session, repo, cfg["score_weights"])
        if repo.score >= min_score and (not require_install or repo.install_blocks):
            pool.append(repo)
    pool.sort(key=lambda r: (-r.score, -r.stars))
    return pool[:limit]
