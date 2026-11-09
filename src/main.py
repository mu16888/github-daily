"""流水线编排入口：抓取 -> 打分 -> 核查 -> 成稿 -> 归档 -> 发布 -> 记台账。

用法：
  python -m src.main --dry-run              # 只出稿 + 组装发布请求，不发文
  python -m src.main --date 2026-11-09      # 指定日期目录
  python -m src.main --limit 2              # 本次出几篇
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from .compose import compose
from .discover import _session, pick
from .publish import Result, all_publishers, redact
from .schedule import mark_dispatched, stagger_plan

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "published.json"
SUMMARY_FILE = ROOT / "run-summary.json"
DEFAULT_DATE = dt.date.today().isoformat()


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "seen": {}}


def seen_repos(state: dict, window_days: int) -> set[str]:
    cutoff = dt.date.today() - dt.timedelta(days=window_days)
    out = set()
    for repo, meta in state.get("seen", {}).items():
        try:
            first = dt.date.fromisoformat(str(meta.get("first_date", ""))[:10])
        except ValueError:
            out.add(repo)
            continue
        if first >= cutoff:
            out.add(repo)
    return out


def quota_used(state: dict, platform: str, date: str, model: str) -> int:
    """统计该平台今日（或滚动 24h）已成功发布的篇数。

    只数 published 记录；失败/跳过不占额度。
    """
    used = 0
    now = dt.datetime.now(dt.timezone.utc)
    for meta in state.get("seen", {}).values():
        rec = (meta.get("platforms") or {}).get(platform)
        if not rec:
            continue
        at = str(rec.get("at") or "")
        if model == "rolling_24h":
            try:
                t = dt.datetime.fromisoformat(at)
                if (now - t).total_seconds() < 24 * 3600:
                    used += 1
            except ValueError:
                continue
        elif at[:10] == date:
            used += 1
    return used


def archive(article: dict, date: str) -> list[str]:
    folder = ROOT / "drafts" / date
    folder.mkdir(parents=True, exist_ok=True)
    slug = article["repo"].replace("/", "__")
    md_path = folder / f"{slug}.md"
    html_path = folder / f"{slug}.html"
    md_path.write_text(article["markdown"], encoding="utf-8")
    html_path.write_text(article["html"], encoding="utf-8")
    return [str(md_path.relative_to(ROOT)), str(html_path.relative_to(ROOT))]


def run(args: argparse.Namespace) -> dict[str, Any]:
    settings = load_yaml(ROOT / "config" / "settings.yaml")
    platforms = load_yaml(ROOT / "config" / "platforms.yaml")
    if args.dry_run:
        settings["publish"]["dry_run"] = True
    if args.no_publish:
        settings["publish"]["enabled"] = False

    state = load_state()
    already = seen_repos(state, int(settings["daily"]["history_window_days"]))
    print(f"[1/5] 台账已有 {len(already)} 个项目在去重窗口内")

    session = _session()
    repos = pick(session, settings, already, limit=args.limit)
    print(f"[2/5] 入选 {len(repos)} 个项目")
    note = ""
    if not repos:
        note = "没有达到分数门槛的新项目，本次不发文（不编凑内容）"
        print(f"      {note}")

    # 只有「闸门放行的那一棒」（CI 传 --dispatched）才占住当天唯一名额并立即落盘：
    # (a) 后续 15 分钟一次的唤醒直接空跑，不重复抓 GitHub / 不重复发文；
    # (b) 即使成稿或发布阶段抛异常，也不会因台账没写而重复发文。
    # 抓候选本身失败时不写，留给后面的唤醒重试。本地直接跑不传该参数，
    # 因此本地演练完全不碰台账，也不会误把「今天已派发」推上去挡住云端。
    if getattr(args, "dispatched", False):
        mark_dispatched(state, args.date, "dry_run" if settings["publish"]["dry_run"] else "live")
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    publishers = all_publishers(platforms, settings) if settings["publish"]["enabled"] else []
    print(f"[3/5] 启用 {len(publishers)} 个发布适配器 | dry_run={settings['publish']['dry_run']}")

    try:
        schedule_date = dt.date.fromisoformat(args.date)
    except ValueError:
        schedule_date = dt.date.today()
    plan = stagger_plan(schedule_date, settings.get("schedule", {}), [p.name for p in publishers])

    drafts, results = [], []
    for repo in repos:
        article = compose(repo, args.date, settings)
        files = archive(article, args.date)
        drafts.append({
            "repo": repo.full_name, "title": article["title"],
            "platform_titles": article["titles"], "keywords": article["keywords"],
            "score": repo.score, "files": files,
        })
        print(f"      成稿 {repo.full_name} (score={repo.score}) -> {files[0]}")

        # 演练不产生任何持久副作用：否则多跑几次 dry_run 就把候选写进去重台账，
        # 真发时反而没项目可选。只有正式运行才记「已推荐」。
        if not settings["publish"]["dry_run"]:
            state["seen"].setdefault(repo.full_name, {"first_date": args.date, "platforms": {}})
        quota = settings.get("quota", {})
        per_day = quota.get("per_day", {})
        model = quota.get("model", "calendar_day")
        for pub in publishers:
            cap = int(per_day.get(pub.name, 1))
            used = quota_used(state, pub.name, args.date, model)
            if used >= cap:
                r = Result(pub.name, "skipped", detail=f"今日配额已满（{used}/{cap}，{model}），跳过以防重复发文")
            else:
                # 三个平台错峰发出，别让同一秒三连发（演练与配额跳过时不等待）
                delay = plan.get(pub.name, 0)
                if delay and not settings["publish"]["dry_run"]:
                    print(f"      平台错峰：等待 {delay}s 后发 {pub.name}")
                    time.sleep(delay)
                r = pub.publish(article)
            results.append(r.as_dict())
            print(f"      [{r.status:9s}] {r.platform}: {r.detail[:120]}")
            # drafted 也要占住当天名额：草稿虽未公开，但重复建同样会刷屏。
            if r.status in ("published", "drafted") and not settings["publish"]["dry_run"]:
                state["seen"][repo.full_name]["platforms"][r.platform] = {
                    "url": r.url,
                    "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "status": r.status,
                }

    print("[4/5] 写台账与运行摘要")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "date": args.date,
        "picked": len(repos),
        "dry_run": bool(settings["publish"]["dry_run"]),
        "publish_enabled": bool(settings["publish"]["enabled"]),
        "quota": settings.get("quota", {}).get("per_day", {}),
        "drafts": drafts,
        "publish": results,
        "published_count": sum(1 for r in results if r["status"] == "published"),
        "drafted_count": sum(1 for r in results if r["status"] == "drafted"),
        "skipped_count": sum(1 for r in results if r["status"] == "skipped"),
        "failed_count": sum(1 for r in results if r["status"] == "failed"),
    }
    if note:
        summary["note"] = note
    SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[5/5] 完成")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="每日 GitHub 小白友好项目介绍流水线")
    ap.add_argument("--date", default=DEFAULT_DATE, help="归档日期 YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=None, help="本次出稿数量")
    ap.add_argument("--dry-run", action="store_true", help="只组装请求，不调用发布接口")
    ap.add_argument("--no-publish", action="store_true", help="完全跳过发布层，只出稿")
    ap.add_argument("--dispatched", action="store_true",
                    help="CI 闸门放行的当日一棒：写 schedule.last_dispatched，防止重复派发")
    args = ap.parse_args()
    if args.limit is None:
        args.limit = int(load_yaml(ROOT / "config" / "settings.yaml")["daily"]["picks_per_day"])
    try:
        s = run(args)
    except Exception as e:
        # 抓取/成稿阶段失败必须让 CI 变红，不静默吞掉；
        # 同时覆盖旧的 run-summary.json，避免失败运行留下上一次的成功摘要被误读。
        safe_error = redact(f"{type(e).__name__}: {e}")
        print(f"FATAL: {safe_error}", file=sys.stderr)
        SUMMARY_FILE.write_text(
            json.dumps({"date": args.date, "status": "failed",
                        "error": safe_error}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return 1
    if s.get("failed_count"):
        print(f"WARN: {s['failed_count']} 个平台发布失败，详见 run-summary.json；出稿与归档不受影响。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
