"""三平台发布适配器。

设计要点：
1. 凭据缺失 -> status=skipped（不是 failed，也不是 published），绝不误报成功。
2. HTTP 200 不等于发布成功：知乎看 JSON status/code，CSDN 看 code==200，掘金看两层响应。
3. dry_run 只组装请求体与检查凭据是否齐备，不向任何发布端点发请求。
4. Secret 与签名值不写日志、不写文件。所有 Result.detail 在构造时统一脱敏，
   因为 requests 的 InvalidHeader 会把整个 Cookie 请求头原样塞进异常消息。
5. Cookie 从 DevTools 复制时经常带 `cookie:` 标签、换行、多余空格；
   统一经 clean_cookie() 规范化，避免把标签名当请求头值发出去。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests


# 仓库根目录（云端运行时用它定位浏览器 profile 等本机路径）
ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# 凭据清洗与脱敏
# --------------------------------------------------------------------------- #

# 只匹配「标签名」：cookie: / cookie：/ cookie\n / cookie（单独一个词）。
# 不能误伤以 cookie_ 开头的真实字段名（如 cookie_consent）。
_COOKIE_LABEL_RE = re.compile(r"^\s*cookie(?:\s*[:：]\s*|\s+|\s*$)", re.IGNORECASE)

_SENSITIVE_FIELDS = (
    "sessionid", "sessionid_ss", "sid_guard", "sid_tt", "sid_ucp_v1", "ssid_ucp_v1",
    "passport_csrf_token", "passport_csrf_token_default", "passport_auth_status",
    "z_c0", "_xsrf", "x-xsrftoken", "userinfo", "usertoken", "username",
    "dc_session_id", "csrftoken", "__ac_signature", "s_v_web_id",
    "authorization", "x-ca-signature", "app_secret", "set-cookie", "cookie",
)
_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])(" + "|".join(re.escape(f) for f in _SENSITIVE_FIELDS) +
    r")\s*=\s*([^;\s,'\"\\)]{1,4000})"
)
_PARAM_LABEL_RE = re.compile(r"(?i)^(?:uuid|aid)\s*=\s*")
_UUID_QUERY_RE = re.compile(r"(?i)\buuid=[0-9A-Za-z_-]{6,}")


def clean_cookie(raw: str) -> str:
    """把从 DevTools 复制的 Cookie 规范化成纯 `name=value; name=value` 请求头值。

    处理三类常见脏数据：`cookie: ` 前缀、`cookie\\n` 前缀（标签+换行）、
    记事本自动换行 / 制表符 / 多余空格。不校验字段内容，避免因测试用的
    短占位值被判为「缺失」；标签名单独一个词会被清成空串，由 missing() 判缺失。
    """
    s = _COOKIE_LABEL_RE.sub("", raw or "", count=1)
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s*;\s*", "; ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s.strip("; ").strip()


def clean_param(raw: str) -> str:
    """清洗从 URL 里复制的 uuid / aid：去掉 `uuid=` 前缀、`&spider=0` 尾巴与引号。"""
    s = str(raw or "").strip().strip("'\"")
    s = _PARAM_LABEL_RE.sub("", s)
    return re.split(r"[&\s?#]", s, maxsplit=1)[0].strip()


def cookie_value(cookie: str, name: str) -> str:
    for part in (cookie or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == name:
            return v.strip()
    return ""


def redact(text: str, limit: int = 300) -> str:
    """脱敏任何可能进日志 / 公开仓库文件的文本。

    三段：整串 Cookie（很多分号或等号）直接整体丢弃，不做字段级替换，
    避免漏掉没列进名单的新字段；短消息按敏感字段名逐个打码；
    最后把 URL 里的用户级 uuid（Secret 派生值）也打码，不写进公开文件。
    """
    s = str(text or "").replace("\r", " ").replace("\n", " ")
    if s.count(";") >= 3 or s.count("=") >= 8:
        return "[redacted] 原始消息疑似含完整请求头或 Cookie，已整体脱敏（不写入公开文件）"
    s = _SENSITIVE_FIELD_RE.sub(lambda m: f"{m.group(1)}=***", s)
    s = _UUID_QUERY_RE.sub("uuid=***", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def safe_url(u: str) -> str:
    """只保留 scheme://host/path，丢掉可能带 token 的 query 与非 http(s) 值。"""
    raw = str(u or "").strip().splitlines()[0] if str(u or "").strip() else ""
    try:
        p = urlsplit(raw)
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}{p.path}"[:300]


def csdn_sign_string(method: str, accept: str, content_type: str,
                     key: str, nonce: str, path: str) -> str:
    """阿里云 API 网关 StringToSign。

    规范：Method + Accept + Content-MD5 + Content-Type + Date + Headers + Path。
    Headers 段每行以 \\n 结尾，所以 Path 直接接在 `x-ca-nonce:xxx\\n` 后面。
    第二行必须是 Accept 的值（旧代码误写成 `/`），第四行必须与实际请求头逐字一致。
    """
    return (f"{method}\n{accept}\n\n{content_type}\n\n"
            f"x-ca-key:{key}\n"
            f"x-ca-nonce:{nonce}\n"
            f"{path}")


@dataclass
class Result:
    platform: str
    status: str          # published | drafted | skipped | dry_run | failed
    url: str = ""
    detail: str = ""
    http_status: int | None = None

    def __post_init__(self):
        # 唯一出口：打印、写 state、写 run-summary 都拿到的是脱敏后的值。
        self.detail = redact(self.detail)
        self.url = safe_url(self.url)

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


# --------------------------------------------------------------------------- #
# 基类
# --------------------------------------------------------------------------- #

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

    def cookie(self, key: str) -> str:
        return clean_cookie(self.secrets.get(key, "") or "")

    def missing(self) -> list[str]:
        out = []
        for k in self.required():
            raw = self.secrets.get(k, "") or ""
            if k.endswith("_COOKIE"):
                v: Any = clean_cookie(str(raw))
            elif k.endswith("_UUID"):
                v = clean_param(str(raw))
            else:
                v = str(raw).strip()
            if not str(v).strip():
                out.append(k)
        return out

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


# --------------------------------------------------------------------------- #
# 知乎 C：官方 Publish OpenAPI（需「发布者」内测凭据）
# --------------------------------------------------------------------------- #

class _ZhihuOpenApi(BasePublisher):
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
        key = (self.secrets.get("ZHIHU_APP_KEY") or "").strip()
        secret = (self.secrets.get("ZHIHU_APP_SECRET") or "").strip()
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
        if resp.status_code == 200 and isinstance(status, (int, float)) and status == 0:
            d = data.get("data") or {}
            return True, str(d.get("url") or "") if isinstance(d, dict) else "", msg or "status=0"
        return False, "", f"http={resp.status_code} status={status!r} msg={msg or '(empty)'}"


# --------------------------------------------------------------------------- #
# 知乎 B：登录态网页会话（建草稿 -> 写正文 -> 尝试公开）
# 抓包契约：https://github.com/bifrost-proxy/bifrost/blob/main/.agents/skills/
#           zhihu-publish/references/traffic-contract.md
# 该通道不需要内测资格，但第三步可能需要前端动态签名 x-zse-96，
# 纯 Cookie 无法保证成功；失败时如实 failed，草稿仍在，可人工补发。
# --------------------------------------------------------------------------- #

class _ZhihuWeb(BasePublisher):
    name = "zhihu"

    def required(self) -> list[str]:
        return ["ZHIHU_COOKIE"]

    def _headers(self, cookie: str, publish: bool = False) -> dict:
        w = self.cfg["web"]
        h = {
            "Content-Type": "application/json",
            "Cookie": cookie,
            "User-Agent": w.get("user_agent", "Mozilla/5.0"),
            "Origin": w.get("publish_origin", w["origin"]) if publish else w["origin"],
            "Referer": w.get("publish_referer", w["referer"]) if publish else w["referer"],
            "x-requested-with": "fetch",
            "Accept": "application/json, text/plain, */*",
        }
        xsrf = cookie_value(cookie, "_xsrf")
        if xsrf:
            h["x-xsrftoken"] = xsrf
        return h

    def build(self, article: dict) -> tuple[str, dict, dict]:
        w = self.cfg["web"]
        url = f"{w['base_url']}{w['draft_create_path']}"
        body = {"title": self.title(article), "delta_time": 0, "can_reward": False}
        return url, self._headers(self.cookie("ZHIHU_COOKIE")), body

    def judge(self, resp: requests.Response) -> tuple[bool, str, str]:
        d = _json(resp)
        return (resp.status_code == 200 and d.get("code") in (0, "0"), "",
                f"http={resp.status_code} code={d.get('code')!r}")

    @staticmethod
    def _draft_id(d: dict) -> str:
        for k in ("id", "draft_id", "article_id"):
            v = d.get(k)
            if isinstance(v, (str, int)) and v:
                return str(v)
        for k in ("data", "draft", "article"):
            sub = d.get(k)
            if isinstance(sub, dict):
                got = _ZhihuWeb._draft_id(sub)
                if got:
                    return got
        return ""

    @staticmethod
    def _published_id(d: dict) -> str:
        data = d.get("data")
        obj: dict = {}
        if isinstance(data, dict):
            raw = data.get("result")
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                    obj = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    obj = {}
            elif isinstance(raw, dict):
                obj = raw
            elif isinstance(data.get("publish"), dict):
                obj = data
        pub = obj.get("publish") if isinstance(obj, dict) else None
        if isinstance(pub, dict) and pub.get("id"):
            return str(pub["id"])
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        return ""

    def publish(self, article: dict) -> Result:
        miss = self.missing()
        if miss:
            return Result(self.name, "skipped", detail=f"缺少 Secrets: {', '.join(miss)}")
        if self.dry_run:
            url, _h, _b = self.build(article)
            return Result(self.name, "dry_run",
                          detail=f"已组装知乎网页通道建草稿请求（{url}，正文 {len(article['html'])} 字符），未发送")

        w = self.cfg["web"]
        cookie = self.cookie("ZHIHU_COOKIE")
        headers = self._headers(cookie)
        title = self.title(article)
        html = article["html"]
        try:
            r1 = self.session.post(
                f"{w['base_url']}{w['draft_create_path']}", headers=headers,
                json={"title": title, "delta_time": 0, "can_reward": False}, timeout=30)
            d1 = _json(r1)
            did = self._draft_id(d1)
            if r1.status_code != 200 or not did:
                return Result(self.name, "failed", http_status=r1.status_code,
                              detail=f"建草稿失败 http={r1.status_code} code={d1.get('code')!r} "
                                     f"msg={str(d1.get('msg') or d1.get('message') or '')[:100]}")
            draft_url = str(d1.get("url") or w.get("drafts_url", ""))
            r2 = self.session.patch(
                f"{w['base_url']}{w['draft_update_path'].format(id=did)}", headers=headers,
                json={"title": title, "content": html, "table_of_contents": False,
                      "delta_time": 0, "can_reward": False}, timeout=30)
            if r2.status_code not in (200, 201, 204):
                return Result(self.name, "failed", http_status=r2.status_code, url=draft_url,
                              detail=f"写正文失败 http={r2.status_code}；草稿 id={did} 已生成，可到创作中心手动发布")

            if not bool(self.settings.get("zhihu", {}).get("web_auto_publish", False)):
                return Result(self.name, "drafted", url=draft_url, http_status=r2.status_code,
                              detail=f"网页通道已建草稿并写入正文（id={did}）；web_auto_publish=false，未公开发布")

            text_len = len(re.sub(r"<[^>]+>", "", html))
            pub_body = {
                "action": "article",
                "data": {
                    "draft": {"id": did},
                    "title": {"title": title},
                    "hybrid": {"html": html, "textLength": text_len},
                    "extra_info": {"pc_business_params": json.dumps(
                        {"title": title, "content": html}, ensure_ascii=False)},
                },
            }
            r3 = self.session.post(
                f"{w['publish_base']}{w['publish_path']}",
                headers=self._headers(cookie, publish=True), json=pub_body, timeout=30)
            d3 = _json(r3)
            pid = self._published_id(d3)
            ok = r3.status_code == 200 and d3.get("code") in (0, "0") and bool(pid)
            link = f"https://zhuanlan.zhihu.com/p/{pid}" if pid else draft_url
            return Result(self.name, "published" if ok else "failed", url=link,
                          http_status=r3.status_code,
                          detail=f"draft_id={did} | publish http={r3.status_code} "
                                 f"code={d3.get('code')!r} article_id={pid or '(none)'} "
                                 f"msg={str(d3.get('msg') or d3.get('message') or '')[:100]}"
                                 + ("" if ok else " | 草稿仍在，可到创作中心手动发布；"
                                    "公开发布可能需要前端动态签名 x-zse-96"))
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")


class ZhihuPublisher(BasePublisher):
    """知乎通道路由：A=off / C=openapi / B=web / auto=有官方凭据优先、否则网页。

    name 固定为 zhihu，保证配额、错峰、平台化标题都按同一平台处理。
    """
    name = "zhihu"

    def _impl(self) -> BasePublisher | None:
        z = self.settings.get("zhihu", {})
        raw = z.get("mode", "auto")
        # YAML 1.1 会把裸 off / on 解析成布尔值；兼容旧配置，别把 off 静默升级成 auto
        if raw is False or str(raw).lower() in ("false", "off"):
            mode = "off"
        elif raw is True or str(raw).lower() in ("true", "on"):
            mode = "auto"
        else:
            mode = str(raw or "auto").lower()
        if mode not in ("off", "openapi", "web", "auto"):
            mode = "auto"
        if mode == "off":
            return None
        has_api = bool((self.secrets.get("ZHIHU_APP_KEY") or "").strip()
                       and (self.secrets.get("ZHIHU_APP_SECRET") or "").strip())
        has_web = bool(clean_cookie(self.secrets.get("ZHIHU_COOKIE") or ""))
        if mode == "openapi":
            return _ZhihuOpenApi(self.cfg, self.settings, self.secrets, self.dry_run) if has_api else None
        if mode == "web":
            return _ZhihuWeb(self.cfg, self.settings, self.secrets, self.dry_run) if has_web else None
        if has_api and z.get("standing_consent", False):
            return _ZhihuOpenApi(self.cfg, self.settings, self.secrets, self.dry_run)
        if has_web:
            return _ZhihuWeb(self.cfg, self.settings, self.secrets, self.dry_run)
        if has_api:
            # 有官方凭据但没授权：交给 OpenAPI 实现返回如实 skipped，不静默改走网页。
            return _ZhihuOpenApi(self.cfg, self.settings, self.secrets, self.dry_run)
        return None

    def _impl_or_default(self) -> BasePublisher:
        return self._impl() or _ZhihuOpenApi(self.cfg, self.settings, self.secrets, self.dry_run)

    def build(self, article: dict) -> tuple[str, dict, dict]:
        return self._impl_or_default().build(article)

    def judge(self, resp: requests.Response) -> tuple[bool, str, str]:
        return self._impl_or_default().judge(resp)

    def publish(self, article: dict) -> Result:
        impl = self._impl()
        if impl is None:
            return Result(self.name, "skipped",
                          detail="知乎无可用通道：缺 ZHIHU_APP_KEY/APP_SECRET（官方 OpenAPI）"
                                 "与 ZHIHU_COOKIE（网页会话），或 zhihu.mode=off；按约定跳过，不假报成功")
        return impl.publish(article)


# --------------------------------------------------------------------------- #
# 掘金
# --------------------------------------------------------------------------- #

class JuejinPublisher(BasePublisher):
    name = "juejin"

    def build(self, article: dict) -> tuple[str, dict, dict]:
        c = self.cfg
        q = c["query"]
        cookie = self.cookie("JUEJIN_COOKIE")
        uid = clean_param(self.secrets.get("JUEJIN_UUID", "") or "")
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
            uid = clean_param(self.secrets.get("JUEJIN_UUID", "") or "")
            pub_url = f"{c['api_base']}{c['endpoints']['publish']}?aid={q['aid']}&uuid={uid}&spider={q['spider']}"
            pub_body = {"draft_id": draft_id, "sync_to_org": False, "column_ids": [], "theme_ids": []}
            r2 = self.session.post(pub_url, headers=headers, json=pub_body, timeout=30)
            d2 = _json(r2)
            # 严格判定：必须 HTTP 200 且响应里出现「明确的」成功信号。
            # 旧写法把字段缺失也当成功（err_no=None in (0, None) 恒为真），
            # 境外 IP 被风控拦截时返回 403 HTML / 空 JSON，会误报 published。
            ok = (
                r2.status_code == 200
                and (
                    bool(d2.get("data"))
                    or d2.get("err_no") == 0
                    or d2.get("code") in (0, 200)
                )
            )
            link = ""
            if isinstance(d2.get("data"), dict):
                link = str(d2["data"].get("article_url") or d2["data"].get("url") or "")
            return Result(self.name, "published" if ok else "failed", url=link,
                          http_status=r2.status_code,
                          detail=f"draft_id={draft_id} | http={r2.status_code} | "
                                 f"publish code={d2.get('code') or d2.get('err_no')} "
                                 f"msg={d2.get('msg') or d2.get('err_msg') or ''}")
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------- #
# CSDN
# --------------------------------------------------------------------------- #

class CsdnPublisher(BasePublisher):
    name = "csdn"

    def build(self, article: dict) -> tuple[str, dict, dict]:
        c = self.cfg
        path = c["path"]
        ct = c["content_type"]
        accept = c.get("accept", "*/*")
        key = str(c["ca_key"])
        nonce = str(uuid.uuid4())
        # 签名串里的 Accept / Content-Type 必须与下面实际发出的请求头逐字一致。
        to_sign = csdn_sign_string("POST", accept, ct, key, nonce, path).encode()
        sign = base64.b64encode(
            hmac.new(str(c["ca_sign_secret"]).encode(), to_sign, hashlib.sha256).digest()
        ).decode()
        headers = {
            "content-type": ct,
            "accept": accept,
            "origin": c["origin"],
            "referer": c["referer"],
            "cookie": self.cookie("CSDN_COOKIE"),
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "accept-language": "zh-CN",
            "x-ca-key": key,
            "x-ca-nonce": nonce,
            "x-ca-signature": sign,
            "x-ca-signature-headers": c["ca_signature_headers"],
        }
        # 请求体字段与类型必须和 CSDN 网页编辑器完全一致，否则 400 Bad Request。
        # 这些值是 2026-11-10 从浏览器真实请求里抓的（点一次「保存草稿」即抓到）。
        # 关键点：status=2、pubStatus=draft、not_auto_saved="1"（字符串）、
        # authorized_status=false（布尔）、is_new=1（数字）、creation_statement=0、
        # categories=""（字符串，不是数组）、cover_type=1。
        #
        # 2026-11-10 晚修正（实测结论，之前判断错了）：
        #   status=2 → 建草稿，接口返回成功但文章永远 404（从未公开发布）
        #   status=1 → **公开发布**，实测返回 code=200「成功」
        #   status=0 + pubStatus=publish → 400「今天发表文章数量已达到限制的2篇」
        #     （说明 status=0 走的才是额度校验分支；status=1 绕过了它）
        # 因此直发必须用 status=1。免费号每天 2 篇，额度用完时返回 400300011。
        ps = dict(c.get("payload_static") or {})
        publish_status = int(ps.get("status", 2))
        pub_status = str(ps.get("pubStatus", "draft"))
        body = {
            "title": self.title(article),
            "markdowncontent": article["markdown"],
            "content": article["html"],
            "readType": self.settings["csdn"]["read_type"],
            "level": 0,
            "tags": self.tags(article),
            "categories": "",
            "type": self.settings["csdn"]["article_type"],
            "original_link": "",
            "authorized_status": False,
            "not_auto_saved": "1",
            "source": "pc_mdeditor",
            "cover_images": [],
            "cover_type": 1,
            "is_new": 1,
            "vote_id": 0,
            "resource_id": "",
            "status": publish_status,
            "pubStatus": pub_status,
            "creation_statement": 0,
            "creator_activity_id": "",
        }
        return f"{c['api_base']}{path}", headers, body

    def judge(self, resp: requests.Response) -> tuple[bool, str, str]:
        data = _json(resp)
        code = data.get("code")
        msg = str(data.get("msg") or data.get("message") or "")
        # 业务码与 HTTP 状态都必须是 200：网关/WAF 拦截页有时也会带一个 JSON 体，
        # 只看 code 会把失败当成发布成功。
        ok = resp.status_code == 200 and code in (200, "200")
        d = data.get("data") or {}
        link = str(d.get("url") or "") if isinstance(d, dict) else ""
        # 额度用完是可预期的业务态，不是程序故障：如实说明「今日额度已用尽」，
        # 让上层知道「等明天」而不是无脑重试（重试只会一直撞同一堵墙）。
        if not ok and ("数量已达到限制" in msg or "达到限制" in msg or "限制的" in msg):
            return False, "", f"今日发文额度已用尽（{msg[:80]}），需次日重置"
        return ok, link, f"http={resp.status_code} code={code!r} msg={msg[:120]}"


def all_publishers(platforms_cfg: dict, settings: dict) -> list[BasePublisher]:
    secrets = {k: os.environ.get(k, "") for k in (
        "ZHIHU_APP_KEY", "ZHIHU_APP_SECRET", "ZHIHU_COOKIE",
        "JUEJIN_COOKIE", "JUEJIN_UUID", "CSDN_COOKIE",
    )}
    dry = bool(settings["publish"].get("dry_run", True))
    mapping = {"zhihu": ZhihuPublisher, "juejin": JuejinPublisher, "csdn": CsdnPublisher}
    out = []
    for name, cls in mapping.items():
        cfg = platforms_cfg["platforms"].get(name, {})
        if not cfg.get("enabled", False):
            continue
        # 知乎「浏览器通道」：纯 HTTP 的 web 通道依赖 x-zse-96 签名，实测已失效；
        # 浏览器通道由页面自己算签名，是 2026-11-10 实测发布成功的唯一路径。
        # 云端（settings.zhihu.mode=browser）走这条；本机默认仍走原有通道。
        if name == "zhihu" and str(
            (settings.get("zhihu") or {}).get("mode", "")
        ).lower() == "browser":
            out.append(_ZhihuBrowserAdapter(cfg, settings, secrets, dry))
            continue
        # CSDN「浏览器面板」通道：saveArticle 直发在零发文/额度满等场景会返回
        # code=200 但不落库（假成功），只有带封面走网页发布面板才是真发布。
        # 云端 settings.csdn.mode=browser 走这条；本机默认仍走接口版。
        if name == "csdn" and str(
            (settings.get("csdn") or {}).get("mode", "")
        ).lower() == "browser":
            out.append(_CsdnBrowserAdapter(cfg, settings, secrets, dry))
            continue
        out.append(cls(cfg, settings, secrets, dry))
    return out


class _ZhihuBrowserAdapter(BasePublisher):
    """把知乎浏览器通道包装成标准发布器接口（供云端 all_publishers 装配）。

    为什么不直接用 src/zhihu_browser.py：那个类不继承 BasePublisher，
    而 all_publishers 需要统一的 publish() -> Result 接口，才能复用
    配额闸门、错峰、失败不中断和台账回写。
    """

    name = "zhihu"

    def __init__(self, cfg: dict, settings: dict, secrets: dict, dry_run: bool):
        super().__init__(cfg, settings, secrets, dry_run)
        self._impl = None

    def required(self) -> list[str]:
        return ["ZHIHU_COOKIE"]

    def publish(self, article: dict) -> Result:
        if self.dry_run:
            return Result(self.name, "dry_run",
                          detail="知乎浏览器通道：云端需装 Playwright + Chromium，"
                                 "dry_run 不启动浏览器")
        if not (self.secrets.get("ZHIHU_COOKIE") or "").strip():
            return Result(self.name, "skipped", detail="缺少 Secrets: ZHIHU_COOKIE")
        try:
            from .zhihu_browser import ZhihuBrowserPublisher
        except Exception as e:
            return Result(self.name, "failed",
                          detail=f"无法加载知乎浏览器发布器（缺 playwright？）：{type(e).__name__}")
        bcfg = dict((self.settings.get("browser") or {}))
        # 云端是 Linux runner，用 Playwright 自带的 chromium（channel 留空）；
        # 本机默认 msedge。
        bcfg.setdefault("channel", "")
        pub = ZhihuBrowserPublisher(browser_cfg=bcfg, root=ROOT)
        try:
            return pub.publish_browser(
                article,
                title=self.title(article),
                body=article.get("markdown", ""),
                brief=self.brief(article),
                tags=self.tags(article),
            )
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")


class _CsdnBrowserAdapter(BasePublisher):
    """CSDN 浏览器面板发布器（云端赛道 A 用）。

    为什么不用接口直发：实测 `saveArticle status=1` 会回 `code=200 msg=success`
    但文章不落库、额度也不扣（假成功），会把台账记成「已发」导致真稿被去重跳过。
    网页发布面板是唯一验证过真发布的路径（2026-11-11 手动发一篇「发布成功！正在审核中」），
    且「添加封面」是红星必填项 —— 封面由本适配器按当天项目动态准备。
    """

    name = "csdn"

    def __init__(self, cfg: dict, settings: dict, secrets: dict, dry_run: bool):
        super().__init__(cfg, settings, secrets, dry_run)

    def required(self) -> list[str]:
        return ["CSDN_COOKIE"]

    def _cover_path(self, article: dict) -> str:
        """为当天项目准备封面：GitHub opengraph → 统一裁成 1200×675 JPG。

        2026-11-11 实测：手动发布成功用的封面正是 1200×675 的 JPG；
        直接喂 opengraph 的 PNG 原图时 CSDN 上传不落库。所以必须先转格式，
        规格对齐后再交给浏览器通道。每天项目不同 → 封面不同。
        下载/转换失败时退回仓库里那张已验证可发布的 JPG。
        """
        repo = str(article.get("repo") or "").strip()
        out = ROOT / "state" / "csdn_cover.jpg"
        if repo:
            try:
                import io
                from PIL import Image
                r = requests.get(
                    f"https://opengraph.githubassets.com/1/{repo}",
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
                if r.status_code == 200 and len(r.content) > 1000:
                    im = Image.open(io.BytesIO(r.content)).convert("RGB")
                    tw, th = 1200, 675
                    w, h = im.size
                    scale = max(tw / w, th / h)
                    im = im.resize((int(w * scale) + 1, int(h * scale) + 1),
                                   Image.LANCZOS)
                    w, h = im.size
                    left, top = (w - tw) // 2, (h - th) // 2
                    im = im.crop((left, top, left + tw, top + th))
                    out.parent.mkdir(parents=True, exist_ok=True)
                    im.save(str(out), "JPEG", quality=88)
                    return str(out)
            except Exception:
                pass
        fallback = ROOT / "drafts" / "2026-11-10" / "wordcraft-csdn-cover.jpg"
        return str(fallback) if fallback.exists() else ""

    def publish(self, article: dict) -> Result:
        if self.dry_run:
            return Result(self.name, "dry_run",
                          detail="CSDN 浏览器通道：云端需装 Playwright + Chromium，"
                                 "dry_run 不启动浏览器")
        if not (self.secrets.get("CSDN_COOKIE") or "").strip():
            return Result(self.name, "skipped", detail="缺少 Secrets: CSDN_COOKIE")
        cover = self._cover_path(article)
        if not cover:
            return Result(self.name, "failed",
                          detail="封面不可用：opengraph 下载失败且仓库内无备用封面")
        try:
            from .csdn_browser import CsdnBrowserPublisher
        except Exception as e:
            return Result(self.name, "failed",
                          detail=f"无法加载 CSDN 浏览器发布器（缺 playwright？）：{type(e).__name__}")
        bcfg = dict(self.settings.get("browser") or {})
        bcfg.setdefault("channel", "")   # 云端 Linux runner 用自带 chromium
        pub = CsdnBrowserPublisher(browser_cfg=bcfg, root=ROOT)
        try:
            return pub.publish_browser(
                article,
                title=self.title(article),
                body=article.get("markdown", ""),
                brief=self.brief(article),
                tags=self.tags(article),
                cover=cover,
            )
        except Exception as e:
            return Result(self.name, "failed", detail=f"{type(e).__name__}: {e}")
        finally:
            pub.close()
