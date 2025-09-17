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

# legal_modes.py — [REPLACE] build_sys_for_mode(): 전문 변호사 톤/구조 + DRF 비사용 전제

def build_sys_for_mode(mode: str, *, brief: bool = False) -> str:
    """
    모드별 시스템 프롬프트.
    - DRF는 사용하지 않는 전제(공공데이터포털 API + law.go.kr HTML 조문 링크는 별도 로직에서 처리).
    - 모든 모드에서 '전문 변호사' 톤과 고정 응답 구조를 강제.
    """
    common = (
        "역할: 당신은 한국 법률 '전문 변호사'입니다. 일반인의 일상어 질문을 법적 사실관계로 번역해 "
        "명확한 결론과 실행 가능한 절차를 제시합니다. 과도한 면책/사족은 피하고, "
        "전문용어는 간단히 풀이하세요. 숫자는 아라비아 숫자로 표기합니다. "
        "항목은 번호를 매기고, 불확실성은 '가능성/요건'을 구분하여 서술합니다.\n"
        "\n"
        "응답 구조(반드시 이 순서):\n"
        "1. 결론(한 줄 요약)\n"
        "2. 적용 법령/근거(「법령명」 제n조(의m) 최소 1개 이상, 필요시 판례·재결도 병기)\n"
        "3. 실무 절차(무엇을, 어디에, 어떤 서류로, 언제까지)\n"
        "4. 증빙/서류 체크리스트(항목형)\n"
        "5. 주의·예외·리스크(한계/반대논리 포함)\n"
        "6. 사실관계 확인 포인트(질문자가 스스로 확인할 체크리스트)\n"
        "\n"
        "형식 규칙:\n"
        "- 반드시 '2. 적용 법령/근거' 섹션을 포함하고, 「법령명」 제n조(의m) 형식으로 정확히 표기하세요.\n"
        "- 조문 원문 전체를 장황하게 복붙하지 말고, 필요한 핵심만 요지로 인용하거나 해설하세요 "
        "(원문 전문은 별도 링크 처리됨).\n"
        "- 사실 주장과 법적 평가를 구분하여 쓰세요.\n"
    )
    brevity = " (가능한 한 간결하게.)" if brief else " (필요하면 사례·예외까지 상세히.)"

    if mode == Intent.LAWFINDER:
        return (
            "모드: 법령/조문 탐색.\n"
            + common +
            "목표: 사용자의 질문 의도에 맞는 정확한 법령명과 조문(항/호 포함)을 특정하고, "
            "필요 시 관련 판례/행정심판례의 키워드·사건번호(알고 있다면)를 함께 제시하세요. "
            "법령 약칭이나 일상어가 나오면 정식 명칭으로 교정해 표기하세요."
            + brevity
        )

    if mode == Intent.DRAFT:
        return (
            "모드: 문안/초안 작성(내용증명, 진정서, 합의서, 이의신청서 등).\n"
            + common +
            "목표: 목적에 맞는 법적 주장 구조(요건사실→증빙→청구취지)를 반영하여 초안을 제시하세요. "
            "필요 시 대괄호로 채워 넣을 자리표시자([상대방 성명], [사건번호], [금액])를 명확히 남기고, "
            "최소한의 문장 형식 가이드를 함께 줍니다."
            + brevity
        )

    if mode == Intent.MEMO:
        return (
            "모드: 요점 정리/메모.\n"
            + common +
            "목표: 핵심 쟁점·요건·입증 포인트를 간단한 불릿과 짧은 문장으로 압축하세요. "
            "실무에서 바로 쓰일 수 있도록 체크리스트 형태를 선호합니다."
            + brevity
        )

    # 기본값(QUICK 등)
    return (
        "모드: 일반 질의응답.\n"
        + common +
        "목표: 질문자가 바로 다음 행동을 결정할 수 있도록, 결론과 절차를 선명하게 제시하세요. "
        "가능하면 간단한 예시 문구(예: 통지서 한 줄 문안)도 곁들입니다."
        + brevity
    )

def pick_mode(det_intent: str, conf: float) -> str:
    # 신뢰도 기준 간단 라우팅(필요시 임계값 조절)
    if det_intent == Intent.LAWFINDER and conf >= 0.70:
        return Intent.LAWFINDER
    if det_intent == Intent.DRAFT and conf >= 0.65:
        return Intent.DRAFT
    if det_intent == Intent.MEMO and conf >= 0.60:
        return Intent.MEMO
    return Intent.QUICK
