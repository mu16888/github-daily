"""CSDN 已发布内容的清点与恢复。

背景（2026-11-10 事故）：
CSDN 的删除是两级不可逆的 —— 先进回收站，**清空回收站就彻底没了**。
锋哥手动发的一篇 + 自动发的一篇因此被永久删除（内容在本地 drafts/ 有备份）。

这个模块提供两件事：
1. `audit()`    —— 清点线上现状：已发布 / 草稿 / 回收站各有多少，与本地台账对账
2. `republish()` —— 把本地指定日期的稿子重新发一遍（CSDN 免费号每天 1 篇，额度重置后用）

安全约束：
- `audit` 是只读的，随时可跑。
- `republish` 只读本地 drafts/，不改线上任何东西（只是新建文章）。
- 任何**删除**操作都不在这个模块里 —— 那是不可逆的，必须人工在 CSDN 后台做。
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
import hmac
import hashlib
import base64
from pathlib import Path
from typing import Any

import requests

from .publish import csdn_sign_string, redact

ROOT = Path(__file__).resolve().parent.parent
CSDN_BASE = "https://bizapi.csdn.net"
CA_KEY = "203803574"
CA_SECRET = "9znpamsyl2c7cdrr9sas0le9vbc3r6ba"
CONTENT_TYPE = "application/json"          # 不能带 charset，否则签名不一致 → 400
ACCEPT = "*/*"


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def _cookie() -> str:
    from .local_secrets import load_local_secrets
    from .publish import clean_cookie
    return clean_cookie(load_local_secrets().get("CSDN_COOKIE", ""))


def _call(path: str, method: str = "GET", body: dict | None = None) -> dict:
    """调 CSDN 网关接口（自动带 x-ca 签名）。"""
    cookie = _cookie()
    if not cookie:
        return {"code": -1, "msg": "缺少 CSDN_COOKIE"}
    nonce = str(uuid.uuid4())
    to_sign = csdn_sign_string("POST" if method == "POST" else "GET",
                               ACCEPT, CONTENT_TYPE, CA_KEY, nonce, path).encode()
    sign = base64.b64encode(
        hmac.new(CA_SECRET.encode(), to_sign, hashlib.sha256).digest()).decode()
    headers = {
        "content-type": CONTENT_TYPE,
        "accept": ACCEPT,
        "origin": "https://editor.csdn.net",
        "referer": "https://editor.csdn.net/",
        "cookie": cookie,
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "Chrome/131.0 Safari/537.36"),
        "accept-language": "zh-CN",
        "x-ca-key": CA_KEY,
        "x-ca-nonce": nonce,
        "x-ca-signature": sign,
        "x-ca-signature-headers": "x-ca-key,x-ca-nonce",
    }
    s = _session()
    url = CSDN_BASE + path
    try:
        if method == "POST":
            r = s.post(url, headers=headers, json=body or {}, timeout=30)
        else:
            r = s.get(url, headers=headers, timeout=30)
        try:
            d = r.json()
            return d if isinstance(d, dict) else {"code": -1, "msg": "响应不是 JSON"}
        except Exception:
            return {"code": -1, "msg": f"响应解析失败 http={r.status_code}"}
    except Exception as e:
        return {"code": -1, "msg": f"{type(e).__name__}: {str(e)[:80]}"}


def list_articles(status: str = "all", page_size: int = 50) -> list[dict]:
    """按状态取文章列表。status: all / draft / deleted / publish / request_new_publish"""
    d = _call(f"/blog/phoenix/console/v1/article/list?status={status}"
              f"&page=1&pageSize={page_size}")
    data = d.get("data") or {}
    return list(data.get("list") or [])


def audit(date: str | None = None) -> dict[str, Any]:
    """清点线上现状并与本地对账。只读。"""
    out: dict[str, Any] = {"date": date or dt.date.today().isoformat(), "checked_at":
                           dt.datetime.now().isoformat(timespec="seconds")}
    counts = {}
    items: dict[str, list[dict]] = {}
    for st in ("all", "draft", "deleted", "request_new_publish"):
        lst = list_articles(st)
        items[st] = [{"id": it.get("articleId"), "status": it.get("status"),
                      "title": str(it.get("title") or "")[:70],
                      "postTime": it.get("postTime")} for it in lst]
        counts[st] = len(lst)
    out["counts"] = counts
    out["items"] = items

    # 本地已归档的稿子
    local_dir = ROOT / "drafts" / out["date"]
    local = []
    if local_dir.exists():
        for p in sorted(local_dir.glob("*.md")):
            if p.name.endswith("-粘贴用正文.md"):
                continue
            local.append({"file": p.name, "chars": len(p.read_text(encoding="utf-8"))})
    out["local_drafts"] = local
    return out


def republish(date: str, platform_title: str | None = None,
              tags: str = "开源,开发工具,Git",
              brief: str = "") -> dict[str, Any]:
    """把本地某天的稿子重新发到 CSDN。

    走浏览器通道（src/csdn_browser.py）—— 实测接口只能建草稿，
    公开发布必须走编辑器「发布文章」面板。

    注意：CSDN 免费号每天 1 篇，额度用完会提示「今日发文额度已用完」。
    """
    from .csdn_browser import CsdnBrowserPublisher
    from .main import load_yaml

    folder = ROOT / "drafts" / date
    cands = [p for p in sorted(folder.glob("*.md"))
             if not p.name.endswith("-粘贴用正文.md")] if folder.exists() else []
    if not cands:
        return {"status": "failed", "detail": f"{date} 没有可发的本地稿子"}

    md = cands[0].read_text(encoding="utf-8")
    title = platform_title or (md.splitlines()[0].lstrip("# ").strip()
                               if md.startswith("#") else cands[0].stem)
    if not brief:
        first = md.splitlines()[0].lstrip("# ").strip()
        brief = first[:120]

    lcfg = load_yaml(ROOT / "config" / "local.yaml")
    pub = CsdnBrowserPublisher(browser_cfg=lcfg.get("browser") or {}, root=ROOT)
    r = pub.publish({"markdown": md, "titles": {"csdn": title}},
                    headless=False, title=title, body=md, brief=brief, tags=tags)
    return {"status": r.status, "url": r.url, "detail": r.detail,
            "title": title, "file": cands[0].name}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="CSDN 线上清点与重发")
    ap.add_argument("action", choices=["audit", "republish"])
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--title", default=None)
    ap.add_argument("--tags", default="开源,开发工具,Git")
    ap.add_argument("--brief", default="")
    a = ap.parse_args()
    if a.action == "audit":
        info = audit(a.date)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    res = republish(a.date, a.title, a.tags, a.brief)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("status") == "published" else 1


if __name__ == "__main__":
    raise SystemExit(main())
