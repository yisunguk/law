# modules/legal_modes.py
from __future__ import annotations
from enum import Enum
from typing import Tuple

class Intent(str, Enum):
    QUICK = "quick"
    LAWFINDER = "lawfinder"
    MEMO = "memo"
    DRAFT = "draft"

# 모든 모드에 공통 적용
SYS_COMMON = (
    "당신은 대한민국 변호사다. 모든 답변은 한국어로, 과장 없이 간결하게 작성한다. "
    "불확실하면 ‘추가 확인 필요: 사유’를 명시한다. "
    "공식 링크는 law.go.kr 또는 glaw.scourt.go.kr만 사용한다. "
    "모든 목록 불릿은 반드시 하이픈 '-'으로 시작한다. "
    "조문 표기는 '민법 제750조'처럼 ‘법령명 제N조’ 형식으로 쓴다. "
    "링크는 2) 적용 법령/규정의 각 불릿 텍스트에 **인라인**으로 포함하고, 별도의 ‘참고 링크’ 섹션은 만들지 않는다."
)

# 모드별 규칙
SYS_QUICK = (
    "출력형식: 3~5개 불릿으로 핵심만 요약. 불필요한 서론 금지. "
    "가능하면 마지막에 ‘주의/예외’ 1줄만."
)
SYS_LAWFINDER = (
    "출력형식: 관련 법령/행정규칙/자치법규 3~7개 목록. "
    "각 항목은 ‘명칭(구분, 소관부처) — 요지 1문장 — [원문](절대URL)’ 형태. "
    "장문 인용·중복 금지."
)
SYS_MEMO = (
     "출력형식(고정): "
    "1) 사건 요지(2~4문장) "
    "2) 적용 법령/규정(≤5) — 각 불릿은 '- '으로 시작하고 ‘법령명 제N조(간단 요지)’ 형식으로 쓰며, 각 항목에 **세부조항 링크를 인라인으로 포함** "
    "3) 핵심 판단(3~6 불릿) "
    "4) 근거 조문 요지(쟁점당 1~2개, 각 1~2문장) "
    "5) 리스크/예외(≤4) "
    "6) 즉시 조치 체크리스트(3~5). "
    "동일 내용 반복 금지, 한 번만 출력. "
    "각 섹션 제목과 본문은 반드시 줄바꿈으로 구분한다."
)
SYS_DRAFT = (
    "출력형식: 제목, 목적, 정의(필요시), 본문 조항(번호), 서명 블록. "
    "가변값은 <각괄호> 변수로 표기(예: <당사자A>, <금액>, <기한>). 문체는 ‘~한다’."
)

MODE_SYS = {
    Intent.QUICK: SYS_QUICK,
    Intent.LAWFINDER: SYS_LAWFINDER,
    Intent.MEMO: SYS_MEMO,
    Intent.DRAFT: SYS_DRAFT,
}

# (선택) 간단 모드 애드온
SYS_BRIEF = "가능하면 각 섹션을 1~3줄로 제한하고, 총 분량을 180~280단어로 요약하라."

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
    return (Intent.LAWFINDER, 0.6)  # 안전 기본값

def pick_mode(intent: Intent, conf: float) -> Intent:
    if conf >= 0.7:
        return intent
    if intent == Intent.QUICK:
        return Intent.LAWFINDER   # 모호하면 상향
    if intent == Intent.LAWFINDER:
        return Intent.MEMO
    return intent

def build_sys_for_mode(mode: Intent, brief: bool = False) -> str:
    base = SYS_COMMON
    if brief:
        base += "\n" + SYS_BRIEF
    return base + "\n" + MODE_SYS[mode]
