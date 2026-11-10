"""本机运行入口：抓取 -> 成稿 -> 发布 -> 记台账，全部在这台电脑上跑。

与云端 `python -m src.main` 的区别：

| 维度 | 云端（GitHub Actions） | 本机（src.local） |
| --- | --- | --- |
| 凭据来源 | GitHub Secrets（只写不可读） | config/local_secrets.json + 沐风博客公众号配置 |
| 出口 IP | runner 动态 IP（每次不同） | 本机固定 IP 183.209.232.176 |
| 平台 | 掘金 / 掘金 / CSDN（Cookie 接口） | + 公众号（官方接口）+ 知乎/头条（浏览器通道） |
| 台账 | state/published.json | state/local-ledger.json（独立，不互相覆盖） |
| 触发 | cron 每 15 分钟唤醒 + 时间闸门 | 计划任务开机自启 + 内部定时循环 |

用法：
    python -m src.local --status              # 体检：开关 / 凭据 / 平台可用性
    python -m src.local --dry-run             # 跑一次：出稿 + 组装请求，不推送
    python -m src.local --run                 # 跑一次：真发（受 dry_run 闸门约束）
    python -m src.local --daemon              # 常驻：每天到点自动跑（计划任务用这个）
    python -m src.local --login zhihu         # 首次登录：打开浏览器让锋哥扫码
    python -m src.local --preview-days 7      # 预览未来 7 天的发布时间
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml

import requests

from .compose import compose, md_to_html
from .discover import _session, pick
from .local_publish import BrowserPublisher, WechatPublisher
from .local_secrets import load_local_secrets, secrets_status
from .blog_source import pick_for_track
from .publish import (CsdnPublisher, JuejinPublisher, Result, ZhihuPublisher,
                       all_publishers, redact)
from .schedule import stagger_plan, target_for

ROOT = Path(__file__).resolve().parent.parent
LOCAL_CFG = ROOT / "config" / "local.yaml"
LOCAL_SUMMARY = ROOT / "run-summary-local.json"
UTC = dt.timezone.utc


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def local_cfg() -> dict:
    """本机配置 = config/local.yaml + config/tracks.yaml 合并。

    赛道定义放在独立的 tracks.yaml（平台归属、内容标签、每日配额、人工发说明），
    合并进来方便各处统一用 lcfg["tracks"] 取。
    """
    cfg = dict(load_yaml(LOCAL_CFG) or {})
    tracks_file = ROOT / "config" / "tracks.yaml"
    if tracks_file.exists():
        try:
            cfg["tracks"] = load_yaml(tracks_file) or {}
        except Exception:
            cfg["tracks"] = {}
    return cfg


def ledger_path(cfg: dict) -> Path:
    p = ROOT / str(cfg.get("local", {}).get("ledger", "state/local-ledger.json"))
    return p


def load_ledger(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"version": 1, "seen": {}}


def fetch_remote_ledger(timeout: int = 60) -> dict:
    """读远程 main 上的 state/published.json（云端台账）。

    为什么必须读：本机工作区的 state/published.json 可能比远程旧
    （本地 checkout 过、或云端 workflow 后来才提交）。不合并的话，
    本机会把云端已经发过的项目当成「没发过」再发一遍——同一个项目
    在两个平台各发两次，是最典型的重复发文事故。

    读不到就返回空 dict：宁可少去重（可能重复），也不能因为
    远程不可达就整个流程崩掉。
    """
    import subprocess
    try:
        # 先 fetch，保证 origin/main 是最新的；失败不影响主流程
        subprocess.run(["git", "fetch", "origin", "main"],
                       cwd=str(ROOT), capture_output=True, timeout=timeout)
        r = subprocess.run(["git", "show", "origin/main:state/published.json"],
                           cwd=str(ROOT), capture_output=True, timeout=timeout)
        if r.returncode == 0 and r.stdout:
            data = json.loads(r.stdout.decode("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def seen_repos(state: dict, window_days: int, extra: dict | None = None) -> set[str]:
    """去重集合 = 本机台账 + 云端台账（只读合并）。

    云端发过的项目本机不重复发，避免同一天两处发同一篇。
    """
    out: set[str] = set()
    cutoff = dt.date.today() - dt.timedelta(days=window_days)
    for src in (state, extra or {}):
        for repo, meta in (src.get("seen") or {}).items():
            try:
                first = dt.date.fromisoformat(str(meta.get("first_date", ""))[:10])
            except ValueError:
                out.add(repo)
                continue
            if first >= cutoff:
                out.add(repo)
    return out


def quota_used(state: dict, platform: str, date: str, model: str = "calendar_day") -> int:
    used = 0
    now = dt.datetime.now(UTC)
    for meta in (state.get("seen") or {}).values():
        rec = (meta.get("platforms") or {}).get(platform)
        if not rec:
            continue
        at = str(rec.get("at") or "")
        if model == "rolling_24h":
            try:
                if (now - dt.datetime.fromisoformat(at)).total_seconds() < 24 * 3600:
                    used += 1
            except ValueError:
                continue
        elif at[:10] == date:
            used += 1
    return used


def list_tracks() -> int:
    """列出赛道划分、平台归属、内容源，以及各平台的发文能力边界。"""
    lcfg = local_cfg()
    tracks = lcfg.get("tracks") or load_yaml(ROOT / "config" / "tracks.yaml")
    plat = lcfg.get("platforms") or {}
    manual = tracks.get("manual_only") or {}

    print("=" * 72)
    print(f"  {tracks.get('name', '沐风')} · 赛道划分")
    print("=" * 72)
    for tname, tcfg in (tracks.get("tracks") or {}).items():
        print(f"\n【赛道 {tname}】{tcfg.get('title', '')}")
        print(f"  定位: {tcfg.get('desc', '')}")
        print(f"  平台: {', '.join(tcfg.get('platforms') or [])}")
        print(f"  内容标签: {', '.join(tcfg.get('blog_tags') or []) or '—'}")
        if tcfg.get("include_github_daily"):
            print("  内容源: + GitHub 开源项目介绍（github-daily）")
        q = tcfg.get("daily_quota") or {}
        if q:
            print(f"  每日配额: {', '.join(f'{k}={v}' for k, v in q.items())}")

    print("\n" + "=" * 72)
    print("  平台归属与发文方式")
    print("=" * 72)
    for name, pc in (plat or {}).items():
        track = pc.get("track", "—")
        mode = pc.get("mode", "api")
        man = manual.get(name) or {}
        way = {"api": "接口", "browser": "浏览器"}.get(mode, mode)
        flag = "启用" if pc.get("enabled") else "停用"
        print(f"\n  {name}（{track} / {way} / {flag}）")
        if man:
            print(f"    ⚠ {man.get('reason', '')}")
            print(f"    → {man.get('output', '')}")
    print()
    return 0


def build_publishers(lcfg: dict, settings: dict, platforms_cfg: dict,
                     dry_run: bool, track: str | None = None) -> list[Any]:
    """按 local.yaml 的平台开关组装发布器。

    掘金 / 公众号走接口；CSDN / 知乎 / 头条走浏览器通道
    （见 csdn_browser.py / zhihu_browser.py / toutiao_browser.py 的说明：
    它们公开发布必须走网页编辑器，接口只能建草稿）。

    track 不为空时，只组装该赛道的平台（赛道 A=技术/AI，赛道 B=餐饮）。
    """
    plat = lcfg.get("platforms") or {}
    secrets = load_local_secrets()
    out: list[Any] = []

    def in_track(name: str) -> bool:
        if not track:
            return True
        return (plat.get(name, {}) or {}).get("track") == track

    if plat.get("juejin", {}).get("enabled") and in_track("juejin"):
        cfg = platforms_cfg["platforms"].get("juejin", {})
        out.append(JuejinPublisher(cfg, settings, secrets, dry_run))
    if plat.get("csdn", {}).get("enabled") and in_track("csdn"):
        cfg = platforms_cfg["platforms"].get("csdn", {})
        if str(plat.get("csdn", {}).get("mode", "browser")).lower() == "browser":
            from .csdn_browser import CsdnBrowserPublisher
            out.append(CsdnBrowserPublisher(
                browser_cfg=lcfg.get("browser") or {}, root=ROOT))
        else:
            out.append(CsdnPublisher(cfg, settings, secrets, dry_run))
    if plat.get("wechat", {}).get("enabled") and in_track("wechat"):
        out.append(WechatPublisher(
            {}, settings, secrets, dry_run,
            wechat_cfg=lcfg.get("wechat") or {},
            root=ROOT,
        ))
    if plat.get("zhihu", {}).get("enabled") and in_track("zhihu"):
        from .zhihu_browser import ZhihuBrowserPublisher
        out.append(ZhihuBrowserPublisher(
            browser_cfg=lcfg.get("browser") or {}, root=ROOT))
    if plat.get("toutiao", {}).get("enabled") and in_track("toutiao"):
        from .toutiao_browser import ToutiaoBrowserPublisher
        out.append(ToutiaoBrowserPublisher(
            browser_cfg=lcfg.get("browser") or {}, root=ROOT))
    return out


def platform_view(article: dict, platform: str, source: str) -> dict:
    """rewrite 模式下把新结构稿映射成发布器认识的字段（与 src/main.py 同逻辑）。"""
    if source != "rewrite":
        return article
    art = (article.get("rewrite") or {}).get(platform)
    if not art:
        return article
    view = dict(article)
    view["titles"] = {**article.get("titles", {}), platform: art["title"]}
    view["briefs"] = {**article.get("briefs", {}), platform: art["brief"]}
    if art.get("tags"):
        view["platform_tags"] = {**article.get("platform_tags", {}), platform: art["tags"]}
    view["markdown"] = art["body"]
    view["html"] = md_to_html(art["body"])
    return view


def archive(article: dict, date: str, source: str) -> list[str]:
    folder = ROOT / "drafts" / date
    folder.mkdir(parents=True, exist_ok=True)
    slug = str(article.get("repo", "unknown")).replace("/", "__")
    md_path = folder / f"{slug}.md"
    md_path.write_text(article["markdown"], encoding="utf-8")
    out = [str(md_path.relative_to(ROOT))]
    if source == "rewrite":
        rfolder = folder / "rewrite"
        rfolder.mkdir(parents=True, exist_ok=True)
        for platform, art in (article.get("rewrite") or {}).items():
            p = rfolder / f"{slug}.{platform}.md"
            p.write_text(f"# {art['title']}\n\n> {art['brief']}\n\n{art['body']}\n",
                         encoding="utf-8")
            out.append(str(p.relative_to(ROOT)))
    return out


def run_once(date: str, force: bool = False, limit: int | None = None,
             dry_run_override: bool | None = None,
             track: str | None = None) -> dict[str, Any]:
    """跑一次完整流水线。

    force=True 时忽略时间闸门（手动补发用）。
    track 指定赛道时只发该赛道的平台；track="restaurant" 时内容源改为
    沐风博客的餐饮线（而不是 GitHub 开源项目）。
    """
    lcfg = local_cfg()
    settings = load_yaml(ROOT / "config" / "settings.yaml")
    platforms_cfg = load_yaml(ROOT / "config" / "platforms.yaml")
    tracks_cfg = lcfg.get("tracks") or load_yaml(ROOT / "config" / "tracks.yaml")
    track_cfg = (tracks_cfg.get("tracks") or {}).get(track or "", {})

    local = lcfg.get("local") or {}
    if not local.get("enabled", True):
        print("[skip] local.enabled=false，本机不出稿不推送")
        return {"status": "skipped", "reason": "local.enabled=false"}

    dry_run = bool(local.get("dry_run", True))
    if dry_run_override is not None:
        dry_run = dry_run_override
    source = str(local.get("content_source", "legacy")).strip().lower()
    if source not in ("legacy", "rewrite"):
        source = "legacy"

    lpath = ledger_path(lcfg)
    state = load_ledger(lpath)
    # 云端台账：以远程 main 为准（本地那份可能过期）。读不到就退回本地文件。
    cloud = fetch_remote_ledger() or load_ledger(ROOT / "state" / "published.json")

    already = seen_repos(state, int(settings["daily"]["history_window_days"]), cloud)
    print(f"[1/5] 本机台账 {len(state.get('seen') or {})} 条 | 云端台账 "
          f"{len(cloud.get('seen') or {})} 条 | 去重集合 {len(already)} 个项目")

    session = _session()
    publishers = build_publishers(lcfg, settings, platforms_cfg, dry_run, track=track)
    tracks = tracks_cfg
    print(f"[2/5] 发布器 {len(publishers)} 个 | dry_run={dry_run} | 正文={source}")
    for tname, tcfg_ in (tracks.get("tracks") or {}).items():
        names = [p.name for p in publishers
                 if (lcfg.get("platforms", {}).get(p.name, {}) or {}).get("track") == tname]
        if names:
            print(f"      赛道[{tcfg_.get('title', tname)}] → {', '.join(names)}")

    plan = stagger_plan(dt.date.fromisoformat(date), settings.get("schedule", {}),
                        [p.name for p in publishers])

    drafts, results = [], []
    # 赛道 B：内容来自博客餐饮线；赛道 A：来自 GitHub 开源项目
    if track and not track_cfg.get("include_github_daily", True):
        plats = [p.name for p in publishers]
        articles = pick_for_track(track_cfg, plats,
                                  limit=limit or int(local.get("picks_per_day", 1)))
        print(f"[3/5] 赛道[{track_cfg.get('title', track)}] 从博客取稿 {len(articles)} 篇")
        repos = []
    else:
        repos = pick(session, settings, already,
                     limit=limit or int(local.get("picks_per_day", 1)))
        print(f"[3/5] 入选 {len(repos)} 个项目")
        articles = []

    for repo in repos:
        article = compose(repo, date, settings)
        article["repo"] = repo.full_name
        articles.append(article)

    for article in articles:
        repo_name = article.get("repo", "unknown")
        files = archive(article, date, source)
        drafts.append({
            "repo": repo_name,
            "title": article["title"],
            "platform_titles": article["titles"],
            "keywords": article["keywords"],
            "score": article.get("score", 0),
            "files": files,
            "content_source": source,
        })
        print(f"      成稿 {repo_name} -> {files[0]}")

        if not dry_run:
            state["seen"].setdefault(repo_name,
                                     {"first_date": date, "platforms": {}})
        for pub in publishers:
            cap = int((settings.get("quota", {}).get("per_day", {}) or {}).get(pub.name, 1))
            used = quota_used(state, pub.name, date)
            if used >= cap:
                r = Result(pub.name, "skipped",
                           detail=f"今日配额已满（{used}/{cap}），跳过以防重复发文")
            else:
                delay = plan.get(pub.name, 0)
                if delay and not dry_run:
                    print(f"      错峰：等待 {delay}s 后发 {pub.name}")
                    time.sleep(delay)
                # 浏览器通道的发布器签名不同（自己管标题/摘要/标签），单独分支
                if hasattr(pub, "publish_browser"):
                    r = pub.publish_browser(
                        platform_view(article, pub.name, source),
                        title=(article.get("titles") or {}).get(pub.name, ""),
                        body=(article.get("rewrite") or {}).get(pub.name, {}).get("body")
                        or article.get("markdown", ""),
                        brief=(article.get("briefs") or {}).get(pub.name, ""),
                        tags=(article.get("platform_tags") or {}).get(pub.name, ""),
                    )
                else:
                    r = pub.publish(platform_view(article, pub.name, source))
            results.append(r.as_dict())
            print(f"      [{r.status:9s}] {r.platform}: {r.detail[:120]}")
            if r.status in ("published", "drafted") and not dry_run:
                state["seen"][repo_name]["platforms"][pub.name] = {
                    "url": r.url,
                    "at": dt.datetime.now(UTC).isoformat(timespec="seconds"),
                    "status": r.status,
                }

    lpath.parent.mkdir(parents=True, exist_ok=True)
    lpath.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "date": date,
        "mode": "local",
        "picked": len(repos),
        "dry_run": dry_run,
        "content_source": source,
        "drafts": drafts,
        "publish": results,
        "published_count": sum(1 for r in results if r["status"] == "published"),
        "drafted_count": sum(1 for r in results if r["status"] == "drafted"),
        "skipped_count": sum(1 for r in results if r["status"] == "skipped"),
        "failed_count": sum(1 for r in results if r["status"] == "failed"),
    }
    LOCAL_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print("[4/5] 写本机台账与运行摘要")
    print("[5/5] 完成")
    return summary


def _target_now(cfg: dict, date: dt.date) -> dt.datetime:
    """把 schedule 的目标时刻换算到本机本地时间（UTC+8）。

    返回 **naive** 本地时间：本机守护进程全程用本地时间做比较，
    避免 aware/naive 混用抛 TypeError。
    """
    t = target_for(date, cfg)
    return t.astimezone(dt.timezone(dt.timedelta(hours=8))).replace(tzinfo=None)


def _setup_file_log() -> None:
    """把 stdout/stderr 同时写到 logs/daemon-YYYY-MM-DD.log。

    计划任务用 pythonw.exe 跑（不弹控制台），没有这层日志就完全看不到
    它到底干了什么。输出同时保留在控制台，手动跑时照常可见。

    切目录的原因：`python -m src.local` 依赖 cwd 在仓库根，
    而计划任务默认从 C:\\Windows\\System32 启动。
    """
    try:
        os.chdir(ROOT)
    except Exception:
        pass
    try:
        log_dir = ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        f = open(log_dir / f"daemon-{dt.date.today().isoformat()}.log",
                 "a", encoding="utf-8", buffering=1)
        sys.stdout = _Tee(sys.stdout, f)
        sys.stderr = _Tee(sys.stderr, f)
    except Exception:
        pass      # 日志失败不能影响主流程


class _Tee:
    """同时写到两个流。"""

    def __init__(self, a, b):
        self.a = a
        self.b = b

    def write(self, data):
        try:
            self.a.write(data)
        except Exception:
            pass
        try:
            self.b.write(data)
        except Exception:
            pass

    def flush(self):
        for s in (self.a, self.b):
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def daemon(once: bool = False) -> int:
    """常驻模式：每天在「当天目标时刻」跑一次。

    与云端的差别：云端靠 cron 每 15 分钟唤醒（runner 不能常驻），
    本机可以直接 sleep 到点。错过了目标时刻（电脑当时关机/休眠），
    在 catchup 窗口内补发；超窗就跳过当天——宁可漏发也不半夜发文。
    """
    _setup_file_log()
    lcfg = local_cfg()
    settings = load_yaml(ROOT / "config" / "settings.yaml")
    sched = settings.get("schedule", {})
    catchup_minutes = int((lcfg.get("catchup") or {}).get("window_minutes", 180))
    lpath = ledger_path(lcfg)
    print(f"[daemon] 启动 | 目标窗口 {sched.get('window_start')}–{sched.get('window_end')}"
          f" | 补发窗口 {catchup_minutes} 分钟 | 台账 {lpath.name}")

    while True:
        now = dt.datetime.now()
        today = now.date()
        target = _target_now(sched, today)
        state = load_ledger(lpath)
        done = (state.get("schedule") or {}).get("last_dispatched")

        if done == today.isoformat():
            wait_until = dt.datetime.combine(today + dt.timedelta(days=1),
                                             dt.time(hour=3, minute=0))
            print(f"[daemon] 今天已派发，休眠至 {wait_until:%m-%d %H:%M}")
            _sleep_until(wait_until)
            continue

        if now < target:
            wait = (target - now).total_seconds()
            print(f"[daemon] 目标 {target:%m-%d %H:%M:%S}，等待 {int(wait)}s")
            _sleep_until(target)
            now = dt.datetime.now()

        late = (now - target).total_seconds() / 60
        if late > catchup_minutes:
            print(f"[daemon] 已过目标 {int(late)} 分钟，超出补发窗口，跳过今天")
            _sleep_until(dt.datetime.combine(today + dt.timedelta(days=1),
                                             dt.time(hour=3, minute=0)))
            continue

        if late > 1:
            print(f"[daemon] 迟 {int(late)} 分钟触发（在补发窗口内）")
        try:
            run_once(today.isoformat())
            state = load_ledger(lpath)
            state.setdefault("schedule", {})
            state["schedule"]["last_dispatched"] = today.isoformat()
            state["schedule"]["last_at"] = dt.datetime.now(UTC).isoformat(timespec="seconds")
            lpath.parent.mkdir(parents=True, exist_ok=True)
            lpath.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        except Exception as e:
            print(f"[daemon] 运行失败: {redact(f'{type(e).__name__}: {e}')}", file=sys.stderr)
        if once:
            return 0
        _sleep_until(dt.datetime.combine(today + dt.timedelta(days=1),
                                         dt.time(hour=3, minute=0)))
    return 0


def _sleep_until(when: dt.datetime) -> None:
    """分片休眠：机器休眠/唤醒后重新校准，避免睡过头。"""
    while True:
        remain = (when - dt.datetime.now()).total_seconds()
        if remain <= 0:
            return
        time.sleep(min(remain, 300))


def status() -> int:
    lcfg = local_cfg()
    settings = load_yaml(ROOT / "config" / "settings.yaml")
    local = lcfg.get("local") or {}
    st = secrets_status()

    print("=== 本机运行状态 ===")
    print(f"local.enabled        = {local.get('enabled', True)}")
    print(f"local.dry_run        = {local.get('dry_run', True)}"
          f"   ← true=只出稿不推送；改 false 才真发")
    print(f"content_source       = {local.get('content_source', 'legacy')}")
    print(f"台账                 = {ledger_path(lcfg).relative_to(ROOT)}")
    print(f"调度窗口(北京)      = {settings.get('schedule', {}).get('window_start')}"
          f"–{settings.get('schedule', {}).get('window_end')}")

    print("\n=== 凭据（只看有没有，不回显值）===")
    print(f"凭据文件             = {st['file']}  存在={st['file_exists']}")
    for k, v in st["keys"].items():
        print(f"  {k:20s} {'有' if v else '缺'}")
    print(f"  {'公众号配置':20s} {'有' if st['wechat'] else '缺（沐风博客/config/wechat_config.json）'}")

    print("\n=== 平台开关 ===")
    for name, p in (lcfg.get("platforms") or {}).items():
        print(f"  {name:10s} {'开' if p.get('enabled') else '关'}")

    print("\n=== 未来 7 天发布时间 ===")
    sched = settings.get("schedule", {})
    for i in range(7):
        d = dt.date.today() + dt.timedelta(days=i)
        t = _target_now(sched, d)
        plan = stagger_plan(d, sched, list((lcfg.get("platforms") or {}).keys()))
        seq = " / ".join(f"{(t + dt.timedelta(seconds=v)):%H:%M:%S}" for v in plan.values())
        print(f"  {d.isoformat()} 周{'一二三四五六日'[d.weekday()]}  {t:%H:%M:%S}   {seq}")
    return 0


def probe_credentials() -> int:
    """只读探测本机凭据是否有效，不发任何文章。

    用途：录完 Cookie 后先验证，别等真发时才发现登录态过期。
    每个平台用「查询类」接口，不碰任何写入端点。
    """
    from .local_secrets import load_local_secrets
    secrets = load_local_secrets()
    platforms_cfg = load_yaml(ROOT / "config" / "platforms.yaml")
    lcfg = local_cfg()
    print("=== 凭据探测（只读，不发文章）===\n")

    # 掘金：list_by_user 列出自己的文章，能返回说明 Cookie 有效
    jc = clean_cookie_local(secrets.get("JUEJIN_COOKIE", ""))
    ju = clean_param_local(secrets.get("JUEJIN_UUID", ""))
    if not jc:
        print("掘金   凭据缺    → 跑 python -m src.local --login juejin（浏览器登录，自动导出）")
    elif not ju:
        print("掘金   uuid 缺   → 重新跑 python -m src.local --login juejin")
    else:
        try:
            c = platforms_cfg["platforms"]["juejin"]
            q = c["query"]
            # 探测用「查当前用户信息」这个只读接口。
            # 端点是从浏览器实际请求里抓的（2026-11-10 实测）：
            #   GET /user_api/v1/user/get  → err_no=0 并返回 user_name
            # 早先 config 里记的 list_by_user 已不存在（err_no=2 路由不存在），
            # 用它判断会把好凭据误报成坏的。
            url = (f"{c['api_base']}/user_api/v1/user/get"
                   f"?aid={q['aid']}&uuid={ju}&spider={q['spider']}")
            r = requests.get(url, headers={"Cookie": jc, "User-Agent": "Mozilla/5.0",
                                           "Referer": "https://juejin.cn/editor/drafts/new"},
                             timeout=20)
            d = r.json() if r.content else {}
            err = d.get("err_no")
            ok = r.status_code == 200 and err == 0
            who = ""
            if ok and isinstance(d.get("data"), dict):
                who = str(d["data"].get("user_name") or "")
            msg = str(d.get("err_msg") or "")[:60]
            print(f"掘金   {'有效' if ok else '异常'}  http={r.status_code} err_no={err}"
                  f"{(' 账号=' + who) if who else ' ' + msg}")
        except Exception as e:
            print(f"掘金   探测异常  {type(e).__name__}: {str(e)[:80]}")

    # CSDN：查用户信息（只读）
    cc = clean_cookie_local(secrets.get("CSDN_COOKIE", ""))
    if not cc:
        print("CSDN   凭据缺    → 跑 python -m src.local --login csdn（扫码登录，自动导出）")
    else:
        try:
            r = requests.get("https://blog.csdn.net/community/home-api/v1/get-business-list",
                             headers={"Cookie": cc, "User-Agent": "Mozilla/5.0"},
                             params={"page": 1, "size": 1, "businessType": "blog"},
                             timeout=20)
            ok = r.status_code == 200
            print(f"CSDN   {'连通' if ok else '异常'}  http={r.status_code} "
                  f"len={len(r.content)}")
        except Exception as e:
            print(f"CSDN   探测异常  {type(e).__name__}: {str(e)[:80]}")

    # 公众号：取 token（只读，不建稿）
    from .local_secrets import wechat_config
    w = wechat_config()
    if not w:
        print("公众号  配置缺    → 找不到沐风博客/config/wechat_config.json")
    else:
        try:
            r = requests.get("https://api.weixin.qq.com/cgi-bin/token",
                             params={"grant_type": "client_credential",
                                     "appid": w["appid"], "secret": w["secret"]},
                             timeout=15)
            d = r.json()
            if "access_token" in d:
                print("公众号  有效      token 取到了，IP 白名单已放行本机")
            else:
                code = d.get("errcode")
                hint = ""
                if code == 40164:
                    hint = " → 开发者平台加本机 IP 白名单"
                elif code in (40001, 40125):
                    hint = " → AppSecret 不对"
                print(f"公众号  无效      errcode={code}{hint}")
        except Exception as e:
            print(f"公众号  探测异常  {type(e).__name__}: {str(e)[:80]}")

    # 知乎 / 头条：登录态在浏览器 profile 里，只报 profile 状态
    prof = ROOT / str((lcfg.get("browser") or {}).get("profile_dir", "state/browser-profile"))
    print(f"\n知乎/头条  浏览器 profile: {'已建立' if prof.exists() and any(prof.iterdir()) else '未建立'}"
          f"（{prof}）")
    print("           需要发这两家时再跑：python -m src.local --login zhihu")
    return 0


def clean_cookie_local(raw: str) -> str:
    from .publish import clean_cookie
    return clean_cookie(raw or "")


def clean_param_local(raw: str) -> str:
    from .publish import clean_param
    return clean_param(raw or "")


def login(platform: str) -> int:
    """扫码登录一次，自动把登录态导成本机凭据。

    这是「一条龙」的关键一环：锋哥只管扫码，程序自己从浏览器里
    把 Cookie 读出来写进凭据文件 —— 不用手工去 DevTools 抄。
    登录一次长期有效：登录态存在独立 profile 里，每天跑直接复用。
    """
    from .browser_creds import FIELD_MAP, capture, save_to_secrets
    lcfg = local_cfg()
    if platform not in FIELD_MAP:
        print(f"[错误] 不认识的平台: {platform}；可选 {', '.join(FIELD_MAP)}")
        return 2

    print(f"=== 登录 {platform} ===")
    res = capture(platform, lcfg.get("browser") or {},
                  timeout=int((lcfg.get("browser") or {}).get("login_timeout_seconds", 600)))
    if not res["logged_in"]:
        print("[login] 没检测到登录成功（可能没登进去，或页面结构变了）。"
              "登录态不会被写入，凭据保持原样。")
        return 1

    values = {}
    for kind, key in FIELD_MAP[platform].items():
        v = (res.get(kind) or "").strip()
        if v:
            values[key] = v
    # 判断"拿到 cookie 了没有"要用该平台自己的字段名。
    # ⚠️ 2026-11-10 bug：这里原来写成 if/else 三元（juejin→CSDN_COOKIE→else ZHIHU_COOKIE），
    # 头条走 else 分支去找 ZHIHU_COOKIE，而它实际写的是 TOUTIAO_COOKIE，
    # 于是头条明明登录成功、cookie 也读到了，却被误判成「没读到 Cookie」。
    # 现在直接用 FIELD_MAP 里的 cookie 字段名判断，不再硬编码。
    cookie_key = FIELD_MAP[platform].get("cookie", "")
    if not values.get(cookie_key):
        print(f"[login] 登录成功了但没读到 Cookie（期望字段 {cookie_key}），"
              f"平台可能用了非标准存储。不写入，避免存脏数据。")
        return 1

    path = save_to_secrets(values)
    print(f"[login] 登录成功，已导出 {res['cookies_found']} 个 cookie 字段"
          f"（浏览器里共 {res['total_cookies']} 个）")
    for k in values:
        print(f"[login]   写入 {k}")
    if platform == "juejin" and not values.get("JUEJIN_UUID"):
        print("[login]   ⚠ 没抓到 uuid，掘金接口还需要它。")
        print("[login]     在掘金随便打开一篇文章，地址栏里的 uuid= 后面那串，")
        print("[login]     复制整条网址后跑：python -m src.local --set-uuid juejin")
    print(f"[login] 凭据已写入 {path.name}（已被 .gitignore 挡住，不入仓库）")
    print(f"[login] 验证：python -m src.local --probe")
    return 0


# 各平台凭据从剪贴板录入时，需要哪些字段
CLIPBOARD_FIELDS = {
    "juejin": ["JUEJIN_COOKIE", "JUEJIN_UUID"],
    "csdn": ["CSDN_COOKIE"],
    "zhihu": ["ZHIHU_COOKIE"],
}


def set_credential(platform: str) -> int:
    """从剪贴板读凭据写进本机凭据文件，读完立刻清空剪贴板。

    这样锋哥不用把 Cookie 粘到聊天框里 —— 登录态不进对话记录、
    不进 shell 历史、不进 git。
    """
    from .clipboard import clear_clipboard, read_clipboard
    from .local_secrets import SECRETS_FILE

    fields = CLIPBOARD_FIELDS.get(platform)
    if not fields:
        print(f"[错误] 不认识的平台: {platform}；可选 {', '.join(CLIPBOARD_FIELDS)}")
        return 2

    raw = read_clipboard()
    if not raw.strip():
        print("[错误] 剪贴板是空的。先复制好再跑这条命令。")
        return 1
    if len(raw) > 20000:
        print("[错误] 剪贴板内容过长，不像 Cookie。")
        return 1

    from .publish import clean_cookie, clean_param
    if len(fields) == 1:
        value = clean_cookie(raw)
        label = fields[0]
    else:
        # 双字段平台（掘金）：先按 Cookie 处理
        value = clean_cookie(raw)
        label = fields[0]

    if not value:
        print("[错误] 清洗后内容为空。确认复制的是完整的 Cookie 请求头那一行。")
        return 1

    data = {}
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    data[label] = value
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

    # 立刻抹掉剪贴板
    cleared = clear_clipboard()
    n = len(value.split(";"))
    print(f"[ok] {label} 已写入 {SECRETS_FILE.name}（{n} 个字段，{len(value)} 字符）")
    print(f"[ok] 剪贴板已{'清空' if cleared else '未清空（请手动清）'}")
    if len(fields) > 1:
        print(f"[下一步] 还需要 {fields[1]}：")
        print(f"          在掘金编辑器里随便打开一篇文章，从地址栏复制带 uuid= 的完整 URL，")
        print(f"          然后跑：python -m src.local --set-uuid {platform}")
    return 0


def set_uuid(platform: str) -> int:
    """从剪贴板读 URL，抠出 uuid 参数写进本机凭据文件。"""
    from .clipboard import clear_clipboard, read_clipboard
    from .local_secrets import SECRETS_FILE
    from .publish import clean_param

    raw = read_clipboard()
    if not raw.strip():
        print("[错误] 剪贴板是空的。")
        return 1
    if "uuid=" not in raw:
        print("[错误] 剪贴板里没有 uuid=。要复制的是带 uuid 参数的完整 URL。")
        return 1
    # 从 URL 里抠 uuid= 后面的值
    m = re.search(r"uuid=([0-9A-Za-z_-]{6,})", raw)
    if not m:
        print("[错误] 没能从剪贴板内容里解析出 uuid。")
        return 1
    value = clean_param(m.group(1))
    if not value:
        print("[错误] uuid 解析为空。")
        return 1

    data = {}
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    data["JUEJIN_UUID"] = value
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    cleared = clear_clipboard()
    print(f"[ok] JUEJIN_UUID 已写入（{len(value)} 位，值不回显）")
    print(f"[ok] 剪贴板已{'清空' if cleared else '未清空（请手动清）'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="github-daily 本机运行入口")
    ap.add_argument("--status", action="store_true", help="体检：开关 / 凭据 / 平台 / 时间表")
    ap.add_argument("--dry-run", action="store_true", help="只出稿，不推送（覆盖配置）")
    ap.add_argument("--run", action="store_true", help="跑一次流水线")
    ap.add_argument("--daemon", action="store_true", help="常驻：每天到点自动跑")
    ap.add_argument("--once", action="store_true", help="常驻模式下只跑一次就退出")
    ap.add_argument("--login", metavar="PLATFORM",
                    help="扫码登录一次，自动导出登录态（cookie+uuid）：juejin/csdn/zhihu/toutiao")
    ap.add_argument("--set-cookie", metavar="PLATFORM",
                    help="从剪贴板读 Cookie 写进本机凭据文件：juejin / csdn / zhihu")
    ap.add_argument("--set-uuid", metavar="PLATFORM",
                    help="从剪贴板读 URL 并抠出 uuid（掘金）")
    ap.add_argument("--probe", action="store_true", help="只读探测凭据是否有效，不发文章")
    ap.add_argument("--track", metavar="TRACK", default=None,
                    help="只跑指定赛道：tech（技术/AI）或 restaurant（餐饮）")
    ap.add_argument("--list-tracks", action="store_true", help="列出赛道与平台归属")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--preview-days", type=int, default=0)
    args = ap.parse_args()

    if args.status:
        return status()
    if args.probe:
        return probe_credentials()
    if args.list_tracks:
        return list_tracks()
    if args.login:
        return login(args.login)
    if args.set_cookie:
        return set_credential(args.set_cookie)
    if args.set_uuid:
        return set_uuid(args.set_uuid)
    if args.daemon:
        return daemon(once=args.once)
    if args.run or args.dry_run:
        try:
            run_once(args.date, limit=args.limit,
                     dry_run_override=True if args.dry_run else None,
                     track=args.track)
        except Exception as e:
            print(f"FATAL: {redact(f'{type(e).__name__}: {e}')}", file=sys.stderr)
            return 1
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
