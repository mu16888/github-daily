"""本机凭据读取。

为什么不直接用环境变量：
GitHub Secrets 只写不可读，云端那份掘金 / CSDN Cookie 拉不回本机；
本机运行必须有一份自己的凭据文件。放在 `config/local_secrets.json`，
已被 .gitignore 挡住，绝不进仓库。

优先级：环境变量 > 本地文件。同名环境变量用于临时覆盖（例如临时换一个
CSDN Cookie 试一次），不写盘、不进日志。

公众号凭据不复制到这里：复用 `E:\\workbuddy工作台\\沐风博客\\config\\wechat_config.json`
（同一个 AppID / AppSecret，避免两份凭据各发一遍把配额打乱）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# 本机凭据文件：必须在 .gitignore 里
SECRETS_FILE = ROOT / "config" / "local_secrets.json"

# 允许从环境变量注入的键（与 GitHub Secrets 同名，便于对照排查）
ENV_KEYS = (
    "ZHIHU_APP_KEY",
    "ZHIHU_APP_SECRET",
    "ZHIHU_COOKIE",
    "JUEJIN_COOKIE",
    "JUEJIN_UUID",
    "CSDN_COOKIE",
)

# 公众号凭据来源（复用沐风博客，避免重复存一份 AppSecret）
WECHAT_CONFIG_CANDIDATES = (
    Path(r"E:\workbuddy工作台\沐风博客\config\wechat_config.json"),
    ROOT.parent.parent / "沐风博客" / "config" / "wechat_config.json",
)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def wechat_config() -> dict:
    """返回公众号的 appid / secret / author / site_base；找不到返回空 dict。"""
    for p in WECHAT_CONFIG_CANDIDATES:
        if p.exists():
            data = _read_json(p)
            if data.get("appid") and data.get("secret"):
                return {
                    "appid": str(data["appid"]),
                    "secret": str(data["secret"]),
                    "author": str(data.get("author") or ""),
                    "site_base": str(data.get("site_base") or ""),
                    "_source": str(p),
                }
    return {}


def load_local_secrets(path: Path | None = None) -> dict[str, str]:
    """读本机凭据：环境变量覆盖本地文件。返回 {KEY: value}。"""
    out: dict[str, str] = {}
    f = path or SECRETS_FILE
    if f.exists():
        data = _read_json(f)
        for k in ENV_KEYS:
            v = data.get(k)
            if v is not None and str(v).strip():
                out[k] = str(v)
    for k in ENV_KEYS:
        v = os.environ.get(k, "")
        if v.strip():
            out[k] = v
    return out


def secrets_status(path: Path | None = None) -> dict[str, Any]:
    """只报告「有没有」，绝不回显值。给体检脚本和日志用。"""
    s = load_local_secrets(path)
    f = path or SECRETS_FILE
    status: dict[str, Any] = {
        "file": str(f),
        "file_exists": f.exists(),
        "keys": {k: bool(s.get(k, "").strip()) for k in ENV_KEYS},
        "wechat": bool(wechat_config()),
    }
    return status
