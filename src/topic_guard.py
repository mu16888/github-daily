#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""话题框架 v3 护栏。

依据技能方法论（2026-11-14 实际加载）：
  wechat-content-research  选题推导链 / 问题树 / 信源 S-A-B-C / 转换卡 / 评估 7 维
  gzh-mia-pipeline        标题承诺须正文兑现 / F-I-H-D 事实分级 / 输出合同
  verify-before-claim     四级标记，禁止把「觉得应该是」写成结论

校验对象是出稿时随稿落盘的 `drafts/<YYYY-MM-DD>/topic_card.json`（话题卡）。
**渐进闸门**：`gate.require_card=false` 时缺卡片只警告、不阻断，避免无人值守
流水线因存量稿件无元数据而零产出；改 true 即收紧为硬闸门。

用法：
    python -m src.topic_guard [YYYY-MM-DD]
    from src.topic_guard import check_topic, check_day
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CFG_FILE = ROOT / "config" / "topic_framework_v3.yaml"
_CACHE: dict = {}


def _cfg() -> dict:
    """读取框架配置；缺文件/缺依赖时返回空 dict，由调用方降级跳过。"""
    if _CACHE:
        return _CACHE
    try:
        import yaml
        d = yaml.safe_load(CFG_FILE.read_text(encoding="utf-8")) or {}
        if int((d.get("meta") or {}).get("version", 0)) >= 3:
            _CACHE.update(d)
    except Exception:
        pass
    return _CACHE


def _text(v: Any) -> str:
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return " ".join(str(x).strip() for x in v.values() if x)
    if isinstance(v, (list, tuple)):
        return " ".join(str(x).strip() for x in v if x)
    return str(v).strip() if v else ""


def check_topic(meta: dict | None, platform: str = "") -> dict:
    """校验一张话题卡，返回 {ok, skipped, missing_card, blocked_by, warnings, ...}。"""
    cfg = _cfg()
    if not cfg:
        return {"ok": True, "skipped": True, "missing_card": False,
                "blocked_by": [], "warnings": [],
                "reason": "话题框架配置未加载，护栏跳过"}

    gate = cfg.get("gate") or {}
    enforce = bool(gate.get("enforce", True))
    require_card = bool(gate.get("require_card", False))
    blocked: list[str] = []
    warnings: list[str] = []

    if not meta or not isinstance(meta, dict):
        missing = "缺话题卡 topic_card.json（推导链 / 信源 / 事实分级均未声明）"
        return {"ok": not require_card, "skipped": False, "missing_card": True,
                "blocked_by": [missing] if require_card else [],
                "warnings": [missing] if not require_card else [],
                "reason": missing, "enforced": enforce}

    # L0 支柱
    pillars = list(cfg.get("pillars") or [])
    pillar = _text(meta.get("pillar"))
    if pillars and pillar not in pillars:
        blocked.append(f"话题未落进任何支柱：{pillar or '（空）'}；可选：{'/'.join(pillars)}")

    # L2 推导链五段
    chain = meta.get("chain") or {}
    for f in (cfg.get("chain_fields") or []):
        if not _text(chain.get(f)):
            blocked.append(f"推导链缺字段 chain.{f}")
    scene = chain.get("scene")
    if isinstance(scene, dict):
        filled = sum(1 for v in scene.values() if _text(v))
        if filled < 4:
            warnings.append(f"场景化只填了 {filled}/5 要素，行业×角色×场景×阻碍×期望结果应写全")

    # 低档话题模式
    hay = " ".join([_text(chain.get("signal")), _text(chain.get("judgement")),
                    _text(meta.get("title"))])
    for pat in (cfg.get("banned_topic_patterns") or []):
        if pat and pat in hay:
            blocked.append(f"命中低档话题模式：{pat}")

    # L4 信源门
    sources = [s for s in (meta.get("sources") or []) if isinstance(s, dict)]
    valid_s = [s for s in sources
               if str(s.get("tier", "")).upper() == "S" and _text(s.get("url"))]
    core_facts = [x for x in (meta.get("core_facts") or []) if _text(x)]
    if core_facts and not valid_s:
        blocked.append("有核心事实但缺 S 级原始来源（链接+等级）；按规则须标 ⚠️待核实且不得进标题")
    if cfg.get("reject_c_as_fact_source", True):
        for s in sources:
            if str(s.get("tier", "")).upper() == "C" and s.get("role") == "fact_source":
                blocked.append("C 级来源被标为 fact_source（聚合/转载/软文不能支撑核心判断）")
    if not sources:
        warnings.append("未声明任何来源")

    # L6 事实分级与标题承诺
    grades = set((cfg.get("fact_grades") or {}).keys()) or {"F", "I", "H", "D"}
    forbidden = set(cfg.get("title_forbidden_grades") or ["H", "D"])
    allowed = set(cfg.get("title_allowed_grades") or ["F", "I"])
    claims = [c for c in (meta.get("title_claims") or []) if isinstance(c, dict)]
    for c in claims:
        g = str(c.get("grade", "")).upper()
        if g not in grades:
            blocked.append(f"标题断言事实分级非法：{g}")
        elif g in forbidden or g not in allowed:
            blocked.append(f"标题断言使用了禁止等级 {g}（只允许 F 与明确标注的 I）")
        if g == "I" and not c.get("in_body"):
            blocked.append("推断级(I)标题断言未声明正文兑现点 in_body=true")
    for fg in (meta.get("fact_grades") or []):
        if isinstance(fg, dict) and str(fg.get("grade", "")).upper() not in grades:
            blocked.append(f"事实分级非法：{fg.get('grade')}")
    if not claims:
        warnings.append("未声明 title_claims，标题承诺是否正文兑现未受护栏检查")

    # 一手现场降级
    deg = cfg.get("degradation") or {}
    if not bool(meta.get("first_hand", False)):
        if deg.get("require_degrade_note", True) and not _text(meta.get("degrade_note")):
            blocked.append("无一手现场但未写 degrade_note 降级说明")
    if deg.get("no_fictional_first_person", False) and meta.get("no_fictional_first_person") is not True:
        blocked.append("no_fictional_first_person 未声明为 true（禁止虚构店主/亲历叙事）")

    # 推荐字段（只警告）
    qt = meta.get("question_tree") or {}
    for f in (cfg.get("question_tree_fields") or []):
        if not _text(qt.get(f)):
            warnings.append(f"问题树缺 question_tree.{f}")
    ev = meta.get("evaluation") or {}
    for f in (cfg.get("evaluation_fields") or []):
        if f not in ev:
            warnings.append(f"评估 7 维缺 evaluation.{f}")

    ok = (not blocked) or (not enforce)
    return {"ok": ok, "skipped": False, "missing_card": False,
            "blocked_by": blocked, "warnings": warnings,
            "reason": "；".join(blocked) if blocked else "通过",
            "enforced": enforce, "pillar": pillar,
            "sources_s": len(valid_s), "claims": len(claims)}


def load_card(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_day(day: str, drafts_dir: Path | None = None) -> dict:
    """校验某日稿件的话题卡。卡片路径 drafts/<day>/topic_card.json。"""
    base = drafts_dir or (ROOT / "drafts" / day)
    card = base / "topic_card.json"
    r = check_topic(load_card(card) if card.exists() else None)
    r["card"] = str(card)
    r["day"] = day
    return r


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    r = check_day(day)
    cfg = _cfg()
    print(f"[话题框架 v3] track={(cfg.get('meta') or {}).get('track')} "
          f"enforce={r.get('enforced')} require_card={(cfg.get('gate') or {}).get('require_card')}")
    print(f"  卡片：{r['card']}")
    if r.get("skipped"):
        print(f"  跳过：{r['reason']}")
        return 0
    status = "✅ 通过" if r["ok"] else "⛔ 拦截"
    if r.get("missing_card"):
        status = "⚠️ 缺卡（渐进期不阻断）"
    print(f"  结果：{status}  S级源={r.get('sources_s', 0)}  标题断言={r.get('claims', 0)}")
    for x in r["blocked_by"]:
        print(f"    ⛔ {x}")
    for x in r["warnings"][:8]:
        print(f"    ⚠️  {x}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
