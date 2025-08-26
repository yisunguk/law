# modules/legal_modes.py
from __future__ import annotations
from enum import Enum
from typing import Tuple
# ▼ 추가
from dataclasses import dataclass
import json, re

class Intent(str, Enum):
    QUICK = "quick"
    LAWFINDER = "lawfinder"
    MEMO = "memo"
    DRAFT = "draft"

# ... (기존 SYS_COMMON, MODE_SYS, SYS_BRIEF 동일)

# 파일 상단에 추가
def classify_intent(q: str) -> Tuple[Intent, float]:
    text = (q or "").strip()

    # ✅ 조문 번호 질의는 '단순 질의(quick)'
    if re.search(r"(제?\s*\d{1,4}\s*조(?:의\d{1,3})?)", text):
        return (Intent.QUICK, 0.85)

    # ✅ 단순 설명·정의형
    if any(k in text for k in ["간단", "짧게", "요약", "알려줘", "뭐야", "무엇", "뜻", "정의"]):
        return (Intent.QUICK, 0.8)

    # 🔎 링크/원문 탐색형
    if any(k in text for k in ["링크", "원문", "찾아", "검색", "근거", "관련 법", "조문"]):
        return (Intent.LAWFINDER, 0.8)

    # 🧑‍⚖️ 자문/판단형
    if any(k in text for k in ["가능", "책임", "위험", "벌금", "처벌", "배상", "소송", "해결",
                               "판단", "조치", "되나요", "되나", "되냐"]):
        return (Intent.MEMO, 0.8)

    # 📄 서식/계약 작성형
    if any(k in text for k in ["계약", "통지", "서식", "양식", "조항 작성", "조항 만들어"]):
        return (Intent.DRAFT, 0.85)

    # ✅ 기본값: 단순 질의
    return (Intent.QUICK, 0.55)

def pick_mode(intent: Intent, conf: float) -> Intent:
    # ✅ 상향 금지: 신뢰도 낮으면 QUICK 유지
    return intent if conf >= 0.55 else Intent.QUICK



# ▼ LLM 라우터 결과 구조
@dataclass
class IntentVote:
    intent: Intent
    confidence: float = 0.75
    needs_lookup: bool = False   # 툴(법령 조회) 필요 여부
    reason: str = ""

def classify_intent(q: str) -> Tuple[Intent, float]:
    text = (q or "")
    if any(k in text for k in ["간단", "짧게", "요약"]):
        return (Intent.QUICK, 0.9)
    if any(k in text for k in ["법령", "조문", "근거", "관련 법률"]):
        return (Intent.LAWFINDER, 0.8)
    if any(k in text for k in ["자문", "판단", "책임", "위험", "가능성"]):
        return (Intent.MEMO, 0.75)
    if any(k in text for k in ["조항", "계약", "통지", "서식", "양식"]):
        return (Intent.DRAFT, 0.85)
    # 🔁 백업 기본값은 보수적으로 '간단 질의'로
    return (Intent.QUICK, 0.55)

# ▼ 자동 상향 제거: 분류 결과를 가급적 신뢰
def pick_mode(intent: Intent, conf: float) -> Intent:
    # 신뢰도 0.55 이상이면 그대로 사용
    if conf >= 0.55:
        return intent
    # 매우 낮으면 과도한 법률 판단(MEMO) 대신 QUICK로 안전하게
    return Intent.QUICK

# ▼ 신규: LLM 기반 분류기
def classify_intent_llm(q: str, *, client=None, model: str | None = None) -> IntentVote | None:
    if not client or not model or not (q or "").strip():
        return None

    SYS = (
        "너는 법률상담 챗봇의 라우터다. 사용자의 질문을 다음 중 하나로 정확히 분류해 JSON만 출력하라.\n"
        "- quick: 단순 사실/정의/범위 설명, 특정 조문이나 개념 의미를 간단히 묻는 경우(예: '민법 839조가 뭐지?').\n"
        "- lawfinder: 관련 법령/조문/원문/링크를 찾아달라는 요청(예: '산재 관련 법령 링크 모아줘').\n"
        "- memo:주제 판단·책임·위험·가능성·조치 등 법률 자문을 요구(예: '이 경우 손해배상 가능?').\n"
        "- draft: 계약서/통지서/합의서 등 문서 작성.\n"
        "needs_lookup은 정확한 조문 확인이나 최신 원문 링크가 필요하면 true로 하라.\n"
        '출력 형식: {"intent":"quick|lawfinder|memo|draft","confidence":0.0~1.0,"needs_lookup":true|false}'
    )
    prompt = f"질문:\n{q.strip()}"

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content":SYS},{"role":"user","content":prompt}],
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

# ▼ 신규: 앱에서 한 번에 쓰도록 라우팅 헬퍼
def route_intent(q: str, *, client=None, model: str | None = None) -> tuple[Intent, float, bool]:
    v = classify_intent_llm(q, client=client, model=model)
    if v:
        return (v.intent, v.confidence, v.needs_lookup)
    # LLM 실패 시 기존 휴리스틱으로 백업
    intent, conf = classify_intent(q)
    needs_lookup = intent in (Intent.LAWFINDER, Intent.MEMO)
    return (intent, conf, needs_lookup)

def build_sys_for_mode(mode: Intent, brief: bool = False) -> str:
    base = SYS_COMMON
    if brief:
        base += "\n" + SYS_BRIEF
    return base + "\n" + MODE_SYS[mode]
