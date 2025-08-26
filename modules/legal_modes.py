# modules/legal_modes.py
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from typing import Tuple, Optional
import re, json

# === Helpers: accident routing + simple quick detector ===
ACCIDENT_MEMO_HINTS = [
    "사고","교통사고","접촉사고","충돌","추돌","버스","택시","화물","자전거","보행자",
    "운전자","가해자","피해자","과실","책임","보험","자동차손해배상","국가배상","시설물","도로"
]
COMP_OR_FAULT_HINTS = [
    "보상","배상","청구","합의","합의금","가능","받을 수 있","받나","되나","되나요","되냐"
]

def is_accident_memo(text: str) -> bool:
    t = text or ""
    return (any(k in t for k in ACCIDENT_MEMO_HINTS)
            and (any(k in t for k in COMP_OR_FAULT_HINTS)
                 or re.search(r"(과실|책임|보험|배상|보상)", t)))

def looks_simple_quick(text: str) -> bool:
    t = (text or "").strip()
    if len(t) <= 32 and re.search(r"(뜻|의미|정의|요약|한줄|무엇|뭔가요?|벌금|과태료\s*얼마|제\d+조)", t):
        return True
    if len(t) <= 25 and not re.search(r"[?.!]", t) and len(t.split()) <= 4:
        return True
    return False

class Intent(str, Enum):
    QUICK = "quick"
    LAWFINDER = "lawfinder"
    MEMO = "memo"
    DRAFT = "draft"

SYS_COMMON = (
    "너는 한국어로 답하는 법률 상담 보조원이다. "
    "법제처 국가법령정보(DB) 기반의 용어를 사용하고, 과도한 단정은 피한다. "
    "사실관계가 불명확하면 전제와 한계를 명시한다."
)
SYS_BRIEF = "가능하면 간결하게 핵심만 정리하라."

MODE_SYS = {
    Intent.QUICK:  "요청이 짧은 정의/범위/조문 의미라면 간단 명료하게 설명하라.",
    Intent.LAWFINDER:
        "관련 법령/조문/행정규칙/자치법규 후보를 제시하고, 조문 번호를 명확히 적어라. "
        "각 법령의 적용 범위와 핵심 키워드를 간단히 요약하라.",
    Intent.MEMO:
        """법률 자문 메모 형식으로 정리하라.
1. 자문요지
2. 적용 법령/근거
3. 핵심 판단
4. 권고 조치"""
        "1) 자문요지  2) 적용 법령/근거  3) 핵심 판단  4) 권고 조치",
    Intent.DRAFT:
        "사용자가 요청한 문서/조항 초안을 제시하고, 변수(날짜/당사자/금액 등)는 대괄호로 표시하라.",
}

def build_sys_for_mode(mode: Intent, brief: bool = False) -> str:
    base = SYS_COMMON
    if brief:
        base += "\n" + SYS_BRIEF
    return base + "\n" + MODE_SYS[mode]

def classify_intent(q: str) -> Tuple[Intent, float]:
    text = (q or "").strip()
    if re.search(r"(제?\s*\d{1,4}\s*조(?:의\d{1,3})?)", text):
        return (Intent.QUICK, 0.85)
    if any(k in text for k in ["간단", "짧게", "요약", "뜻", "정의", "무엇", "뭐야"]):
        return (Intent.QUICK, 0.8)
    if any(k in text for k in ["링크", "원문", "찾아", "검색", "근거", "관련 법", "조문"]):
        return (Intent.LAWFINDER, 0.8)
    if any(k in text for k in ["자문", "판단", "책임", "위험", "벌금", "처벌", "배상", "소송", "가능", "되나요", "되나", "되냐", "조치"]):
        return (Intent.MEMO, 0.8)
    if any(k in text for k in ["계약", "통지", "서식", "양식", "조항 작성", "조항 만들어"]):
        return (Intent.DRAFT, 0.85)
    return (Intent.QUICK, 0.55)

def pick_mode(intent: Intent, conf: float) -> Intent:
    return intent if conf >= 0.55 else Intent.QUICK

@dataclass
class IntentVote:
    intent: Intent
    confidence: float = 0.75
    needs_lookup: bool = False
    reason: str = ""

def classify_intent_llm(q: str, *, client=None, model: Optional[str] = None) -> Optional[IntentVote]:
    if not client or not model or not (q or "").strip():
        return None
    SYS = (
        "너는 법률상담 챗봇의 라우터다. 아래 중 하나로 분류해 JSON만 출력하라.\n"
        "- quick | lawfinder | memo | draft\n"
        '형식: {"intent":"quick","confidence":0.9,"needs_lookup":true}'
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content":SYS},{"role":"user","content":q.strip()}],
            temperature=0.0, max_tokens=80,
        )
        txt = (resp.choices[0].message.content or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
        if m: txt = m.group(1).strip()
        data = json.loads(txt)
        return IntentVote(
            intent=Intent(data["intent"]),
            confidence=float(data.get("confidence", 0.75)),
            needs_lookup=bool(data.get("needs_lookup", False)),
            reason=data.get("reason",""),
        )
    except Exception:
        return None

def route_intent(q: str, *, client=None, model: Optional[str] = None) -> tuple[Intent, float, bool]:
    v = classify_intent_llm(q, client=client, model=model)
    if v:
        return (v.intent, v.confidence, v.needs_lookup)
    intent, conf = classify_intent(q)
    needs_lookup = intent in (Intent.LAWFINDER, Intent.MEMO)
    return (intent, conf, needs_lookup)
