# modules/router_llm.py
from __future__ import annotations
from typing import Optional, Dict, Any, List
import json, re

__all__ = ["ROUTER_SYSTEM", "make_plan_with_llm"]

# ─────────────────────────────────────────────────────────────────
# System Prompt (한국어)
# ─────────────────────────────────────────────────────────────────
ROUTER_SYSTEM = """
너는 한국 법령 질의를 API 호출 계획으로 변환하는 라우터다.
반드시 아래 JSON 한 개만 출력하라(코드블록, 설명, 접두/접미 문장 금지).

{
  "action": "GET_ARTICLE" | "GET_RESOURCE" | "SEARCH_LAW" | "ADVICE" | "QUICK",
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
6) 사용자가 일상어로 두서없이 묻더라도, 숨은 의도를 추론해 필요한 조문/판례 후보를 candidates에 넣어라.
7) 판례·재결·위원회 결정 등 법령 외 자료가 핵심이면 "GET_RESOURCE"를 사용하고
   { "kind": "판례|법령해석례|행정심판례|조세심판재결례|..." , "title": "검색어/사건명" } 필드를 채워라.
8) "ADVICE"를 택해도 candidates에는 최소 1~3개의 「법령명 + 제n조(의m)」를 넣어라(LLM가이드에 쓰인다).
"""
# modules/router_llm.py
import os
from typing import Optional, Dict, Any

SAFE_SYS = (
    "You are a safety rewriter. Rewrite the user's request so it avoids any violent, "
    "illegal, or harmful instructions. Keep the factual context. The output must: "
    "1) focus on lawful procedures and dispute resolution, "
    "2) avoid advising on violence or property damage, "
    "3) be a single concise Korean sentence suitable as a legal consultation question."
)

def rewrite_safe_prompt(client, user_text: str, *, model: Optional[str] = None,
                        temperature: float = 0.0) -> str:
    """
    사용자의 질문을 '폭력/불법 유도 없는 합법적 절차 문의'로 재서술.
    """
    if not user_text:
        return user_text or ""

    mdl = (
        model
        or os.getenv("AZURE_OPENAI_ROUTER_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_MODEL")  # 혹시 사용 중이라면
    )
    if not mdl:
        # 모델 정보가 전혀 없으면, 최소한의 치환만 수행
        return _regex_sanitize(user_text)

    msgs = [
        {"role": "system", "content": SAFE_SYS},
        {"role": "user", "content": user_text},
    ]
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=msgs,
            temperature=temperature,
        )
        out = (resp.choices[0].message.content or "").strip()
        return out or _regex_sanitize(user_text)
    except Exception:
        return _regex_sanitize(user_text)


# --- 경량 정규식 폴백 (라우터 실패 시) -----------------------------------------
import re
_VIOLENT = re.compile(
    r"(베(?:어|다)|부수(?:어|다)|때리(?:어|다)|죽이(?:어|다)|파괴|훼손|불지르|태우|폭행|칼로|망치로)",
    re.IGNORECASE,
)

def _regex_sanitize(s: str) -> str:
    if not s:
        return s
    t = _VIOLENT.sub("불법적/폭력적 행위", s)
    return (
        "다음 상황에 대해 폭력이나 불법행위를 권하지 않고, "
        "오직 법적으로 가능한 절차(민형사·행정)와 분쟁 해결 방법만 설명해 주세요: "
        + t
    )

# ─────────────────────────────────────────────────────────────────
# JSON block extractor (LLM이 텍스트를 섞어도 { ... }만 취함)
# ─────────────────────────────────────────────────────────────────
_JSON_BLOCK = re.compile(r"\{[\s\S]*\}", re.M)

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

# ─────────────────────────────────────────────────────────────────
# Plan sanitizer
# ─────────────────────────────────────────────────────────────────
def _clean_jo(jo: str) -> str:
    jo = (jo or "").strip()
    return jo if re.fullmatch(r"\d{6}", jo) else ""

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
    dedup = []
    seen = set()
    for c in out:
        key = (c["law_name"], c["article_label"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(c)
    return dedup[:3]

def _ensure_defaults(plan: Dict[str, Any]) -> Dict[str, Any]:
    plan = dict(plan or {})
    plan["action"] = (plan.get("action") or "QUICK").upper()
    for k in ("law_name", "mst", "article_label", "jo", "efYd", "notes"):
        plan[k] = (plan.get(k) or "").strip()
    plan["kind"]  = (plan.get("kind")  or "").strip()
    plan["title"] = (plan.get("title") or "").strip()
    plan["jo"] = _clean_jo(plan["jo"])
    if plan.get("efYd") and not re.fullmatch(r"\d{8}", plan["efYd"]):
        plan["efYd"] = ""
    plan["candidates"] = _sanitize_candidates(plan.get("candidates"))
    return plan

# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────
def make_plan_with_llm(client, user_q: str, *, model: str | None = None) -> Dict[str, Any]:
    """
    중앙 클라이언트(get_llm_client)와 라우터 전용 배포명(LLM_ROUTER_MODEL)을 사용.
    - client가 None이면 app.get_llm_client()로 생성
    - model이 None이면 LLM_ROUTER_MODEL > LLM_DEFAULT_MODEL > 안전값 순으로 선택
    """
    # 1) 클라이언트 확보(중앙화된 싱글톤 사용)
    if client is None:
        try:
            from app import get_llm_client
            client = get_llm_client()
        except Exception as _:
            raise RuntimeError("LLM client가 초기화되지 않았습니다.")

    # 2) 모델 선택(배포명)
    mdl = model
    if not mdl:
        try:
            from app import LLM_ROUTER_MODEL, LLM_DEFAULT_MODEL
            mdl = (LLM_ROUTER_MODEL or LLM_DEFAULT_MODEL)
        except Exception:
            mdl = None
    if not mdl:
        mdl = getattr(client, "router_model", None) or getattr(client, "default_model", None)
    if not mdl:
        mdl = "gpt-4o-leesunguk"  # 최후의 안전값(사용자 제공 배포명)

    # 3) 호출
    resp = client.chat.completions.create(
        model=mdl,
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM},
            {"role": "user", "content": user_q},
        ],
        temperature=0,
        max_tokens=900,
    )
    raw = (resp.choices[0].message.content or "").strip()
    plan = _safe_json_loads(raw)
    return _ensure_defaults(plan)
