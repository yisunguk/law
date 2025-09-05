# modules/legal_modes.py
from __future__ import annotations
import re
from typing import Tuple

# 간단한 의도/모드 정의
class Intent:
    QUICK = "quick"        # 일반 질의응답
    LAWFINDER = "lawfinder"  # 법령/조문 탐색
    MEMO = "memo"          # 간단 메모/정리
    DRAFT = "draft"        # 문안/초안 작성

def classify_intent(user_q: str) -> Tuple[str, float]:
    """
    매우 가벼운 규칙 기반 분류기(최소 동작용).
    반환: (모드, 신뢰도 0~1)
    """
    q = (user_q or "").strip()
    if not q:
        return Intent.QUICK, 0.0

    # 조문/법령 신호 → LAWFINDER
    if re.search(r'(법령|조문|제\d{1,4}조(의\d{1,3})?|시행령|시행규칙|.*법\b)', q):
        return Intent.LAWFINDER, 0.85

    # 초안/서식 → DRAFT
    if re.search(r'(초안|문안|서식|작성|draft)', q, re.I):
        return Intent.DRAFT, 0.7

    # 메모/정리 → MEMO
    if re.search(r'(메모|정리|노트|note)', q, re.I):
        return Intent.MEMO, 0.6

    return Intent.QUICK, 0.55

def build_sys_for_mode(mode: str, *, brief: bool = False) -> str:
    """
    모드별 시스템 프롬프트(요약형/상세형 선택 가능).
    """
    if mode == Intent.LAWFINDER:
        return (
            "당신은 한국 법령/조문 검색 보조원입니다. "
            "사용자가 특정 법령·조문을 찾거나 원문을 요청하면, "
            "법제처 DRF(OpenAPI)에서 제공되는 본문을 우선으로 근거와 함께 제시하세요. "
            "추정/창작 금지, 사실만 답변. 필요한 경우 조문 번호와 항·호를 명확히 표기하세요."
            + (" (간결하게)." if brief else "")
        )
    if mode == Intent.DRAFT:
        return (
            "당신은 법률 문안 초안 도우미입니다. "
            "요청한 문서의 구조를 제안하고, 법적 용어는 중립적으로 사용하세요. "
            "법령 인용 시 정확한 조문 번호를 병기하세요."
            + (" (핵심만 간결하게)." if brief else "")
        )
    if mode == Intent.MEMO:
        return (
            "당신은 요점 정리 도우미입니다. 목록화하고, 근거가 있는 부분만 명시하세요."
            + (" (짧게 요약)." if brief else "")
        )
    # 기본값
    return "당신은 신중하고 정확한 한국어 어시스턴트입니다." + (" (간결히 답변)." if brief else "")

def pick_mode(det_intent: str, conf: float) -> str:
    # 신뢰도 기준 간단 라우팅(필요시 임계값 조절)
    if det_intent == Intent.LAWFINDER and conf >= 0.70:
        return Intent.LAWFINDER
    if det_intent == Intent.DRAFT and conf >= 0.65:
        return Intent.DRAFT
    if det_intent == Intent.MEMO and conf >= 0.60:
        return Intent.MEMO
    return Intent.QUICK
