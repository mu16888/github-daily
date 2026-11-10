"""话题层：把被验证过的高赞「结构」变成可复用的切入角度。

边界（写死，别越线）：
1. 只借结构骨架（判断开场 / 可带走清单 / 最小一步），不复制原文句子、标题、代码或观点。
2. 观点可以写，事实必须能溯源：文章里的数字、命令、日期全部来自 GitHub REST API 与 README 原文。
3. 本模块不调 LLM（云端无免费推理），「自己的表达」= 结构原型 + 白话句式按日轮换 + 真实事实；
   表达多样性受模板数量限制，不能对外宣称是生成式改写。
4. 热榜只走匿名公开接口；不碰登录态浏览器与任何社交账号。

用法：
  python -m src.topics --check                    # 自检话题池与防洗稿基准
  python -m src.topics --refresh-hot              # 刷新当日热榜信号到 state/hot_signals.json
  python -m src.topics --preview agentsmd/agents.md  # 用真实仓库跑五平台新结构样稿
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
TOPICS_FILE = ROOT / "config" / "topics.yaml"
HOT_STATE_FILE = ROOT / "state" / "hot_signals.json"
HOT_API = "https://api.juejin.cn/content_api/v1/content/article_rank"

_CJK_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]")


def load_topics(path: Path | None = None) -> dict:
    return yaml.safe_load((path or TOPICS_FILE).read_text(encoding="utf-8")) or {}


@dataclass
class TopicPlan:
    """当天选中的结构原型。渲染器只读这里，不直接碰原文标题。"""
    id: str
    hook_type: str
    basis: str
    opening: str
    closing: str
    sections: list[str]
    takeaway_title: str
    source_query: str
    default_labels: list[str]
    reference_titles: list[str]
    date: str
    index: int
    opening_index: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "hook_type": self.hook_type,
            "opening_index": self.opening_index, "sections": list(self.sections),
            "source_query": self.source_query, "date": self.date,
        }


def _day_number(date: str) -> int:
    s = date.replace("-", "")
    return int(s) if s.isdigit() else 0


def choose(date: str, cfg: dict | None = None, salt: str = "opening") -> TopicPlan:
    """按日期确定性选原型与句式：同一天重跑一致，跨天自动轮换。"""
    cfg = cfg or load_topics()
    protos = cfg.get("prototypes") or []
    if not protos:
        raise ValueError("config/topics.yaml 没有 prototypes，话题层无法工作")
    day = _day_number(date)
    idx = day % len(protos)
    p = protos[idx]
    openings = p.get("openings") or [""]
    closings = p.get("closings") or [""]
    salt_n = sum(ord(c) for c in salt)
    oi = (day + salt_n) % len(openings)
    return TopicPlan(
        id=str(p["id"]),
        hook_type=str(p.get("hook_type", "")),
        basis=str(p.get("basis", "")),
        opening=str(openings[oi]),
        closing=str(closings[(day + salt_n) % len(closings)]),
        sections=list(p.get("sections") or []),
        takeaway_title=str(p.get("takeaway_title", "能带走的几条")),
        source_query=str(p.get("source_query", "")),
        default_labels=list(p.get("default_labels") or []),
        reference_titles=list(cfg.get("reference_titles") or []),
        date=date,
        index=idx,
        opening_index=oi,
    )


def ngrams(text: str, n: int = 8) -> set[str]:
    """取连续 n 字片段集合；先剥掉标点与空白，只比对字面。"""
    s = _CJK_RE.sub("", text or "")
    if len(s) < n:
        return set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def ngram_overlap(source: str, draft: str, n: int = 8,
                  normalize: tuple[str, ...] | list[str] = ()) -> tuple[int, list[str]]:
    """返回 (重合片段数, 最多 5 个样例)。0 表示未发现成段复制。

    normalize 里的公开专有名词在**两边同时**清掉，避免「同一个文件名」
    被误判成洗稿；整句照抄时其余片段仍会大量重合，校验不会被架空。
    注意：只比对字面，不代表观点 / 结构相似度；结构借用须在文档里显式列出。
    """
    for term in normalize or ():
        plain = _CJK_RE.sub("", term)
        source = source.replace(term, "").replace(plain, "")
        draft = draft.replace(term, "").replace(plain, "")
    a, b = ngrams(source, n), ngrams(draft, n)
    hits = sorted(a & b)
    return len(hits), hits[:5]


def guard(cfg: dict, drafts: dict[str, str]) -> dict[str, Any]:
    """对所有平台成稿做统一防洗稿校验。"""
    g = cfg.get("guardrails") or {}
    n = int(g.get("ngram", 8))
    terms = tuple(g.get("normalize_terms") or ())
    src = "\n".join(cfg.get("reference_titles") or [])
    out: dict[str, Any] = {"ngram": n, "platforms": {}, "ok": True,
                           "normalized_terms": list(terms),
                           "source_grams": len(ngrams(src, n))}
    for platform, body in drafts.items():
        count, samples = ngram_overlap(src, body, n, normalize=terms)
        out["platforms"][platform] = {"overlap": count, "samples": samples,
                                       "draft_grams": len(ngrams(body, n))}
        if count > int((cfg.get("guardrails") or {}).get("max_overlap", 0)):
            out["ok"] = False
    return out


def labels_for(plan: TopicPlan, cfg: dict, repo: Any, platform: str,
               topic_zh: dict | None = None) -> dict[str, Any]:
    """同话题标签关联。只填已实测通道，未实测的如实返回 unverified，不凭猜填 id。"""
    meta = (cfg.get("labels") or {}).get(platform, {})
    status = str(meta.get("status", "unverified"))
    raw = [str(t).strip() for t in (getattr(repo, "topics", []) or []) if str(t).strip()]
    zh = [topic_zh[t.lower()] for t in raw if topic_zh and t.lower() in topic_zh]
    names: list[str] = []
    # CSDN 等标签字段保留 GitHub 真实 topic 原文；文内话题只用中文，不塞英文
    for x in (raw[:3] + zh + plan.default_labels):
        if x and x not in names:
            names.append(x)
    zh_names = [x for x in names if re.search(r"[\u4e00-\u9fff]", x)]

    if status == "ready":
        return {"field": meta.get("field", ""), "status": status,
                "value": ",".join(names[:5]), "note": meta.get("note", "")}
    if status == "text_only":
        words = " ".join("#" + x.replace(" ", "") + "#"
                         for x in (zh_names or names)[:3])
        return {"field": meta.get("field", ""), "status": status,
                "value": words, "note": meta.get("note", "")}
    return {"field": meta.get("field", ""), "status": status,
            "value": "", "note": meta.get("note", "未实测，不填")}


# --------------------------------------------------------------------------- #
# 热榜信号刷新（匿名只读，失败不影响出稿）
# --------------------------------------------------------------------------- #

def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def _walk_items(node: Any) -> list[dict]:
    """宽容解析：找出所有带 content_counter 的条目，不假设固定嵌套层级。"""
    out: list[dict] = []
    if isinstance(node, dict):
        if isinstance(node.get("content_counter"), dict):
            out.append(node)
        for v in node.values():
            out.extend(_walk_items(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_walk_items(v))
    return out


def fetch_hot(timeout: int = 20) -> dict[str, Any]:
    """抓掘金技术热榜公开接口，返回结构化信号；失败如实返回 error，不伪造数据。"""
    try:
        r = _session().get(HOT_API, params={"category_id": "1", "type": "hot"},
                           headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                           timeout=timeout)
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}", "items": []}
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "items": []}

    items = []
    for it in _walk_items(data):
        cc = it.get("content_counter") or {}
        content = it.get("content") if isinstance(it.get("content"), dict) else it
        title = str(content.get("title") or it.get("title") or "").strip()
        if not title:
            continue
        items.append({
            "title": title,
            "like": int(cc.get("like") or 0),
            "collect": int(cc.get("collect") or 0),
            "comment": int(cc.get("comment_count") or 0),
            "view": int(cc.get("view") or 0),
            "hot_rank": cc.get("hot_rank"),
        })
    if not items:
        return {"ok": False, "error": "响应里没有可解析的 content_counter 条目", "items": []}
    return {
        "ok": True,
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "publisher": "掘金技术热榜（公开接口，匿名只读）",
        "source_url": HOT_API + "?category_id=1&type=hot",
        "count": len(items),
        "items": items,
    }


def refresh_hot() -> dict:
    result = fetch_hot()
    if not result.get("ok"):
        return result
    HOT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOT_STATE_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _preview(repo_name: str, date: str) -> int:
    """用真实 GitHub REST API + README 跑一份五平台新结构样稿。"""
    import base64
    from .discover import (Repo, _session as gh_session, extract_install_blocks,
                           extract_quickstart, extract_problem, extract_features,
                           extract_intro, score)
    from .rewrite import render_rewrite
    from .main import load_yaml
    from .seo import load_seo

    s = gh_session()
    data_url = f"https://api.github.com/repos/{repo_name}"
    r = s.get(data_url, timeout=25)
    if r.status_code != 200:
        print(f"FAIL: GitHub API {r.status_code} for {repo_name}", file=sys.stderr)
        return 1
    item = r.json()
    repo = Repo(
        full_name=item["full_name"], html_url=item["html_url"],
        description=item.get("description") or "", stars=int(item.get("stargazers_count") or 0),
        language=item.get("language") or "未标注",
        license=((item.get("license") or {}).get("spdx_id") or "NOASSERTION"),
        topics=item.get("topics") or [], created_at=item.get("created_at") or "",
        pushed_at=item.get("pushed_at") or "", default_branch=item.get("default_branch") or "main",
    )
    rr = s.get(f"{data_url}/readme", timeout=25)
    if rr.status_code == 200 and isinstance(rr.json(), dict):
        try:
            repo.readme = base64.b64decode(rr.json()["content"]).decode("utf-8", errors="replace")
        except Exception:
            repo.readme = ""
    cfg = load_yaml(ROOT / "config" / "settings.yaml")
    repo.install_blocks = extract_install_blocks(repo.readme)
    repo.quickstart_excerpt = extract_quickstart(repo.readme)
    repo.problem_excerpt = extract_problem(repo.readme)
    repo.features_excerpt = extract_features(repo.readme)
    repo.intro_excerpt = extract_intro(repo.readme)
    repo.score, repo.signals = score(repo, cfg["score_weights"])

    result = render_rewrite(repo, date, seo_cfg=load_seo())
    arts, topic, check = result["articles"], result["topic"], result["guard"]
    out_dir = ROOT / "drafts" / "preview_topics"
    out_dir.mkdir(parents=True, exist_ok=True)
    for platform, art in arts.items():
        (out_dir / f"{platform}.md").write_text(
            f"# {art['title']}\n\n> {art['brief']}\n\n{art['body']}\n", encoding="utf-8")
    (out_dir / "INDEX.md").write_text(
        f"# 新结构五平台样稿（{date}）\n\n"
        f"- 事实源：`{repo.full_name}`，★{repo.stars} / {repo.language} / {repo.license} / "
        f"建库 {repo.created_at[:10]} / 更新 {repo.pushed_at[:10]}\n"
        f"- 数据来源：GitHub REST API 与 README 原文，实时抓取，未手填任何数字\n"
        f"- 话题原型：`{topic['id']}`（{topic['hook_type']}），句式 #{topic['opening_index']}\n"
        f"- 防洗稿：8 字连续片段重合 "
        f"{sum(v['overlap'] for v in check['platforms'].values())} 处，"
        f"校验 {'通过' if check['ok'] else '未通过'}\n\n"
        "| 平台 | 标题 | 篇幅 |\n| --- | --- | --- |\n"
        + "\n".join(f"| {p} | {a['title']} | {a['chars']} 字 |"
                    for p, a in arts.items())
        + "\n", encoding="utf-8")
    print(json.dumps({"repo": repo.full_name, "stars": repo.stars,
                      "topic": topic, "guard_ok": check["ok"],
                      "platforms": {p: a["chars"] for p, a in arts.items()}},
                     ensure_ascii=False, indent=2))
    return 0 if check["ok"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="话题层自检 / 热榜刷新 / 样稿预览")
    ap.add_argument("--check", action="store_true", help="自检话题池与防洗稿基准")
    ap.add_argument("--refresh-hot", action="store_true", help="刷新匿名热榜信号")
    ap.add_argument("--preview", metavar="OWNER/REPO", help="用真实仓库跑五平台样稿")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    if args.refresh_hot:
        r = refresh_hot()
        if not r.get("ok"):
            print(f"FAIL: {r.get('error')}", file=sys.stderr)
            return 1
        print(json.dumps({k: r[k] for k in ("ok", "captured_at", "count", "source_url")},
                         ensure_ascii=False, indent=2))
        print(f"已写入 {HOT_STATE_FILE.relative_to(ROOT)}")
        return 0

    if args.preview:
        return _preview(args.preview, args.date)

    cfg = load_topics()
    plan = choose(args.date, cfg)
    src = "\n".join(cfg.get("reference_titles") or [])
    print(json.dumps({
        "prototypes": len(cfg.get("prototypes") or []),
        "reference_titles": len(cfg.get("reference_titles") or []),
        "reference_grams": len(ngrams(src, 8)),
        "chosen": plan.as_dict(),
        "labels_status": {k: v.get("status") for k, v in (cfg.get("labels") or {}).items()},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
