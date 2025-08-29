# modules/router_llm.py
from __future__ import annotations
from typing import Dict, Any
import json
import re

__all__ = ["ROUTER_SYSTEM", "make_plan_with_llm"]

ROUTER_SYSTEM = """
너는 한국 법령 질의를 API 호출 계획으로 변환하는 라우터다.
반드시 아래 JSON만 출력하라.
{
  "action": "GET_ARTICLE" | "SEARCH_LAW" | "QUICK",
  "law_name": "정확한 법령명(모르면 빈 문자열)",
  "mst": "알면 기입, 모르면 빈 문자열",
  "article_label": "예: 제83조, 제83조의2 (모르면 빈 문자열)",
  "jo": "가능하면 직접 계산한 6자리 조문코드(예: 83조→008300, 10조의2→001002)",
  "efYd": "요청시행일 YYYYMMDD (없으면 빈 문자열)",
  "notes": "추가 설명(선택)"
}
규칙:
1) 사용자가 '83조', '제 83 조', '83조의2'처럼 말해도 네가 스스로 jo(6자리)를 계산해라.
2) 확신이 없으면 SEARCH_LAW를 먼저 계획하고, 다음 단계에서 GET_ARTICLE을 제안하라.
3) 불필요한 설명/문장 금지. 위 JSON만 출력.
"""

# JSON만 오도록 유도하지만, 혹시 코드펜스/문장 섞여도 안전하게 꺼내는 헬퍼
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

def _ensure_defaults(plan: Dict[str, Any]) -> Dict[str, Any]:
    # 필드 기본값 보정 + 대문자 정규화
    plan = dict(plan or {})
    plan["action"] = (plan.get("action") or "QUICK").upper()
    for k in ("law_name", "mst", "article_label", "jo", "efYd", "notes"):
        plan[k] = (plan.get(k) or "").strip()
    # jo는 6자리만 허용
    if plan["jo"] and not re.fullmatch(r"\d{6}", plan["jo"]):
        plan["jo"] = ""
    # efYd는 YYYYMMDD 형식만 허용
    if plan["efYd"] and not re.fullmatch(r"\d{8}", plan["efYd"]):
        plan["efYd"] = ""
    return plan

def make_plan_with_llm(client, user_q: str, *, model: str | None = None) -> Dict[str, Any]:
    """
    - OpenAI/Azure OpenAI Chat Completions 클라이언트를 그대로 받습니다.
    - 함수호출(tools) 없이 'JSON만 출력' 프롬프트를 사용합니다(환경 호환성↑).
    - 반환값: 실행 계획 딕셔너리 (action, law_name, mst, article_label, jo, efYd, notes)
    """
    resp = client.chat.completions.create(
        model=model or getattr(client, "router_model", None) or "gpt-4o-mini",
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM},
            {"role": "user", "content": user_q},
        ],
        temperature=0,
    )
    raw = resp.choices[0].message.content or ""
    plan = _safe_json_loads(raw)
    return _ensure_defaults(plan)
