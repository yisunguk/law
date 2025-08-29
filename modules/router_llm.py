# modules/router_llm.py
from __future__ import annotations
from typing import Dict, Any, List
import json
import re

__all__ = ["ROUTER_SYSTEM", "make_plan_with_llm"]

# ──────────────────────────────────────────────────────────────────────────────
# LLM Router System Prompt
# - 상담(ADVICE) 모드 추가
# - 후보 조문(candidates)까지 LLM이 직접 산출: law_name, article_label, mst, jo
# - 반드시 JSON만 출력하도록 강제
# ──────────────────────────────────────────────────────────────────────────────
ROUTER_SYSTEM = """
너는 한국 법령 질의를 API 호출 계획으로 변환하는 라우터다.
반드시 아래 JSON 한 개만 출력하라(코드블록, 설명, 접두/접미 문장 금지).

{
  "action": "GET_ARTICLE" | "SEARCH_LAW" | "ADVICE" | "QUICK",
  "law_name": "정확한 법령명(모르면 \"\")",
  "mst": "알면 기입, 모르면 \"\"",
  "article_label": "예: 제83조, 제83조의2 (모르면 \"\")",
  "jo": "6자리 조문코드(가능하면 직접 계산, 예: 83조→008300, 10조의2→001002, 모르면 \"\")",
  "efYd": "요청 시행일 YYYYMMDD (없으면 \"\")",
  "notes": "추가 설명(선택, 없으면 \"\")",
  "candidates": [
    {
      "law_name": "민법",
      "article_label": "제839조의2",
      "mst": "",
      "jo": ""
    }
  ]
}

규칙:
1) 사용자가 '83조', '제 83 조', '83조의2'처럼 말해도 네가 스스로 jo(6자리)를 계산하라.
2) 법령명이 불명확하거나 복수 후보가 있는 경우, candidates 배열에 우선순위가 높은 항목부터 1~3개를 넣어라.
3) 상담형 질문(예: 국제결혼 이혼·재산분할)은 "ADVICE"를 사용하고, candidates에 관련 근거 조문들을 작성하라.
4) 확신이 없으면 "SEARCH_LAW"를 사용하라(그 외 필드는 빈 문자열 허용).
5) 불필요한 문장 출력 금지. 위 JSON 구조 그대로, 한 개만 출력.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Robust JSON extractor (LLM이 실수로 텍스트를 섞어도 { ... } 블록만 추출)
# ──────────────────────────────────────────────────────────────────────────────
_JSON_BLOCK = re.compile(r'\{[\s\S]*\}', re.M)

def _safe_json_loads(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    m = _JSON_BLOCK.search(text)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"action": "QUICK", "notes": "parse_error", "raw": (text or "")[:2000]}

# ──────────────────────────────────────────────────────────────────────────────
# Plan sanitizer (필수 필드 보정 + candidates 정형화)
# ──────────────────────────────────────────────────────────────────────────────
def _sanitize_candidates(arr: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not isinstance(arr, list):
        return out
    for it in arr:
        if not isinstance(it, dict):
            continue
        out.append({
            "law_name":      (it.get("law_name") or "").strip(),
            "article_label": (it.get("article_label") or "").strip(),
            "mst":           (it.get("mst") or "").strip(),
            "jo":            _clean_jo(it.get("jo") or ""),
        })
    # 중복 제거(법령명+조문라벨 기준)
    dedup = []
    seen = set()
    for c in out:
        key = (c["law_name"], c["article_label"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(c)
    return dedup[:3]  # 과도한 후보 방지

def _clean_jo(jo: str) -> str:
    jo = (jo or "").strip()
    return jo if re.fullmatch(r"\d{6}", jo) else ""

def _ensure_defaults(plan: Dict[str, Any]) -> Dict[str, Any]:
    plan = dict(plan or {})
    plan["action"] = (plan.get("action") or "QUICK").upper()
    for k in ("law_name", "mst", "article_label", "jo", "efYd", "notes"):
        plan[k] = (plan.get(k) or "").strip()
    plan["jo"] = _clean_jo(plan["jo"])
    if plan.get("efYd") and not re.fullmatch(r"\d{8}", plan["efYd"]):
        plan["efYd"] = ""
    plan["candidates"] = _sanitize_candidates(plan.get("candidates"))
    return plan

# ──────────────────────────────────────────────────────────────────────────────
# Public API
# - client: OpenAI 혹은 AzureOpenAI ChatCompletions 호환 클라이언트
# - model: 라우터 전용 소형 모델 지정 가능(미지정 시 client.router_model 또는 gpt-4o-mini)
# ──────────────────────────────────────────────────────────────────────────────
def make_plan_with_llm(client, user_q: str, *, model: str | None = None) -> Dict[str, Any]:
    resp = client.chat.completions.create(
        model=model or getattr(client, "router_model", None) or "gpt-4o-mini",
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM},
            {"role": "user", "content": user_q},
        ],
        temperature=0,
    )
    raw = (resp.choices[0].message.content or "").strip()
    plan = _safe_json_loads(raw)
    return _ensure_defaults(plan)
