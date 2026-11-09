"""仿人工发布时间调度：每天一个「确定性但不同」的发布时刻。

GitHub Actions 的 cron 只能写固定时刻，写不出「每天随机」。做法是：

    cron 每 15 分钟唤醒一次
      -> 本模块用 HMAC-SHA256(日期 + 盐) 确定性地算出当天唯一目标时刻
      -> 没到点：立即空跑退出（不抓 GitHub、不发文章）
      -> 到点：放行，并可选 sleep 到精确的分钟/秒再发
      -> 发完在台账里记 last_dispatched，当天后续唤醒全部跳过

确定性是关键：某次唤醒被取消、排队延迟或失败时，下一次唤醒算出的仍是
同一个目标时刻，会立即补发，不会漏发，也不会因为「重新随机」而重复发。

用法：
    python -m src.schedule --check --align     # CI 闸门，写 GITHUB_OUTPUT
    python -m src.schedule --preview 14        # 预览未来 14 天的发布时刻
    python -m src.schedule --check --force     # 忽略闸门，立即放行（手动触发）
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "published.json"
UTC = dt.timezone.utc

# action 取值：
#   run    立即放行（到点了 / 补发 / 强制）
#   sleep  sleep 到目标时刻再放行
#   wait   今天还没轮到这一棒，空跑退出
#   done   今天已经派发过，空跑退出
#   off    调度功能整体关闭，空跑退出


def load_config() -> dict:
    data = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}
    return data.get("schedule") or {}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "seen": {}}


def local_tz(cfg: dict) -> dt.timezone:
    return dt.timezone(dt.timedelta(hours=float(cfg.get("utc_offset_hours", 8))))


def _hhmm(value: object) -> int:
    h, m = str(value).split(":")
    return int(h) * 60 + int(m)


def _digest(date: dt.date, salt: str, tag: str) -> int:
    msg = f"{date.isoformat()}|{tag}".encode("utf-8")
    return int.from_bytes(hmac.new(salt.encode("utf-8"), msg, hashlib.sha256).digest()[:8], "big")


def target_for(date: dt.date, cfg: dict) -> dt.datetime:
    """当天唯一的目标发布时刻，返回 aware UTC datetime。

    同一天、同一份配置永远得到同一个结果；不同日期几乎必然不同，且：
    - 落在配置窗口内，周末整体顺延（更像真人作息）
    - 分钟避开 5 的倍数（真人很少正好 09:00 / 09:05 / 09:30 发）
    - 秒避开 0（不卡整秒）
    """
    salt = str(cfg.get("salt", ""))
    offset = dt.timedelta(hours=float(cfg.get("utc_offset_hours", 8)))
    start = _hhmm(cfg.get("window_start", "08:30"))
    end = _hhmm(cfg.get("window_end", "10:45"))
    if date.weekday() >= 5:
        shift = int(cfg.get("weekend_delay_minutes", 45))
        start += shift
        end += shift

    span = max(1, end - start)
    minute = start + _digest(date, salt, "target") % span
    if cfg.get("avoid_round_minutes", True) and minute % 5 == 0:
        minute += 1 + _digest(date, salt, "round") % 3
        if minute > end:
            minute -= 5      # 回退后仍在窗口内，且不再是 5 的倍数
    second = 1 + _digest(date, salt, "second") % 59

    local = dt.datetime(date.year, date.month, date.day) + dt.timedelta(minutes=minute, seconds=second)
    return (local - offset).replace(tzinfo=UTC)


def decide(now: dt.datetime, cfg: dict, state: dict, force: bool = False) -> tuple[str, int, dt.datetime | None]:
    """判断这一棒该做什么，返回 (action, wait_seconds, target_utc)。"""
    if not cfg.get("enabled", True):
        return "off", 0, None
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    date = now.astimezone(local_tz(cfg)).date()
    target = target_for(date, cfg)

    if force:
        return "run", 0, target
    if (state.get("schedule") or {}).get("last_dispatched") == date.isoformat():
        return "done", 0, target
    if now < target:
        poll = max(5, int(cfg.get("poll_minutes", 15)))
        # 只有目标落在「本次唤醒 ~ 下一次唤醒」之间，才由这一棒 sleep 到点；
        # 否则把机会留给后面的唤醒，本次立即退出，别白占 runner。
        if target <= now + dt.timedelta(minutes=poll):
            return "sleep", max(0, int((target - now).total_seconds()) + 1), target
        return "wait", 0, target
    return "run", 0, target


def stagger_plan(date: dt.date, cfg: dict, platform_names: list[str]) -> dict[str, int]:
    """三平台错峰秒数（按发布顺序累加），避免同一秒三连发。"""
    lo = int(cfg.get("stagger_min_seconds", 90))
    hi = int(cfg.get("stagger_max_seconds", 420))
    salt = str(cfg.get("salt", ""))
    span = max(1, hi - lo + 1)
    out: dict[str, int] = {}
    acc = 0
    for i, name in enumerate(platform_names):
        if i > 0:
            acc += lo + _digest(date, salt, f"stagger:{i}") % span
        out[name] = acc
    return out


def mark_dispatched(state: dict, date: str, mode: str = "live") -> None:
    """记「今天已派发」，只保留最近 14 天历史，不碰去重台账 seen。

    这是调度层的幂等标记，与 published.json 里的「已推荐项目 / 已发布记录」是两回事：
    演练也写它（否则当天每次唤醒都会重复跑一遍流水线），但不写 seen，
    所以候选和发布记录依然不会被演练消耗。想一天内反复演练，本地直接跑
    `python -m src.main --dry-run` 即可（本地不经过闸门）。
    """
    prev = (state.get("schedule") or {}).get("history") or []
    state["schedule"] = {
        "last_dispatched": date,
        "last_mode": mode,
        "history": (list(prev) + [date])[-14:],
    }


def _preview(days: int) -> None:
    cfg = load_config()
    tz = local_tz(cfg)
    print(f"窗口 {cfg.get('window_start')}–{cfg.get('window_end')} UTC+{cfg.get('utc_offset_hours')}"
          f"，周末顺延 {cfg.get('weekend_delay_minutes')} 分钟，盐 {cfg.get('salt')}")
    print(f"{'日期':<12} {'星期':<5} {'目标时刻':<12} {'知乎 / 掘金 / CSDN 实际发出时刻'}")
    for i in range(days):
        d = dt.date.today() + dt.timedelta(days=i)
        t = target_for(d, cfg).astimezone(tz)
        plan = stagger_plan(d, cfg, ["zhihu", "juejin", "csdn"])
        seq = " / ".join((t + dt.timedelta(seconds=v)).strftime("%H:%M:%S") for v in plan.values())
        wd = "一二三四五六日"[d.weekday()]
        print(f"{d.isoformat():<12} 周{wd:<4} {t.strftime('%H:%M:%S'):<12} {seq}")


def ci_check(force: bool, align: bool) -> int:
    cfg = load_config()
    state = load_state()
    now = dt.datetime.now(UTC)
    action, wait, target = decide(now, cfg, state, force)
    tz = local_tz(cfg)
    info = {
        "now_utc": now.isoformat(timespec="seconds"),
        "target_local": target.astimezone(tz).isoformat(timespec="seconds") if target else None,
        "action": action,
    }
    should = action == "run"

    if action == "sleep" and align and wait > 0:
        info["wait_seconds"] = wait
        print(f"[gate] 今天目标 {info['target_local']}，等待 {wait}s 到点再发", flush=True)
        time.sleep(wait)
        # sleep 期间可能有并发的补发已经完成，重新读台账再确认一次
        action2, _, _ = decide(dt.datetime.now(UTC), cfg, load_state(), False)
        if action2 == "done":
            should = False
            action = "done"
        else:
            should = True
            action = "run"
    elif action == "sleep" and not align:
        action = "wait"      # 本地不带 --align 时，绝不误放行

    info["action"] = action
    info["should_run"] = should
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"run={'true' if should else 'false'}\n")
            f.write(f"target={target.isoformat() if target else ''}\n")
            f.write(f"action={action}\n")
    print("[gate] " + json.dumps(info, ensure_ascii=False), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="仿人工发布时间闸门")
    ap.add_argument("--check", action="store_true", help="CI 闸门模式，写 GITHUB_OUTPUT")
    ap.add_argument("--align", action="store_true", help="放行前 sleep 到当天目标时刻")
    ap.add_argument("--force", action="store_true", help="忽略时间闸门，立即放行")
    ap.add_argument("--preview", type=int, metavar="N", help="预览未来 N 天的发布时刻")
    a = ap.parse_args()
    if a.preview:
        _preview(max(1, a.preview))
        return 0
    if a.check:
        return ci_check(a.force, a.align)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
