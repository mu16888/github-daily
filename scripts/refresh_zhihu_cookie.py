#!/usr/bin/env python3
"""一键刷新云端 ZHIHU_COOKIE。

流程（锋哥只做一步：在弹出的 Edge 窗口里登录知乎）：
  1. 用本机 Edge（独立 profile）打开知乎登录页
  2. 锋哥扫码/登录，程序检测到登录态 cookie 出现
  3. 程序把 Cookie 导出，通过 `gh secret set` 写进 GitHub 仓库 secret
  4. 同步写一份到本机 config/local_secrets.json 便于本地调试

用法：
  python scripts/refresh_zhihu_cookie.py
  python scripts/refresh_zhihu_cookie.py --timeout 300

为什么需要它：
  云端 Linux runner 没有浏览器，知乎 Cookie 只能从本机导出后存进 GitHub Secret。
  知乎 Cookie 有效期有限（数小时到数天不等）。云端自动化若某天报知乎失败，
  重跑本脚本即可。本脚本必须在本地（有浏览器、有 gh 登录态）运行，不在云端跑。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _main() -> int:
    ap = argparse.ArgumentParser(description="刷新云端平台 Cookie Secret")
    ap.add_argument("--platform", default="zhihu", choices=["zhihu"])
    ap.add_argument("--timeout", type=int, default=240,
                    help="等待登录的最长秒数")
    args = ap.parse_args()

    platform = args.platform
    # 知乎走本机 Edge 浏览器（与云端 Linux runner 的 Playwright chromium 不同）
    browser_cfg = {"profile_dir": "state/browser-profile", "channel": "msedge"}

    from src.browser_creds import capture, save_to_secrets

    print(f"[refresh] 打开本机 Edge，请在弹出的窗口内登录 {platform}（最多等 {args.timeout} 秒）...")
    res = capture(platform, browser_cfg, headless=False, timeout=args.timeout)
    cookie = (res or {}).get("cookie", "")
    if not cookie:
        print("[refresh] 未拿到 cookie，登录可能未完成。请重试。")
        return 1

    # 写云端 secret：从 stdin 读取，避免命令行超长 / 特殊字符转义问题。
    secret_name = f"{platform.upper()}_COOKIE"
    print(f"[refresh] 已拿到 cookie，写入云端 secret {secret_name} ...")
    try:
        subprocess.run(
            ["gh", "secret", "set", secret_name],
            input=cookie, text=True, capture_output=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or e.stdout or "").strip()
        print(f"[refresh] gh secret set 失败：{stderr}")
        return 1

    # 同步写本机缓存，便于本地调试（不进 git，已被 .gitignore 挡住）
    try:
        save_to_secrets({secret_name: cookie})
    except Exception as e:  # noqa: BLE001 - 本机缓存失败不影响云端 secret
        print(f"[refresh] 本机缓存写入跳过（{type(e).__name__}），不影响云端 secret")

    print("[refresh] 完成。云端 ZHIHU_COOKIE 已更新。")
    print("[refresh] 知乎 Cookie 有效期有限，若日后自动化报知乎失败，重跑本脚本即可。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
