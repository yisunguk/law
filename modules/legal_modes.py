
# modules/legal_modes.py
from __future__ import annotations

import re
from enum import Enum
from typing import Tuple

# ====== Intent routing ======
class Intent(str, Enum):
    QUICK = "quick"        # 짧은 정의/요약/단답
    LAWFINDER = "lawfinder" # 조문·원문·링크 찾기
    MEMO = "memo"          # 자문서(메모) 형식
    DRAFT = "draft"        # 조항/문서 초안 작성

# ====== System prompts ======
SYS_COMMON = (
    "너는 한국어로 답하는 법률 상담 전문가다. "
    "법제처 국가법령정보(DB) 용어를 사용하고 과도한 단정은 피한다. "
    "사실과 법리를 구분하고, 사용자에게 유리/불리한 사정을 균형 있게 제시한다."
    """
[데이터 접근]
- 이 서비스는 국가법령정보공유서비스(법제처) OPEN API/DRF를 사용해 최신 법령 본문과 조문을 조회한다.
- "API로 직접 읽느냐"는 질문에 대해서는 "네, 국가법령정보공유서비스 OPEN API로 본문을 조회합니다"라고 명확히 답한다.

[도구 사용 규칙]
- 질문에 다음 신호가 하나라도 있으면 반드시 도구를 사용한다: "법령", "조문", "제[숫자]조", "DRF", "API", "본문", "원문", "요약하지 말".
- 도구 사용이 실패하면 가능한 범위에서 최신 링크(법제처/DRF)를 안내한다.

[조문 직접 인용 규칙]
- 사용자가 "본문/원문/조문 전문/요약하지 말"고 요청하면, 프롬프트로 제공된 "법령 본문 캡슐"의 텍스트를 **그대로** 인용한다.
- 임의 요약·의역 금지. 문장 순서 유지. 필요 시 1~2천자 내에서 앞부분부터 인용한다.
- 인용 형식:
  1) `요청하신 제○조` 제목
  2) 법제처 공식 링크(상세/DRF) 한 줄
  3) 이어서 원문 텍스트(코드펜스 또는 문단 그대로)
- 인용이 불충분하면 "다음 링크에서 전체를 확인" 문장을 덧붙여 링크를 반복 제시한다.

[출력 일관성]
- 링크만 제시하고 끝내지 않는다. (인용 가능할 때는 반드시 인용)
- 법령명·조문 번호는 한국어 표기 그대로 유지한다.
"""
)

SYS_BRIEF = (
    "가능하면 간결하게 답하되, 핵심 법적 기준은 빠뜨리지 말라. "
    "불필요한 서론/공손한 인사말은 생략한다."
    "제약조건: 반드시 OPEN API를 호출해 최신 법령 본문/조문을 조회하고 그 내용을 바탕으로 답한다."
)

MODE_SYS = {
    Intent.QUICK: (
        "아래 형식을 지켜 짧게 답하라:\n"
        "- 한 문단 정리\n"
        "- 필요 시 관련 법령 1~2개만 제시(인라인 링크 허용)."
    ),
    Intent.LAWFINDER: (
        "다음 정보를 찾아 요약하라:\n"
        "1) 법령명·조문·핵심 요지 (한 줄)\n"
        "2) 반드시 국가법령정보센터(법제처) 링크 제공\n"
        "3) 중복 법령은 피하고 최신 법령을 우선한다."
        "제약조건: 반드시 OPEN API를 호출해 최신 법령 본문/조문을 조회하고 그 내용을 바탕으로 답한다."
    ),
    # ★ Revised MEMO template ★
    Intent.MEMO: (
        "너는 실제 변호사라고 생각하고, 법률 자문서를 작성하듯 답변하라.\n"
        "\n"
        "1. 자문요지 : [두세 문장 이상의 요지, 의뢰인에게 설명하듯 변호사 어투로]\n"
        "\n"
        "2. 적용 법령/근거\n"
        "- [법령명 제n조 -링크생성] — 요지(한 줄)\n"
        "- [법령명 제n조 -링크생성] — 요지(한 줄)\n"
        "\n"
        "3. 핵심 판단\n"
        "- 각 쟁점은 반드시 별도 불릿(-)으로 나누고, 불릿마다 2~3문장 이상으로 작성한다.\n"
        "- 이 섹션에서는 법령명·조문번호·링크를 적지 말고, 사실관계에 대한 판단만 제시한다.\n"
        "\n"
        "4. 권고 조치\n"
        "- 실행 가능한 조치를 단계별·실무적으로 제시한다(체크리스트 수준으로 구체화).\n"
        "\n"
        "규칙:\n"
        "- 제목과 번호, 콜론 형식을 정확히 지킨다(예: \"1. 자문요지 :\").\n"
        "- 링크는 반드시 \"2. 적용 법령/근거\"에서만 사용한다.\n"
        "- 필요 시 '해설' 소제목을 쓸 수 있으나, 링크는 그 안에서만 인라인 허용."
    ),
    Intent.DRAFT: (
        "- 요청한 문서/조항의 초안을 한국어로 작성하라.\n"
        "- 구조: 제목 → 목적 → 정의(필요시) → 본문 조항 → 부칙(필요시)\n"
        "- 숫자/기간/금액/당사자는 대괄호로 표시한다(예: [금액]).\n"
        "- 관련 조문이 있으면 인용하고, 가능하면 조문 링크도 제시한다."
        "- 제약조건: 반드시 OPEN API를 호출해 최신 법령 본문/조문을 조회하고 그 내용을 바탕으로 답한다."
    ),
}

def build_sys_for_mode(mode: Intent, brief: bool = False) -> str:
    base = SYS_COMMON
    if mode == Intent.LAWFINDER:
        base += """
[LAWFINDER 전용]
- 법령 질의에서는 위 '도구 사용 규칙'과 '조문 직접 인용 규칙'을 우선 적용한다.
- 조문 번호(예: 제83조)가 질문에 있으면 그 조문을 최우선으로 제시한다.
"""
    return base + "\n" + MODE_SYS[mode]

# ====== Output post-processor (for MEMO tidy) ======
def tidy_memo(md: str) -> str:
    """
    모델 출력이 들쭉날쭉할 때 최소한의 마크다운 정리를 수행한다.
    - 과다 공백 → 1개로
    - 글머리 기호 통일('•' → '- ')
    - '링크 금지' 같은 지시문 누출 제거
    - 섹션 번호 라인에 콜론 강제
    """
    md = re.sub(r"\n{3,}", "\n\n", md)                # 과다 공백 축소
    md = re.sub(r"(?m)^\s*[•]\s*", "- ", md)           # 불릿 통일
    md = re.sub(r"\n\((?:링크\s*금지)\)\s*\n?", "\n", md)  # 지시문 누출 제거
    md = re.sub(r"—", " — ", md)                         # em-dash 주변 공백 정리
    md = re.sub(r"(?m)^(\d\.\s*[^\n:]+)\s*$", r"\1 :", md)  # 섹션 콜론 보정
    return md.strip()

# ====== Intent classification ======
_ARTICLE_PAT = re.compile(r"제\s*\d+\s*조(의\s*\d+)?")
_URL_PAT = re.compile(r"(https?://\S+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?)", re.I)

def classify_intent(q: str) -> Tuple[Intent, float]:
    t = (q or "").strip()

    # 1) URL 또는 명시적 검색 의도 → LAWFINDER
    if _URL_PAT.search(t):
        return (Intent.LAWFINDER, 0.96)
    SEARCH_HINTS = ["링크", "원문", "검색", "찾아", "상세보기", "열람", "조문", "법령", "법 이름"]
    if any(k in t for k in SEARCH_HINTS) or bool(_ARTICLE_PAT.search(t)):
        return (Intent.LAWFINDER, 0.90)

    # 2) 간단/정의형 요청 → QUICK
    if any(k in t for k in ["간단", "짧게", "요약", "뜻", "정의", "무엇", "뭐야"]):
        return (Intent.QUICK, 0.82)

    # 3) 자문/책임/조치형 → MEMO
    if any(k in t for k in ["자문", "판단", "책임", "위험", "벌금", "처벌", "배상", "소송", "가능", "되나요", "되나", "되냐", "조치"]):
        return (Intent.MEMO, 0.86)

    # 4) 초안/조항 작성 → DRAFT
    if any(k in t for k in ["계약", "통지", "서식", "양식", "조항 작성", "조항 만들어"]):
        return (Intent.DRAFT, 0.85)

    # 기본값: QUICK
    return (Intent.QUICK, 0.55)

def route_intent(q: str) -> Tuple[Intent, float, bool]:
    """
    returns: (결정된 Intent, 신뢰도, 외부 검색/링크 조회 필요 여부)
    - LAWFINDER와 MEMO는 일반적으로 법령 원문/링크 조회가 필요하므로 True
    - QUICK/DRAFT는 보통 False
    """
    det, conf = classify_intent(q)
    needs_lookup = det in (Intent.LAWFINDER, Intent.MEMO)
    return det, conf, needs_lookup

__all__ = [
    "Intent",
    "SYS_COMMON",
    "SYS_BRIEF",
    "MODE_SYS",
    "build_sys_for_mode",
    "tidy_memo",
    "classify_intent",
    "route_intent",
]
