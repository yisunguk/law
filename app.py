# app.py — Single-window chat with bottom streaming + robust dedupe + pinned question
from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="법제처 법무 상담사",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)
# PATCH safety: default flags (will be updated later)
ANSWERING = bool(st.session_state.get("__answering__", False))
chat_started = bool(globals().get("chat_started", False))
# === [BOOTSTRAP] session keys (must be first) ===
if "messages" not in st.session_state:
    st.session_state.messages = []
if "_last_user_nonce" not in st.session_state:
    st.session_state["_last_user_nonce"] = None


KEY_PREFIX = "main"

from modules import AdviceEngine, Intent, classify_intent, pick_mode, build_sys_for_mode

# 지연 초기화: 필요한 전역들이 준비된 뒤에 한 번만 엔진 생성
def _init_engine_lazy():
    import streamlit as st
    if "engine" in st.session_state and st.session_state.engine is not None:
        return st.session_state.engine

    g = globals()
    c      = g.get("client")
    az     = g.get("AZURE")
    tools  = g.get("TOOLS")
    scc    = g.get("safe_chat_completion")
    t_one  = g.get("tool_search_one")
    t_multi= g.get("tool_search_multi")
    pre    = g.get("prefetch_law_context")
    summar = g.get("_summarize_laws_for_primer")

    # 필수 구성요소가 아직 준비 안 되었으면 None을 캐시하고 리턴
    if not (c and az and tools and scc and t_one and t_multi):
        st.session_state.engine = None
        return None

    st.session_state.engine = AdviceEngine(
        client=c,
        model=az["deployment"],
        tools=tools,
        safe_chat_completion=scc,
        tool_search_one=t_one,
        tool_search_multi=t_multi,
        prefetch_law_context=pre,             # 있으면 그대로
        summarize_laws_for_primer=summar,     # 있으면 그대로
        temperature=0.2,
    )
    return st.session_state.engine

# 기존 ask_llm_with_tools를 얇은 래퍼로 교체
from modules import AdviceEngine, Intent, classify_intent, pick_mode, build_sys_for_mode

def ask_llm_with_tools(
    user_q: str,
    num_rows: int = 5,
    stream: bool = True,
    forced_mode: str | None = None,  # 유지해도 됨: 아래에서 직접 처리
    brief: bool = False,
):
    """
    UI 진입점: 의도→모드 결정, 시스템 프롬프트 합성, 툴 사용 여부 결정 후
    AdviceEngine.generate()에 맞는 인자(system_prompt, allow_tools)로 호출.
    """
    engine = _init_engine_lazy() if "_init_engine_lazy" in globals() else globals().get("engine")
    if engine is None:
        yield ("final", "엔진이 아직 초기화되지 않았습니다. (client/AZURE/TOOLS 확인)", [])
        return

    # 1) 모드 결정
    det_intent, conf = classify_intent(user_q)
    try:
        valid = {m.value for m in Intent}
        mode = Intent(forced_mode) if forced_mode in valid else pick_mode(det_intent, conf)
    except Exception:
        mode = pick_mode(det_intent, conf)

    # 2) 프롬프트/툴 사용 여부
    use_tools = mode in (Intent.LAWFINDER, Intent.MEMO)
    sys_prompt = build_sys_for_mode(mode, brief=brief)

    # 3) 엔진 호출 (새 시그니처에 맞게)
    yield from engine.generate(
        user_q,
        system_prompt=sys_prompt,
        allow_tools=use_tools,
        num_rows=num_rows,
        stream=stream,
        primer_enable=True,
    )

import io, os, re, json, time, html

if "_normalize_text" not in globals():
    def _normalize_text(s: str) -> str:
        """불필요한 공백/빈 줄을 정돈하는 안전한 기본 버전"""
        s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
        # 앞뒤 공백 정리
        s = s.strip()
        # 3개 이상 연속 개행 → 2개로
        s = re.sub(r"\n{3,}", "\n\n", s)
        # 문장 끝 공백 제거
        s = re.sub(r"[ \t]+\n", "\n", s)
        return s

def _esc(s: str) -> str:
    """HTML escape only"""
    return html.escape("" if s is None else str(s))

def _esc_br(s: str) -> str:
    """HTML escape + 줄바꿈을 <br>로"""
    return _esc(s).replace("\n", "<br>")

from datetime import datetime            # _push_user_from_pending, 저장 시각 등에 필요
import urllib.parse as up                # normalize_law_link, quote 등에서 사용
import xml.etree.ElementTree as ET       # _call_moleg_list() XML 파싱에 필요
from urllib.parse import quote
import requests
import streamlit.components.v1 as components
from openai import AzureOpenAI
from llm_safety import safe_chat_completion

# TLS 1.2 강제용 어댑터 정의
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
class TLS12HttpAdapter(HTTPAdapter):
    """TLS1.2 only adapter for requests"""
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.set_ciphers('HIGH:!aNULL:!eNULL:!SSLv2:!SSLv3')
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

from chatbar import chatbar
# (첨부 파싱은 나중 확장용으로 import 유지)
from utils_extract import extract_text_from_pdf, extract_text_from_docx, read_txt, sanitize
from external_content import is_url, make_url_context
from external_content import extract_first_url
from typing import Iterable, List

import hashlib

def _hash_text(s: str) -> str:
    return hashlib.md5((s or "").encode("utf-8")).hexdigest()


# 행정규칙 소관 부처 드롭다운 옵션
MINISTRIES = [
    "부처 선택(선택)",
    "국무조정실", "기획재정부", "교육부", "과학기술정보통신부",
    "외교부", "통일부", "법무부", "행정안전부", "문화체육관광부",
    "농림축산식품부", "산업통상자원부", "보건복지부", "환경부",
    "고용노동부", "여성가족부", "국토교통부", "해양수산부",
    "중소벤처기업부", "금융위원회", "방송통신위원회", "공정거래위원회",
    "국가보훈부", "인사혁신처", "원자력안전위원회", "질병관리청",
]
# === UI/동작 옵션 ===
SHOW_SEARCH_DEBUG = False     # ← 통합 검색 패널의 디버그(시도/LLM plans/에러) 감추기

SHOW_STREAM_PREVIEW = False  # 스트리밍 중간 미리보기 끄기

# ==============================
# 추천 키워드 (탭별) + 헬퍼
# ==============================

# 법령명 기반 추천(법령 탭 전용)
SUGGESTED_LAW_KEYWORDS = {
    "민법": ["제839조", "재산분할", "이혼", "제840조", "친권"],
    "형법": ["제307조", "명예훼손", "사기", "폭행", "상해"],
    "주택임대차보호법": ["보증금", "임차권등기명령", "대항력", "우선변제권"],
    "상가건물 임대차보호법": ["보증금", "권리금", "갱신요구권", "대항력"],
    "근로기준법": ["해고", "연차", "퇴직금", "임금체불"],
    "개인정보 보호법": ["수집이용", "제3자제공", "유출통지", "과징금"],
}
FALLBACK_LAW_KEYWORDS = ["정의", "목적", "벌칙"]

def suggest_keywords_for_law(law_name: str) -> list[str]:
    if not law_name:
        return FALLBACK_LAW_KEYWORDS
    if law_name in SUGGESTED_LAW_KEYWORDS:
        return SUGGESTED_LAW_KEYWORDS[law_name]
    for k in SUGGESTED_LAW_KEYWORDS:
        if k in law_name:
            return SUGGESTED_LAW_KEYWORDS[k]
    return FALLBACK_LAW_KEYWORDS

# 탭별 기본 추천(행정규칙/자치법규/조약/판례/헌재/해석례)
SUGGESTED_TAB_KEYWORDS = {
    "admrul": ["고시", "훈령", "예규", "지침", "개정"],
    "ordin":  ["조례", "규칙", "규정", "시행", "개정"],
    "trty":   ["비준", "발효", "양자", "다자", "협정"],
    # 판례/헌재는 키워드 검색용 보조(정확 링크는 사건번호·사건표시가 더 적합)
    "prec":   ["손해배상", "대여금", "사기", "이혼", "근로"],
    "cc":     ["위헌", "합헌", "각하", "침해", "기각"],
    "expc":   ["유권해석", "질의회신", "법령해석", "적용범위"],
}
def suggest_keywords_for_tab(tab_kind: str) -> list[str]:
    return SUGGESTED_TAB_KEYWORDS.get(tab_kind, [])

def inject_sticky_layout_css(mode: str = "wide"):
    PRESETS = {
        "wide":   {"center": "1160px", "bubble_max": "760px"},
        "narrow": {"center": "880px",  "bubble_max": "640px"},
    }
    p = PRESETS.get(mode, PRESETS["wide"])

    # 전역 CSS 변수(한 군데에서만 선언)
    root_vars = (
        ":root {"
        " --center-col: 1160px;"
        " --bubble-max: 760px;"
        " --chatbar-h: 56px;"
        " --chat-gap: 12px;"
        " --rail: 460px;"
        " --hgap: 24px;"
        "}"
    )

    css = f"""

    <style>

      {root_vars}

    </style>

    """

    st.markdown(css, unsafe_allow_html=True)
# ✅ PRE-CHAT: 완전 중앙(뷰포트 기준) + 여백 제거
if not chat_started:
    pass



# --- PATCH: body class toggles for chat-started / answering ---
try:
    pass
#      st.markdown(f"""
#      <script>
#      document.body.classList.toggle('chat-started', {str(chat_started).lower()});
#      document.body.classList.toggle('answering', {str(ANSWERING).lower()});
#      </script>
#      """, unsafe_allow_html=True)
except Exception:
    pass