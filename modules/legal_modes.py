# modules/legal_modes.py
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from typing import Tuple, Optional
import re, json

class Intent(str, Enum):
    QUICK = "quick"
    LAWFINDER = "lawfinder"
    MEMO = "memo"
    DRAFT = "draft"

SYS_COMMON = (
    "너는 한국어로 답하는 법률 상담 전문가야. "
    "법제처 국가법령정보(DB) 기반의 용어를 사용하고, 과도한 단정은 피한다. "
    "사실관계가 불명확하면 전제와 한계를 명시한다."
)
SYS_BRIEF = "가능하면 간결하게 핵심만 정리하라."

MODE_SYS = {
    Intent.QUICK: (
        "요청이 짧은 정의/법위/조문 의미라면 간단 명료하게 설명하라.\n"
        "반드시 조문을 인용하고 누르면 링크가 활성화 되어야 한다."
    ),

    Intent.LAWFINDER: (
        "관련 법령/조문/행정규칙/자치법규 후보를 제시하고, 조문 번호를 명확히 적어라.\n"
        "각 법령의 적용 범위와 핵심 키워드를 간단히 요약하라.\n"
        "반드시 조문을 인용하고 누르면 링크가 활성화 되어야 한다."
    ),

    Intent.MEMO: (
    "법률 자문 메모 형식으로 **아래 양식/제목을 그대로** 사용하라.\n"
    "1. 자문요지 : [두세 문장 이상의 요지, 변호사가 정리한 자문서 어투로]\n"
    "2. 적용 법령/근거\n"
    "- [법령명 제n조 -링크생성] — 요지(한 줄)\n"
    "3. 핵심 판단\n"
    "- 쟁점별 판단을 변호사의 시각에서 구체적으로 기술하라. (2~3문장 이상, 링크 금지)\n"
    "4. 권고 조치\n"
    "- 의뢰인이 실제로 취할 수 있는 단계적·실무적 조치를 변호사 조언처럼 작성하라.\n"
    "\n"
    "규칙:\n"
    "- 제목은 반드시 위의 한글표기와 번호를 그대로 쓰고, \"1. 자문요지 :\" 처럼 콜론까지 붙인다.\n"
    "- \"2. 적용 법령/근거\"에서만 조문 링크를 넣는다. \"3. 핵심 판단\"에는 링크를 넣지 않는다.\n"
    "- \"참고 링크\" 같은 추가 섹션을 만들지 않는다.\n"
    "- 필요 시 \"해설\" 소제목은 선택적으로 사용할 수 있으며, 그 안의 \"법령명 제n조\"는 인라인 링크 허용.\n"
    "- 답변 전반은 변호사가 작성한 자문 의견서처럼, 차분하고 설득력 있게 작성하라."
)
,

    Intent.DRAFT: (
        "사용자가 요청한 문서/조항 초안을 제시하고, 변수(날짜/당사자/금액 등)는 대괄호로 표시하라.\n"
        "반드시 조문을 인용하고 누르면 링크가 활성화 되어야 한다."
    ),
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

# === PATCH: Non-search => MEMO routing ===
import re as _re_simple
from typing import Tuple as _TupleSimple

# URL 인식: http(s):// 또는 도메인형 입력도 검색 모드로
_URL_PAT = _re_simple.compile(r'(https?://\S+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?)', _re_simple.I)

def classify_intent(q: str) -> _TupleSimple[Intent, float]:
    t = (q or "").strip()
    # 1) URL이면 무조건 검색 모드로
    if _URL_PAT.search(t):
        return (Intent.LAWFINDER, 0.96)
    SEARCH_HINTS = ["링크", "원문", "검색", "찾아", "상세보기", "열람", "조문", "법령", "법 이름"]
    has_article_num = bool(_re_simple.search(r"제\s*\d+\s*조(의\s*\d+)?", t))
    if any(k in t for k in SEARCH_HINTS) or has_article_num:
        return (Intent.LAWFINDER, 0.90)
    return (Intent.MEMO, 0.65)

def route_intent(q: str, client=None, model=None) -> _TupleSimple[Intent, float, bool]:
    det, conf = classify_intent(q)
    needs_lookup = det in (Intent.LAWFINDER, Intent.MEMO)
    return det, conf, needs_lookup
# === END PATCH ===
