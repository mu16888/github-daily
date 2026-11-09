"""三平台发布适配器。

设计要点：
1. 凭据缺失 -> status=skipped（不是 failed，也不是 published），绝不误报成功。
2. HTTP 200 不等于发布成功：知乎看 JSON status==0，CSDN 看 code==200，掘金看两层响应。
3. dry_run 只组装请求体与检查凭据是否齐备，不向任何发布端点发请求。
4. Secret 与签名值不写日志、不写文件。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

import requests



@dataclass
class Result:
    platform: str
    status: str          # published | skipped | dry_run | failed
    url: str = ""
    detail: str = ""
    http_status: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def _json(resp: requests.Response) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class BasePublisher:
    name = "base"

    def __init__(self, pcfg: dict, settings: dict, secrets: dict[str, str], dry_run: bool):
        self.cfg = pcfg
        self.settings = settings
        self.secrets = secrets
        self.dry_run = dry_run
        self.session = _session()

    def required(self) -> list[str]:
        return list(self.cfg.get("secrets", []))

    def missing(self) -> list[str]:
        return [k for k in self.required() if not (self.secrets.get(k) or "").strip()]

    # 每个平台用各自的 SEO 标题 / 摘要 / 标签；旧字段作为兼容回退
    def title(self, article: dict) -> str:
        return (article.get("titles") or {}).get(self.name) or article.get("title", "")

    def brief(self, article: dict) -> str:
        return (article.get("briefs") or {}).get(self.name) or article.get("brief", "")

    def tags(self, article: dict) -> str:
        return (article.get("platform_tags") or {}).get(self.name) or article.get("tags", "")

    def build(self, article: dict) -> tuple[str, dict, dict]:
        """返回 (url, headers, body)。子类实现。"""
        raise NotImplementedError

    def judge(self, resp: requests.Response) -> tuple[bool, str, str]:
        raise NotImplementedError

    def publish(self, article: dict) -> Result:
        miss = self.missing()
        if miss:
            return Result(self.name, "skipped", detail=f"缺少 Secrets: {', '.join(miss)}")
        if self.dry_run:
            url, _headers, body = self.build(article)
            size = len(json.dumps(body, ensure_ascii=False))
            return Result(self.name, "dry_run", detail=f"已组装请求（{url}，正文 {size} 字符），未实际发送")
        try:
            url, headers, body = self.build(article)
            resp = self.session.post(url, headers=headers, json=body, timeout=30)
            ok, link, detail = self.judge(resp)
            return Result(self.name, "published" if ok else "failed", url=link,
                          detail=detail, http_status=resp.status_code)
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")


class ZhihuPublisher(BasePublisher):
    name = "zhihu"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.ts = ""
        self.logid = ""

    def publish(self, article: dict) -> Result:
        z = self.settings.get("zhihu", {})
        if not z.get("standing_consent", False):
            return Result(self.name, "skipped",
                          detail="官方规范要求用户确认后才可 confirmed:true；settings.zhihu.standing_consent=false")
        return super().publish(article)

    def build(self, article: dict) -> tuple[str, dict, dict]:
        c = self.cfg
        key = self.secrets["ZHIHU_APP_KEY"].strip()
        secret = self.secrets["ZHIHU_APP_SECRET"].strip()
        self.ts = str(int(time.time()))
        self.logid = f"github-daily-{uuid.uuid4().hex[:12]}"
        extra = ""
        sign_string = f"app_key:{key}|ts:{self.ts}|logid:{self.logid}|extra_info:{extra}"
        sign = base64.b64encode(hmac.new(secret.encode(), sign_string.encode(), hashlib.sha256).digest()).decode()
        headers = {
            "Content-Type": "application/json",
            "X-App-Key": key,
            "X-Timestamp": self.ts,
            "X-Log-Id": self.logid,
            "X-Extra-Info": extra,
            "X-Sign": sign,
        }
        z = self.settings["zhihu"]
        content: dict[str, Any] = {
            "title": self.title(article),
            "html": article["html"],
            "comment_permission": z.get("comment_permission", "all"),
            "table_of_contents_enabled": bool(z.get("table_of_contents_enabled", False)),
        }
        statement = (z.get("creation_statement") or "").strip()
        if statement:
            content["creation_statement"] = statement
        body = {
            "type": "article",
            "confirmed": True,
            # 如实描述授权方式，不冒充官方示例里的「逐篇本地预览」
            "confirm_note": "confirmed by repository owner via standing consent in config/settings.yaml",
            "content": content,
        }
        return f"{c['base_url']}{c['path']}", headers, body

    def judge(self, resp: requests.Response) -> tuple[bool, str, str]:
        data = _json(resp)
        status = data.get("status")
        msg = str(data.get("msg") or "")
        if isinstance(status, (int, float)) and status == 0:
            d = data.get("data") or {}
            return True, str(d.get("url") or ""), msg or "status=0"
        return False, "", f"status={status!r} msg={msg or '(empty)'}"


class JuejinPublisher(BasePublisher):
    name = "juejin"

    def build(self, article: dict) -> tuple[str, dict, dict]:
        c = self.cfg
        q = c["query"]
        cookie = self.secrets["JUEJIN_COOKIE"].strip()
        uid = self.secrets["JUEJIN_UUID"].strip()
        base = c["api_base"]
        url = f"{base}{c['endpoints']['draft_create']}?aid={q['aid']}&uuid={uid}&spider={q['spider']}"
        j = self.settings["juejin"]
        headers = {"Content-Type": "application/json", "Cookie": cookie,
                   "User-Agent": "Mozilla/5.0", "Referer": "https://juejin.cn/editor/drafts/new"}
        body = {
            "title": self.title(article)[: int(c.get("title_max", 80))],
            "mark_content": article["markdown"],
            "brief_content": self.brief(article)[: int(c.get("brief_max", 100))],
            "category_id": str(j["category_id"]),
            "tag_ids": [str(x) for x in j.get("tag_ids", [])],
            "cover_image": "",
            "edit_type": int(c.get("edit_type", 10)),
        }
        return url, headers, body

    def _draft_id(self, data: dict) -> str:
        d = data.get("data")
        if isinstance(d, dict):
            for k in ("draft_id", "id", "article_id"):
                if d.get(k):
                    return str(d[k])
        if isinstance(d, str) and d:
            return d
        return ""

    def publish(self, article: dict) -> Result:
        miss = self.missing()
        if miss:
            return Result(self.name, "skipped", detail=f"缺少 Secrets: {', '.join(miss)}")
        if self.dry_run:
            url, _h, body = self.build(article)
            return Result(self.name, "dry_run", detail=f"已组装掘金草稿请求（{url}，{len(body['mark_content'])} 字符），未发送")
        try:
            url, headers, body = self.build(article)
            r1 = self.session.post(url, headers=headers, json=body, timeout=30)
            d1 = _json(r1)
            draft_id = self._draft_id(d1)
            if not draft_id:
                return Result(self.name, "failed", http_status=r1.status_code,
                              detail=f"建草稿未返回 draft_id，code={d1.get('err_no') or d1.get('code')} msg={d1.get('err_msg') or d1.get('msg')}")
            c = self.cfg
            q = c["query"]
            uid = self.secrets["JUEJIN_UUID"].strip()
            pub_url = f"{c['api_base']}{c['endpoints']['publish']}?aid={q['aid']}&uuid={uid}&spider={q['spider']}"
            pub_body = {"draft_id": draft_id, "sync_to_org": False, "column_ids": [], "theme_ids": []}
            r2 = self.session.post(pub_url, headers=headers, json=pub_body, timeout=30)
            d2 = _json(r2)
            ok = (d2.get("err_no") in (0, None) and d2.get("code") in (0, 200, None)) or bool(d2.get("data"))
            link = ""
            if isinstance(d2.get("data"), dict):
                link = str(d2["data"].get("article_url") or d2["data"].get("url") or "")
            return Result(self.name, "published" if ok else "failed", url=link,
                          http_status=r2.status_code,
                          detail=f"draft_id={draft_id} | publish code={d2.get('code') or d2.get('err_no')} msg={d2.get('msg') or d2.get('err_msg') or ''}")
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")


class CsdnPublisher(BasePublisher):
    name = "csdn"

    def build(self, article: dict) -> tuple[str, dict, dict]:
        c = self.cfg
        path = c["path"]
        ct = c["content_type"]
        key = str(c["ca_key"])
        nonce = str(uuid.uuid4())
        # 阿里云 API 网关签名串：空行与换行必须逐字一致
        to_sign = (
            f"POST\n/\n\n{ct}\n\n"
            f"x-ca-key:{key}\n"
            f"x-ca-nonce:{nonce}\n"
            f"{path}"
        ).encode()
        sign = base64.b64encode(
            hmac.new(str(c["ca_sign_secret"]).encode(), to_sign, hashlib.sha256).digest()
        ).decode()
        headers = {
            "content-type": ct,
            "accept": "*/*",
            "origin": c["origin"],
            "referer": c["referer"],
            "cookie": self.secrets["CSDN_COOKIE"].strip(),
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "x-ca-key": key,
            "x-ca-nonce": nonce,
            "x-ca-signature": sign,
            "x-ca-signature-headers": c["ca_signature_headers"],
        }
        body = {
            **c["payload_static"],
            "title": self.title(article),
            "content": article["html"],          # 必须是渲染后的 HTML
            "markdowncontent": article["markdown"],
            "tags": self.tags(article),
            "readType": self.settings["csdn"]["read_type"],
            "type": self.settings["csdn"]["article_type"],
            "status": int(c["payload_static"]["status"]),
        }
        return f"{c['api_base']}{path}", headers, body

    def judge(self, resp: requests.Response) -> tuple[bool, str, str]:
        data = _json(resp)
        code = data.get("code")
        ok = code in (200, "200")
        d = data.get("data") or {}
        link = str(d.get("url") or "") if isinstance(d, dict) else ""
        return ok, link, f"code={code!r} msg={str(data.get('msg') or data.get('message') or '')[:120]}"


def all_publishers(platforms_cfg: dict, settings: dict) -> list[BasePublisher]:
    secrets = {k: os.environ.get(k, "") for k in (
        "ZHIHU_APP_KEY", "ZHIHU_APP_SECRET", "JUEJIN_COOKIE", "JUEJIN_UUID", "CSDN_COOKIE"
    )}
    dry = bool(settings["publish"].get("dry_run", True))
    mapping = {"zhihu": ZhihuPublisher, "juejin": JuejinPublisher, "csdn": CsdnPublisher}
    out = []
    for name, cls in mapping.items():
        cfg = platforms_cfg["platforms"].get(name, {})
        if cfg.get("enabled", False):
            out.append(cls(cfg, settings, secrets, dry))
    return out
