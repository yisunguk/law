# app.py — Single-window chat with bottom streaming + robust dedupe + pinned question
from __future__ import annotations

import streamlit as st


# === Shared hero (title + two paragraphs) used in pre-chat and inside chat ===
HERO_HTML = '''
<h1 style="font-size:38px;font-weight:800;letter-spacing:-.5px;margin-bottom:12px;">⚖️ 법률상담 챗봇</h1>
<p style="font-size:15px;line-height:1.8;opacity:.92;margin:0 0 6px;">
  법제처 국가법령정보 DB를 기반으로 최신 법령과 행정규칙, 자치법규, 조약, 법령해석례, 헌재결정례, 법령용어를 신뢰성 있게 제공합니다.
</p>
<p style="font-size:15px;line-height:1.8;opacity:.92;margin:0 0 24px;">
  본 챗봇은 신속하고 정확한 법령 정보를 안내하여, 사용자가 법률적 쟁점을 이해하고 합리적인 판단을 내릴 수 있도록 돕습니다.
</p>
'''

# --- per-turn nonce ledger (prevents double appends)
st.session_state.setdefault('_nonce_done', {})
# --- cache helpers: suggestions shouldn't jitter on reruns ---
def cached_suggest_for_tab(tab_key: str):
    import streamlit as st
    store = st.session_state.setdefault("__tab_suggest__", {})
    if tab_key not in store:
        from modules import suggest_keywords_for_tab
        store[tab_key] = cached_suggest_for_tab(tab_key)
    return store[tab_key]

def cached_suggest_for_law(law_name: str):
    import streamlit as st
    store = st.session_state.setdefault("__law_suggest__", {})
    if law_name not in store:
        from modules import suggest_keywords_for_law
        store[law_name] = cached_suggest_for_law(law_name)
    return store[law_name]

st.set_page_config(
    page_title="법제처 법무 상담사",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 최상단 스크롤 기준점
st.markdown('<div id="__top_anchor__"></div>', unsafe_allow_html=True)

st.markdown("""
<style>
:root{
  --center-col: 980px;   /* 중앙 전체 폭 */
  --bubble-max: 760px;   /* 말풍선 최대 폭 */
  --pad-x: 12px;         /* 좌우 여백 */
}

/* 본문(채팅 전/후 공통) 중앙 폭 고정 */
.block-container{
  max-width: var(--center-col) !important;
  margin-left: auto !important;
  margin-right: auto !important;
  padding-left: var(--pad-x) !important;
  padding-right: var(--pad-x) !important;
}

/* 업로더/폼/카드류도 같은 폭 */
.block-container [data-testid="stFileUploader"],
.block-container form,
.block-container .stForm,
.block-container .stMarkdown>div{
  max-width: var(--center-col) !important;
  margin-left: auto !important;
  margin-right: auto !important;
}

/* 채팅 메시지 폭(답변 후) */
[data-testid="stChatMessage"]{
  max-width: var(--bubble-max) !important;
  width: 100% !important;
  margin-left: auto !important;
  margin-right: auto !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown('''
<style>
.hero-in-chat { margin: 8px 0 2px; }
.hero-in-chat h1 { margin-bottom: 10px !important; }
</style>
''' , unsafe_allow_html=True)

st.markdown("""
<style>
:root{
  --left-rail: 300px;
  --right-rail: calc(var(--flyout-width, 0px) + var(--flyout-gap, 0px));
}
</style>
<script>
(function(){
  function setLeftRail(){
    const sb = window.parent.document.querySelector('[data-testid="stSidebar"]');
    if(!sb) return;
    const w = Math.round(sb.getBoundingClientRect().width || 300);
    document.documentElement.style.setProperty('--left-rail', w + 'px');
  }
  setLeftRail();
  window.addEventListener('resize', setLeftRail);
  new MutationObserver(setLeftRail).observe(window.parent.document.body, {subtree:true, childList:true, attributes:true});
})();
</script>
""", unsafe_allow_html=True)


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


# --- Utilities: de-duplicate repeated paragraphs/halves ---
def _dedupe_repeats(txt: str) -> str:
    if not txt:
        return txt
    n = len(txt)
    # Heuristic 1: if halves overlap (common duplication pattern)
    if n > 600:
        half = n // 2
        a, b = txt[:half].strip(), txt[half:].strip()
        if a and b and (a == b or a.startswith(b[:200]) or b.startswith(a[:200])):
            return a if len(a) >= len(b) else b
    # Heuristic 2: paragraph-level dedupe while preserving order
    parts = re.split(r"\n\s*\n", txt)
    seen = set()
    out_parts = []
    for p in parts:
        key = p.strip()
        norm = re.sub(r"\s+", " ", key).strip().lower()
        if norm and norm in seen:
            continue
        if norm:
            seen.add(norm)
        out_parts.append(p)
    return "\n\n".join(out_parts)


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

def cached_suggest_for_law(law_name: str) -> list[str]:
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
def cached_suggest_for_tab(tab_kind: str) -> list[str]:
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

      /* 본문/입력창 공통 중앙 정렬 & 동일 폭 */
      .block-container, .stChatInput {{
        max-width: var(--center-col) !important;
        margin-left: auto !important;
        margin-right: auto !important;
      }}

      /* 채팅 말풍선 최대 폭 */
      [data-testid="stChatMessage"] {{
        max-width: var(--bubble-max) !important;
        width: 100% !important;
      }}
      [data-testid="stChatMessage"] .stMarkdown,
      [data-testid="stChatMessage"] .stMarkdown > div {{
        width: 100% !important;
      }}

      /* 대화 전 중앙 히어로 */
      .center-hero {{
        min-height: calc(100vh - 220px);
        display: flex; flex-direction: column; align-items: center; justify-content: center;
      }}
      .center-hero .stFileUploader, .center-hero .stTextInput {{
        width: 720px; max-width: 92vw;
      }}

.post-chat-ui .stFileUploader, .post-chat-ui .stTextInput {{ width: 720px; max-width: 92vw; }}
.post-chat-ui {{ margin-top: 8px; }}


      /* 업로더 고정: 앵커 다음 형제 업로더 */
      #bu-anchor + div[data-testid='stFileUploader'] {{
        position: fixed;
        left: 50%; transform: translateX(-50%);
        bottom: calc(var(--chatbar-h) + var(--chat-gap) + 12px);
        width: clamp(340px, calc(var(--center-col) - 2*var(--hgap)), calc(100vw - var(--rail) - 2*var(--hgap)));
        max-width: calc(100vw - var(--rail) - 2*var(--hgap));
        z-index: 60;
        background: rgba(0,0,0,0.35);
        padding: 10px 12px; border-radius: 12px;
        backdrop-filter: blur(6px);
      }}
      #bu-anchor + div [data-testid='stFileUploader'] {{
        background: transparent !important; border: none !important;
      }}

      /* 입력창 하단 고정 */
      section[data-testid="stChatInput"] {{
        position: fixed; left: 50%; transform: translateX(-50%);
        bottom: 0; z-index: 70;
        width: clamp(340px, calc(var(--center-col) - 2*var(--hgap)), calc(100vw - var(--rail) - 2*var(--hgap)));
        max-width: calc(100vw - var(--rail) - 2*var(--hgap));
      }}

      /* 본문이 하단 고정 UI와 겹치지 않게 */
      .block-container {{
        padding-bottom: calc(var(--chatbar-h) + var(--chat-gap) + 130px) !important;
      }}

      
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# 호출 위치: 파일 맨 아래, 모든 컴포넌트를 그린 뒤
inject_sticky_layout_css("wide")

# ----- FINAL OVERRIDE: 우측 통합검색 패널 간격/위치 확정 -----

# --- Right flyout: 상단 고정 + 하단(채팅창)과 겹치지 않게 ---
# --- Right flyout: 하단 답변창(입력창) 위에 맞춰 고정 ---
import streamlit as st
st.markdown("""
<style>
  :root{
    /* 숫자만 바꾸면 미세조정 됩니다 */
    --flyout-width: 360px;     /* 우측 패널 폭 */
    --flyout-gap:   80px;      /* 본문과 패널 사이 가로 간격 */
    --chatbar-h:    56px;      /* 하단 입력창 높이 */
    --chat-gap:     12px;      /* 입력창 위 여백 */
    /* 패널 하단이 멈출 위치(= 입력창 바로 위) */
    --flyout-bottom: calc(var(--chatbar-h) + var(--chat-gap) + 16px);
  }

  @media (min-width:1280px){
    /* 본문이 패널과 겹치지 않도록 우측 여백 확보 */
    .block-container{
      padding-right: calc(var(--flyout-width) + var(--flyout-gap)) !important;
    }

    /* 패널: 화면 하단 기준으로 ‘입력창 위’에 딱 붙이기 */
    #search-flyout{
      position: fixed !important;
      bottom: var(--flyout-bottom) !important;  /* ⬅ 핵심: 답변창 위에 정렬 */
      top: auto !important;                     /* 기존 top 규칙 무력화 */
      right: 24px !important; left: auto !important;

      width: var(--flyout-width) !important;
      max-width: 38vw !important;

      /* 패널 내부만 스크롤되게 최대 높이 제한 */
      max-height: calc(100vh - var(--flyout-bottom) - 24px) !important;
      overflow: auto !important;

      z-index: 58 !important; /* 입력창(보통 z=70)보다 낮게 */
    }
  }

  /* 모바일/좁은 화면은 자연 흐름 */
  @media (max-width:1279px){
    #search-flyout{ position: static !important; max-height:none !important; overflow:visible !important; }
    .block-container{ padding-right: 0 !important; }
  }
</style>
""", unsafe_allow_html=True)



# --- 간단 토큰화/정규화(이미 쓰고 있던 것과 호환) ---
# === Tokenize & Canonicalize (유틸 최상단에 배치) ===
import re
from typing import Iterable, List

TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")

def _tok(s: str) -> List[str]:
    """한글/영문/숫자 2자 이상 토큰만 추출"""
    return TOKEN_RE.findall(s or "")

_CANON = {
    # 자주 나오는 축약/동의어만 최소화 (필요 시 확장)
    "손배": "손해배상",
    "차량": "자동차",
    "교특법": "교통사고처리",
}

def _canonize(tokens: Iterable[str]) -> List[str]:
    """토큰을 표준형으로 치환"""
    return [_CANON.get(t, t) for t in tokens]


# --- 레벤슈타인: 1글자 이내 오탈자 교정용(가벼운 구현) ---
def _lev1(a: str, b: str) -> int:
    # 거리 0/1/2만 빠르게 판별
    if a == b: return 0
    if abs(len(a) - len(b)) > 1: return 2
    # 같은 길이: 치환 1회 이내 검사
    if len(a) == len(b):
        diff = sum(1 for x, y in zip(a, b) if x != y)
        return 1 if diff == 1 else 2
    # 하나 길이 차: 삽입/삭제 1회 이내 검사
    if len(a) > len(b): a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1; j += 1
        else:
            edits += 1; j += 1
            if edits > 1: return 2
    return 1 if edits <= 1 else 2

def _closest_token_1edit(t: str, U: set[str]) -> str | None:
    best = None; best_d = 2
    for u in U:
        d = _lev1(t, u)
        if d < best_d:
            best, best_d = u, d
            if best_d == 0: break
    return best if best_d <= 1 else None

def _sanitize_plan_q(user_q: str, q: str) -> str:
    """
    플랜 q 안의 토큰 중 사용자 질문에 없는 토큰을
    '한 글자 이내'로 가까운 사용자 토큰으로 교체(예: 주차자 → 주차장).
    """
    U = set(_canonize(_tok(user_q)))
    T = _canonize(_tok(q))
    repl = {}
    for t in T:
        if t not in U and len(t) >= 2:
            cand = _closest_token_1edit(t, U)
            if cand:
                repl[t] = cand
    # 한국어는 \b 경계가 약하므로 단순 치환(부분치환 위험 낮음)
    for a, b in repl.items():
        q = q.replace(a, b)
    return q

# ---- 오른쪽 플로팅 패널 렌더러 ----
def render_search_flyout(user_q: str, num_rows: int = 8, hint_laws: list[str] | None = None, show_debug: bool = False):
    results = find_all_law_data(user_q, num_rows=num_rows, hint_laws=hint_laws)

    def _pick(*cands):
        for c in cands:
            if isinstance(c, str) and c.strip():
                return c.strip()
        return ""

    def _build_law_link(it, eff):
        link = _pick(it.get("url"), it.get("link"), it.get("detail_url"), it.get("상세링크"))
        if link: return link
        mst = _pick(it.get("MST"), it.get("mst"), it.get("LawMST"))
        if mst:
            return f"https://www.law.go.kr/DRF/lawService.do?OC=sapphire_5&target=law&MST={mst}&type=HTML&efYd={eff}"
        return ""

    def _law_item_li(it):
        title = _pick(it.get("법령명한글"), it.get("법령명"), it.get("title_kr"), it.get("title"), it.get("name_ko"), it.get("name"))
        dept  = _pick(it.get("소관부처"), it.get("부처명"), it.get("dept"), it.get("department"))
        eff   = _pick(it.get("시행일자"), it.get("eff"), it.get("effective_date"))
        pub   = _pick(it.get("공포일자"), it.get("pub"), it.get("promulgation_date"))
        link  = _build_law_link(it, eff)

        parts = [f'<span class="title">{title or "(제목 없음)"} </span>']
        meta  = []
        if dept: meta.append(f"소관부처: {dept}")
        if eff or pub: meta.append(f"시행일자: {eff} / 공포일자: {pub}")
        if meta: parts.append(f'<div class="meta">{" / ".join(meta)}</div>')
        if link: parts.append(f'<a href="{link}" target="_blank" rel="noreferrer">법령 상세보기</a>')
        return "<li>" + "\n".join(parts) + "</li>"

    # 헤더
    html = ['<div id="search-flyout">', '<h3>📚 통합 검색 결과</h3>', '<details open><summary>열기/접기</summary>']

    # 버킷 렌더
    for label in ["법령", "행정규칙", "자치법규", "조약"]:
        pack  = results.get(label) or {}
        items = pack.get("items") or []
        html.append(f'<h4>🔎 {label}</h4>')
        if not items:
            html.append('<p>검색 결과 없음</p>')
        else:
            html.append('<ol class="law-list">')
            html += [_law_item_li(it) for it in items]
            html.append('</ol>')

        if show_debug:
            tried = (pack.get("debug") or {}).get("tried") or []
            plans = (pack.get("debug") or {}).get("plans") or []
            err   = pack.get("error")
            dbg = []
            if tried: dbg.append("시도: " + " | ".join(tried))
            if plans: dbg.append("LLM plans: " + " | ".join([f"{p.get('target')}:{p.get('q')}" for p in plans]))
            if err:   dbg.append("오류: " + err)
            if dbg:   html.append("<small class='debug'>" + "<br/>".join(dbg) + "</small>")

    html.append("</details></div>")
    st.markdown("\n".join(html), unsafe_allow_html=True)

  # ⬇️ 이 블록만 붙여넣으세요 (기존 header st.markdown(...) 블록은 삭제)
# app.py (하단)

# =========================================
# 세션에 임시로 담아 둔 첫 질문을 messages로 옮기는 유틸
# (이 블록을 파일 상단 ‘레이아웃/스타일 주입’ 직후 정도로 올려둡니다)
# =========================================
from datetime import datetime

has_chat = bool(st.session_state.get("messages")) or bool(st.session_state.get("_pending_user_q"))


# ✅ 중요: ‘최초 화면’ 렌더링 전에 먼저 호출

from datetime import datetime
import time
import streamlit as st

def _push_user_from_pending() -> str | None:
    """폼에서 넣어둔 _pending_user_q를 메시지로 옮김 (중복 방지 포함)"""
    q = st.session_state.pop("_pending_user_q", None)
    nonce = st.session_state.pop("_pending_user_nonce", None)
    if not q:
        return None
    if nonce and st.session_state.get("_last_user_nonce") == nonce:
        return None

    # === 첨부파일 처리: 업로드된 파일 텍스트를 질문 뒤에 부착 ===
    try:
        att_payload = st.session_state.pop("_pending_user_files", None)
    except Exception:
        att_payload = None

    # 우선순위: 명시 payload > 포스트-챗 업로더 > 프리챗 업로더 > 하단 업로더
    files_to_read = []
    try:
        if att_payload:
            for it in att_payload:
                name = it.get("name") or "uploaded"
                data = it.get("data", b"")
                mime = it.get("type") or ""
                files_to_read.append(("__bytes__", name, data, mime))
    except Exception:
        pass
    # 스트림릿 업로더에서 직접 읽기 (fallback)
    for key in ("post_files", "first_files", "bottom_files"):
        try:
            for f in (st.session_state.get(key) or []):
                files_to_read.append(("__widget__", getattr(f, "name", "uploaded"), f, getattr(f, "type", "")))
        except Exception:
            pass

    def _try_extract(name, src, mime):
        txt = ""
        try:
            # utils_extract 사용 우선
            if name.lower().endswith(".pdf"):
                try:
                    txt = extract_text_from_pdf(src)
                except Exception:
                    import io
                    try:
                        data = src if isinstance(src, (bytes, bytearray)) else src.read()
                        txt = extract_text_from_pdf(io.BytesIO(data))
                    except Exception:
                        txt = ""
            elif name.lower().endswith(".docx"):
                try:
                    txt = extract_text_from_docx(src)
                except Exception:
                    import io
                    try:
                        data = src if isinstance(src, (bytes, bytearray)) else src.read()
                        txt = extract_text_from_docx(io.BytesIO(data))
                    except Exception:
                        txt = ""
            elif name.lower().endswith(".txt"):
                try:
                    if hasattr(src, "read"):
                        data = src.read()
                        try: src.seek(0)
                        except Exception: pass
                    else:
                        data = src if isinstance(src, (bytes, bytearray)) else b""
                    txt = read_txt(data)
                except Exception:
                    try:
                        txt = data.decode("utf-8", errors="ignore")
                    except Exception:
                        txt = ""
        except Exception:
            txt = ""
        return sanitize(txt) if "sanitize" in globals() else txt

    ATTACH_LIMIT_PER_FILE = 6000   # chars
    ATTACH_TOTAL_LIMIT    = 16000  # chars

    pieces = []
    total = 0
    for kind, name, src, mime in files_to_read[:6]:
        try:
            t = _try_extract(name, src if kind=="__widget__" else src, mime) or ""
        except Exception:
            t = ""
        if not t:
            continue
        t = t.strip()
        if not t:
            continue
        t = t[:ATTACH_LIMIT_PER_FILE]
        if total + len(t) > ATTACH_TOTAL_LIMIT:
            t = t[: max(0, ATTACH_TOTAL_LIMIT - total) ]
        if not t:
            break
        pieces.append(f"### {name}\\n{t}")
        total += len(t)
        if total >= ATTACH_TOTAL_LIMIT:
            break

    attach_block = "\\n\\n".join(pieces) if pieces else ""

    # === 최종 콘텐츠 합성 ===
    content_final = q.strip()
    if attach_block:
        content_final += "\\n\\n[첨부 문서 발췌]\\n" + attach_block + "\\n"
    else:
        content_final = q.strip()
    st.session_state.messages.append({
        "role": "user",
        "content": q.strip(),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    st.session_state["_last_user_nonce"] = nonce
    st.session_state["current_turn_nonce"] = nonce  # ✅ 이 턴의 nonce 확정
    # reset duplicate-answer guard for a NEW user turn
    st.session_state.pop('_last_ans_hash', None)

    return q

def render_pre_chat_center():
    """대화 전: 중앙 히어로 + 중앙 업로더(키: first_files) + 전송 폼"""
    st.markdown('<section class="center-hero">', unsafe_allow_html=True)
    st.markdown(HERO_HTML, unsafe_allow_html=True)

    # 중앙 업로더 (대화 전 전용)
    st.file_uploader(
        "Drag and drop files here",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="first_files",
    )

    # 입력 폼 (전송 시 pending에 저장 후 rerun)
    with st.form("first_ask", clear_on_submit=True):
        q = st.text_input("질문을 입력해 주세요...", key="first_input")
        sent = st.form_submit_button("전송", use_container_width=True)

    st.markdown("</section>", unsafe_allow_html=True)

    if sent and (q or "").strip():
        st.session_state["_pending_user_q"] = q.strip()
        st.session_state["_pending_user_nonce"] = time.time_ns()
        st.rerun()

# 기존 render_bottom_uploader() 전부 교체

# [ADD] 답변 완료 후에도 프리챗과 동일한 UI 사용
def render_post_chat_simple_ui():
    import time, io
    st.markdown('<section class="post-chat-ui">', unsafe_allow_html=True)

    # 업로더 (프리챗과 동일)
    post_files = st.file_uploader(
        "Drag and drop files here",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="post_files",
    )

    # 텍스트 입력 + 전송 버튼 (프리챗과 동일)
    with st.form("next_ask", clear_on_submit=True):
        q = st.text_input("질문을 입력해 주세요...", key="next_input")
        sent = st.form_submit_button("전송", use_container_width=True)

    st.markdown("</section>", unsafe_allow_html=True)

    if sent and (q or "").strip():
        # 업로드된 파일을 안전하게 세션에 보관 (바로 rerun할 것이므로 바이트로 저장)
        safe_payload = []
        try:
            for f in (post_files or []):
                try:
                    data = f.read()
                    f.seek(0)
                except Exception:
                    data = None
                safe_payload.append({
                    "name": getattr(f, "name", "uploaded"),
                    "type": getattr(f, "type", ""),
                    "data": data,
                })
        except Exception:
            pass
        st.session_state["_pending_user_q"] = (q or "").strip()
        st.session_state["_pending_user_nonce"] = time.time_ns()
        st.session_state["_pending_user_files"] = safe_payload
        st.rerun()
def render_bottom_uploader():
    # 업로더 바로 앞에 '앵커'만 출력
    st.markdown('<div id="bu-anchor"></div>', unsafe_allow_html=True)

    # 이 다음에 나오는 업로더를 CSS에서 #bu-anchor + div[...] 로 고정 배치
    st.file_uploader(
        "Drag and drop files here",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="bottom_files",
        help="대화 중에는 업로드 박스가 하단에 고정됩니다.",
    )

# --- 작동 키워드 목록(필요시 보강/수정) ---
LINKGEN_KEYWORDS = {
    "법령": ["제정", "전부개정", "개정", "폐지", "부칙", "정정", "시행", "별표", "별지서식"],
    "행정규칙": ["훈령", "예규", "고시", "지침", "공고", "전부개정", "개정", "정정", "폐지"],
    "자치법규": ["조례", "규칙", "훈령", "예규", "전부개정", "개정", "정정", "폐지"],
    "조약": ["서명", "비준", "발효", "공포", "폐기"],
    "판례": ["대법원", "전원합의체", "하급심", "손해배상", "불법행위"],
    "헌재": ["위헌", "합헌", "한정위헌", "한정합헌", "헌법불합치"],
    "해석례": ["유권해석", "법령해석", "질의회신"],
    "용어/별표": ["용어", "정의", "별표", "서식"],
}

# --- 키워드 위젯 헬퍼: st_tags가 있으면 사용, 없으면 multiselect로 대체 ---
try:
    from streamlit_tags import st_tags
    def kw_input(label, options, key):
        return st_tags(
            label=label,
            text="쉼표(,) 또는 Enter로 추가/삭제",
            value=options,           # ✅ 기본값: 전부 채움
            suggestions=options,
            maxtags=len(options),
            key=key,
        )
except Exception:
    def kw_input(label, options, key):
        return st.multiselect(
            label, options=options, default=options,  # ✅ 기본값: 전부 선택
            key=key, help="필요 없는 키워드는 선택 해제하세요."
        )



# =============================
# Utilities
# =============================
_CASE_NO_RE = re.compile(r'(19|20)\d{2}[가-힣]{1,3}\d{1,6}')
_HBASE = "https://www.law.go.kr"
LAW_PORTAL_BASE = "https://www.law.go.kr/"

def _chat_started() -> bool:
    msgs = st.session_state.get("messages", [])
    # 실제 사용자 메시지가 하나라도 있어야 '대화 시작'으로 간주
    return any(
        (m.get("role") == "user") and (m.get("content") or "").strip()
        for m in msgs
    ) or bool(st.session_state.get("_pending_user_q"))

# --- 최종 후처리 유틸: 답변 본문을 정리하고 조문에 인라인 링크를 붙인다 ---
def apply_final_postprocess(full_text: str, collected_laws: list) -> str:
    # 1) normalize (fallback 포함)
    try:
        ft = _normalize_text(full_text)
    except NameError:
        import re as _re
        def _normalize_text(s: str) -> str:
            s = (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            s = _re.sub(r"\n{3,}", "\n\n", s)
            s = _re.sub(r"[ \t]+\n", "\n", s)
            return s
        ft = _normalize_text(full_text)

    # 2) 불릿 문자 통일: •, * → -  (인라인 링크 치환 누락 방지)
    ft = (
        ft.replace("\u2022 ", "- ")  # 유니코드 불릿
          .replace("• ", "- ")
          .replace("* ", "- ")
    )

    # 3) 조문 인라인 링크 변환:  - 민법 제839조의2 → [민법 제839조의2](...)
    ft = link_inline_articles_in_bullets(ft)

    # 4) 본문 내 [법령명](URL) 교정(법제처 공식 링크로)
    ft = fix_links_with_lawdata(ft, collected_laws)

    # 5) 맨 아래 '참고 링크(조문)' 섹션 제거(중복 방지)
    ft = strip_reference_links_block(ft)

    # 6) 중복/빈 줄 정리
    ft = _dedupe_blocks(ft)

    return ft



# --- 답변(마크다운)에서 '법령명'들을 추출(복수) ---

# [민법 제839조의2](...), [가사소송법 제2조](...) 등
_LAW_IN_LINK = re.compile(r'\[([^\]\n]+?)\s+제\d+조(의\d+)?\]')
# 불릿/일반 문장 내: "OO법/령/규칙/조례" (+선택적 '제n조')
_LAW_INLINE  = re.compile(r'([가-힣A-Za-z0-9·\s]{2,40}?(?:법|령|규칙|조례))(?:\s*제\d+조(의\d+)?)?')

def extract_law_names_from_answer(md: str) -> list[str]:
    if not md:
        return []
    names = set()

    # 1) 링크 텍스트 안의 법령명
    for m in _LAW_IN_LINK.finditer(md):
        nm = (m.group(1) or "").strip()
        if nm:
            names.add(nm)

    # 2) 일반 텍스트/불릿에서 법령명 패턴
    for m in _LAW_INLINE.finditer(md):
        nm = (m.group(1) or "").strip()
        # 과적합 방지: 너무 짧은/긴 것 제외
        if 2 <= len(nm) <= 40:
            names.add(nm)

    # 정리(중복 제거 + 길이 컷 + 상위 6개)
    out, seen = [], set()
    for n in names:
        n2 = n[:40]
        if n2 and n2 not in seen:
            seen.add(n2)
            out.append(n2)
    return out[:6]


def normalize_law_link(u: str) -> str:
    """상대/스킴누락 링크를 www.law.go.kr 절대 URL로 교정"""
    if not u: return ""
    u = u.strip()
    if u.startswith("http://") or u.startswith("https://"): return u
    if u.startswith("//"): return "https:" + u
    if u.startswith("/"):  return up.urljoin(LAW_PORTAL_BASE, u.lstrip("/"))
    return up.urljoin(LAW_PORTAL_BASE, u)

def _normalize_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in s.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    merged, i = [], 0
    num_pat = re.compile(r'^\s*((\d+)|([IVXLC]+)|([ivxlc]+))\s*[\.\)]\s*$')
    while i < len(lines):
        cur = lines[i]; m = num_pat.match(cur)
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip(): j += 1
            if j < len(lines):
                number = (m.group(2) or m.group(3) or m.group(4)).upper()
                title = lines[j].lstrip()
                merged.append(f"{number}. {title}")
                i = j + 1; continue
        merged.append(cur); i += 1
    out, prev_blank = [], False
    for ln in merged:
        if ln.strip() == "":
            if not prev_blank: out.append("")
            prev_blank = True
        else:
            prev_blank = False; out.append(ln)
    return "\n".join(out)

# === [PATCH A] 조문 직링크(인라인) + 하단 '참고 링크' 섹션 제거 ===
import re
from urllib.parse import quote

# 조문 패턴: 민법 제839조의2, 민사소송법 제163조 등
_ART_PAT_BULLET = re.compile(
    r'(?m)^(?P<prefix>\s*[-*•]\s*)(?P<law>[가-힣A-Za-z0-9·()\s]{2,40})\s*제(?P<num>\d{1,4})조(?P<ui>(의\d{1,3}){0,2})(?P<tail>[^\n]*)$'
)

# 하단 '참고 링크' 제목(모델이 7. 또는 7) 등으로 출력하는 케이스 포함)
_REF_BLOCK_PAT = re.compile(
    r'(?ms)^\s*\d+\s*[\.\)]\s*참고\s*링크\s*[:：]?\s*\n(?:\s*[-*•].*\n?)+'
)
# 앞에 공백이 있어도 매칭되도록 보강
_REF_BLOCK2_PAT = re.compile(r'\n[ \t]*###\s*참고\s*링크\(조문\)[\s\S]*$', re.M)


def _deep_article_url(law: str, art_label: str) -> str:
    return f"https://www.law.go.kr/법령/{quote((law or '').strip())}/{quote(art_label)}"

def link_inline_articles_in_bullets(markdown: str) -> str:
    """불릿 라인 중 '법령명 제N조(의M)'를 [텍스트](조문URL)로 교체"""
    def repl(m: re.Match) -> str:
        law = m.group("law").strip()
        art = f"제{m.group('num')}조{m.group('ui') or ''}"
        url = _deep_article_url(law, art)
        tail = (m.group("tail") or "")
        # tail이 " (재산분할)" 같은 부가설명일 수 있으므로 보존
        linked = f"{m.group('prefix')}[{law} {art}]({url}){tail}"
        return linked
    return _ART_PAT_BULLET.sub(repl, markdown or "")

def strip_reference_links_block(markdown: str) -> str:
    """맨 아래 '참고 링크' 섹션을 제거(모델/모듈이 생성한 블록 모두 커버)"""
    if not markdown:
        return markdown
    txt = _REF_BLOCK_PAT.sub("", markdown)
    txt = _REF_BLOCK2_PAT.sub("", txt)
    return txt


# === 새로 추가: 중복 제거 유틸 ===
def _dedupe_blocks(text: str) -> str:
    s = _normalize_text(text or "")

    # 1) 완전 동일 문단의 연속 중복 제거
    lines, out, prev = s.split("\n"), [], None
    for ln in lines:
        if ln.strip() and ln == prev:
            continue
        out.append(ln); prev = ln
    s = "\n".join(out)

    # 2) "법률 자문 메모"로 시작하는 동일 본문 2중 출력 방지
    pat = re.compile(r'(법률\s*자문\s*메모[\s\S]{50,}?)(?:\n+)\1', re.I)
    s = pat.sub(r'\1', s)

    # 3) 내부 절차 문구 노출 시 제거(의도 분석/추가 검색/재검색)
    s = re.sub(
        r'^\s*\d+\.\s*\*\*?(사용자의 의도 분석|추가 검색|재검색)\*\*?.*?(?=\n\d+\.|\Z)',
        '',
        s,
        flags=re.M | re.S
    )

    # 빈 줄 정리
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s

# === add: 여러 법령 결과를 한 번에 요약해서 LLM에 먹일 프라이머 ===
def _summarize_laws_for_primer(law_items: list[dict], max_items: int = 6) -> str:
    """
    여러 법령 검색 결과를 짧게 요약해 시스템 프롬프트로 주입.
    - 너무 많으면 상위 일부만 (max_items)
    - 형식: "관련 법령 후보: 1) 법령명(구분, 소관부처, 시행/공포)"
    """
    if not law_items:
        return ""
    rows = []
    for i, d in enumerate(law_items[:max_items], 1):
        nm = d.get("법령명","").strip()
        kind = d.get("법령구분","").strip()
        dept = d.get("소관부처명","").strip()
        eff = d.get("시행일자","").strip()
        pub = d.get("공포일자","").strip()
        rows.append(f"{i}) {nm} ({kind}; {dept}; 시행 {eff}, 공포 {pub})")
    body = "\n".join(rows)
    return (
        "아래는 사용자 사건과 관련도가 높은 법령 후보 목록이다. "
        "답변을 작성할 때 각각의 적용 범위와 책임주체, 구성요건·의무·제재를 교차 검토하라.\n"
        f"{body}\n"
        "가능하면 각 법령을 분리된 소제목으로 정리하고, 핵심 조문(1~2개)만 간단 인용하라."
    )

# === add: LLM-우선 후보 → 각 후보로 MOLEG API 다건 조회/누적 ===
def prefetch_law_context(user_q: str, num_rows_per_law: int = 3) -> list[dict]:
    """
    1) LLM이 법령 후보를 뽑는다 (extract_law_candidates_llm)  # :contentReference[oaicite:4]{index=4}
    2) 후보들 각각에 대해 _call_moleg_list("law", ...) 호출    # :contentReference[oaicite:5]{index=5}
    3) 결과를 전부 합쳐서 반환 (중복은 간단 제거)
    """
    seen = set()
    merged: list[dict] = []

    # 1) 후보
    law_names = extract_law_candidates_llm(user_q) or []

    # 후보가 0개면 _clean_query_for_api()로 마지막 폴백
    if not law_names:
        law_names = [_clean_query_for_api(user_q)]  # :contentReference[oaicite:6]{index=6}

    # 2) 각 후보로 다건 조회
    for name in law_names:
        if not name:
            continue
        items, _, _ = _call_moleg_list("law", name, num_rows=num_rows_per_law)  # :contentReference[oaicite:7]{index=7}
        for it in (items or []):
            key = (it.get("법령명",""), it.get("법령구분",""), it.get("시행일자",""))
            if key not in seen:
                seen.add(key)
                merged.append(it)

    return merged

# === add: LLM-우선 질의어 선택 헬퍼 ===
# === fix: LLM-우선 질의어 선택 (폴백은 후보가 없을 때만) ===
# ============================================
# [PATCH B] 통합 검색 결과에 '가사소송법'도 항상 후보에 포함
# - LLM이 '민법'만 골라도, 질문이 이혼/재산분할/양육 등 가사 키워드를
#   포함하면 '가사소송법'을 후보에 추가하여 우측 패널에 노출되도록 보강
# - 그대로 붙여 넣어 기존 choose_law_queries_llm_first 를 교체하세요.
# ============================================

from typing import List

# 1) 키워드 → 대표 법령 맵: 없으면 만들고, 있으면 업데이트
try:
    KEYWORD_TO_LAW  # noqa: F821  # 존재 여부만 확인
except NameError:   # 없어도 안전하게 생성
    KEYWORD_TO_LAW = {}

KEYWORD_TO_LAW.update({
    # 가사 사건 핵심 키워드 → 가사소송법
    "이혼": "가사소송법",
    "재산분할": "가사소송법",
    "양육": "가사소송법",
    "양육비": "가사소송법",
    "친권": "가사소송법",
    "면접교섭": "가사소송법",
    "가사": "가사소송법",
    "협의이혼": "가사소송법",
    "재판상 이혼": "가사소송법",
})


def choose_law_queries_llm_first(user_q: str) -> List[str]:
    """
    1) LLM이 제안한 법령 후보를 우선 채택
    2) 후보가 비어 있으면 정규화 질의 폴백 추가
    3) ★항상★ 키워드 매핑으로 보강(가사소송법 등) — 중복은 제거
    """
    ordered: List[str] = []
    text = (user_q or "")

    # 1) LLM 후보 우선
    try:
        llm_candidates = extract_law_candidates_llm(user_q) or []  # 기존 함수 사용
    except NameError:
        llm_candidates = []
    for nm in llm_candidates:
        nm = (nm or "").strip()
        if nm and nm not in ordered:
            ordered.append(nm)

    # 2) 후보가 없으면 클린 질의 폴백
    if not ordered:
        try:
            cleaned = _clean_query_for_api(user_q)  # 기존 함수 사용
        except NameError:
            cleaned = None
        if cleaned:
            ordered.append(cleaned)

    # 3) 키워드 힌트로 항상 보강 (가사 키워드 → 가사소송법 등)
    for kw, mapped in KEYWORD_TO_LAW.items():
        if kw and (kw in text) and mapped not in ordered:
            ordered.append(mapped)

    return ordered

def render_bubble_with_copy(message: str, key: str):
    """어시스턴트 말풍선 전용 복사 버튼"""
    message = _normalize_text(message or "")
    st.markdown(message)
    safe_raw_json = json.dumps(message)
    html_tpl = '''
    <div class="copy-row" style="margin-bottom:8px">
      <button id="copy-__KEY__" class="copy-btn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <path d="M9 9h9v12H9z" stroke="currentColor"/>
          <path d="M6 3h9v3" stroke="currentColor"/>
          <path d="M6 6h3v3" stroke="currentColor"/>
        </svg>
        복사
      </button>
    </div>
    <script>
    (function(){
      const btn = document.getElementById("copy-__KEY__");
      if (!btn) return;
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(__SAFE__);
          const old = btn.innerHTML; btn.innerHTML = "복사됨!";
          setTimeout(()=>btn.innerHTML = old, 1200);
        } catch(e) { alert("복사 실패: " + e); }
      });
    })();
    </script>
    '''
    html_out = html_tpl.replace("__KEY__", str(key)).replace("__SAFE__", safe_raw_json)
    components.html(html_out, height=40)

def copy_url_button(url: str, key: str, label: str = "링크 복사"):
    if not url: return
    safe = json.dumps(url)
    html_tpl = '''
      <div style="display:flex;gap:8px;align-items:center;margin-top:6px">
        <button id="copy-url-__KEY__" style="padding:6px 10px;border:1px solid #ddd;border-radius:8px;cursor:pointer">
          __LABEL__
        </button>
        <span id="copied-__KEY__" style="font-size:12px;color:var(--text-color,#888)"></span>
      </div>
      <script>
        (function(){
          const btn = document.getElementById("copy-url-__KEY__");
          const msg = document.getElementById("copied-__KEY__");
          if(!btn) return;
          btn.addEventListener("click", async () => {
            try {
              await navigator.clipboard.writeText(__SAFE__);
              msg.textContent = "복사됨!";
              setTimeout(()=>msg.textContent="", 1200);
            } catch(e) {
              msg.textContent = "복사 실패";
            }
          });
        })();
      </script>
    '''
    html_out = (html_tpl
                .replace("__KEY__", str(key))
                .replace("__SAFE__", safe)
                .replace("__LABEL__", html.escape(label)))
    components.html(html_out, height=40)

def load_secrets():
    try:
        law_key = st.secrets["LAW_API_KEY"]
    except Exception:
        law_key = None
        st.error("`LAW_API_KEY`가 없습니다. Streamlit → App settings → Secrets에 추가하세요.")
    try:
        az = st.secrets["azure_openai"]
        _ = (az["api_key"], az["endpoint"], az["deployment"], az["api_version"])
    except Exception:
        az = None
        st.warning("Azure OpenAI 설정이 없으므로 기본 안내만 제공합니다.")
    return law_key, az

def _henc(s: str) -> str: return up.quote((s or "").strip())
def hangul_by_name(domain: str, name: str) -> str: return f"{_HBASE}/{_henc(domain)}/{_henc(name)}"

# "제839조" 같은 패턴 인식용
_ARTICLE_RE = re.compile(r"^제?\d+조(의\d+)?$")

def resolve_article_from_keywords(keys):
    ARTICLE_SYNONYMS = {
        "재산분할": "제839조의2",
        "이혼": "제834조",
    }
    keys = [k.strip() for k in (keys or []) if k]
    for k in keys:
        if k in ARTICLE_SYNONYMS:
            return ARTICLE_SYNONYMS[k]
    for k in keys:
        if _ARTICLE_RE.match(k):
            return k
    return None

def hangul_law_article(name: str, subpath: str) -> str: return f"{_HBASE}/법령/{_henc(name)}/{_henc(subpath)}"

def hangul_law_with_keys(name: str, keys) -> str:
    """키워드가 조문을 가리키면 조문으로, 아니면 검색으로."""
    art = resolve_article_from_keywords(keys)
    if art:
        return hangul_law_article(name, art)
    q = " ".join([name] + [k for k in (keys or []) if k]) if keys else name
    return build_fallback_search("law", q)

def hangul_admrul_with_keys(name: str, issue_no: str, issue_date: str) -> str: return f"{_HBASE}/행정규칙/{_henc(name)}/({_henc(issue_no)},{_henc(issue_date)})"
def hangul_ordin_with_keys(name: str, no: str, date: str) -> str: return f"{_HBASE}/자치법규/{_henc(name)}/({_henc(no)},{_henc(date)})"
def hangul_trty_with_keys(no: str, eff_date: str) -> str: return f"{_HBASE}/조약/({_henc(no)},{_henc(eff_date)})"
def expc_public_by_id(expc_id: str) -> str: return f"https://www.law.go.kr/LSW/expcInfoP.do?expcSeq={up.quote(expc_id)}"
def lstrm_public_by_id(trm_seqs: str) -> str: return f"https://www.law.go.kr/LSW/lsTrmInfoR.do?trmSeqs={up.quote(trm_seqs)}"
def licbyl_file_download(fl_seq: str) -> str: return f"https://www.law.go.kr/LSW/flDownload.do?flSeq={up.quote(fl_seq)}"

def extract_case_no(text: str) -> str | None:
    if not text: return None
    m = _CASE_NO_RE.search(text.replace(" ", ""))
    return m.group(0) if m else None

def validate_case_no(case_no: str) -> bool:
    case_no = (case_no or "").replace(" ", "")
    return bool(_CASE_NO_RE.fullmatch(case_no))

def build_case_name_from_no(case_no: str, court: str = "대법원", disposition: str = "판결") -> str | None:
    case_no = (case_no or "").replace(" ", "")
    if not validate_case_no(case_no): return None
    return f"{court} {case_no} {disposition}"

def build_scourt_link(case_no: str) -> str:
    return f"https://glaw.scourt.go.kr/wsjo/panre/sjo050.do?saNo={up.quote(case_no)}"

def is_reachable(url: str) -> bool:
    try:
        r = requests.get(url, timeout=8, allow_redirects=True)
        if not (200 <= r.status_code < 400):
            return False
        text = r.text[:4000]
        bad_signals = [
            "해당 한글주소명을 찾을 수 없습니다",
            "한글 법령주소를 확인해 주시기 바랍니다",
        ]
        return not any(sig in text for sig in bad_signals)
    except Exception:
        return False

def build_fallback_search(kind: str, q: str) -> str:
    qq = up.quote((q or "").strip())
    if kind in ("law", "admrul", "ordin", "trty"):
        return f"https://www.law.go.kr/LSW/lsSc.do?query={qq}"
    if kind == "prec":
        return f"https://glaw.scourt.go.kr/wsjo/panre/sjo050.do?saNo={qq}"
    if kind == "cc":
        return f"https://www.law.go.kr/LSW/lsSc.do?query={qq}"
    return f"https://www.law.go.kr/LSW/lsSc.do?query={qq}"

def present_url_with_fallback(main_url: str, kind: str, q: str, label_main="새 탭에서 열기"):
    if main_url and is_reachable(main_url):
        st.code(main_url, language="text")
        st.link_button(label_main, main_url, use_container_width=True)
        copy_url_button(main_url, key=str(abs(hash(main_url))))
    else:
        fb = build_fallback_search(kind, q)
        st.warning("직접 링크가 열리지 않아 **대체 검색 링크**를 제공합니다.")
        st.code(fb, language="text")
        st.link_button("대체 검색 링크 열기", fb, use_container_width=True)
        copy_url_button(fb, key=str(abs(hash(fb))))

def render_pinned_question():
    last_q = (st.session_state.get("last_q") or "").strip()
    if not last_q:
        return

    st.markdown(
        f"""
        <div class="pinned-q">
          <div class="label">최근 질문</div>
          <div class="text">{_esc_br(last_q)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# 답변 내 링크를 수집된 법령 상세링크로 교정
def fix_links_with_lawdata(markdown: str, law_data: list[dict]) -> str:
    import re
    if not markdown or not law_data:
        return markdown
    name_to_url = {
        d["법령명"]: (d["법령상세링크"] or f"https://www.law.go.kr/법령/{_henc(d['법령명'])}")
        for d in law_data if d.get("법령명")
    }
    pat = re.compile(r'\[([^\]]+)\]\((https?://www\.law\.go\.kr/[^\)]+)\)')
    def repl(m):
        text, url = m.group(1), m.group(2)
        if text in name_to_url:
            return f'[{text}]({name_to_url[text]})'
        return m.group(0)
    return pat.sub(repl, markdown)

# =============================
# Secrets / Clients / Session
# =============================
LAW_API_KEY, AZURE = load_secrets()
client = None
if AZURE:
    try:
        client = AzureOpenAI(
            api_key=AZURE["api_key"],
            api_version=AZURE["api_version"],
            azure_endpoint=AZURE["endpoint"],
        )
    except Exception as e:
        st.error(f"Azure OpenAI 초기화 실패: {e}")

# =============================
# MOLEG API (Law Search) — unified
# =============================
import ssl
from urllib3.poolmanager import PoolManager

MOLEG_BASES = [
    "https://apis.data.go.kr/1170000",
    "http://apis.data.go.kr/1170000",
]

class TLS12HttpAdapter2(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        self.poolmanager = PoolManager(*args, ssl_context=ctx, **kwargs)

def _call_moleg_list(target: str, query: str, num_rows: int = 10, page_no: int = 1):
    """
    target: law | admrul | ordin | trty | expc | detc | licbyl | lstrm
    """
    if not LAW_API_KEY:
        return [], None, "LAW_API_KEY 미설정"

    api_key = (LAW_API_KEY or "").strip().strip("'").strip('"')
    if "%" in api_key and any(t in api_key.upper() for t in ("%2B", "%2F", "%3D")):
        try:
            api_key = up.unquote(api_key)
        except Exception:
            pass

    # === 추가: 빈 질의어(와일드카드) 호출 차단 ===
    q = (query or "").strip()
    if not q:
        return [], None, "빈 질의어로 호출되어 무시함"

    params = {
        "serviceKey": api_key,
        "target": target,
        "query": q,  # <-- 기존의 (query or "*") 를 q 로 교체
        "numOfRows": max(1, min(10, int(num_rows))),
        "pageNo": max(1, int(page_no)),
    }
    # ... 이하 기존 로직 그대로 ...

    last_err = None
    resp = None
    last_endpoint = None

    for base in MOLEG_BASES:
        endpoint = f"{base}/{target}/{target}SearchList.do"
        last_endpoint = endpoint
        try:
            sess = requests.Session()
            if base.startswith("https://"):
                sess.mount("https://", TLS12HttpAdapter2())
            resp = sess.get(
                endpoint, params=params, timeout=15,
                headers={"User-Agent":"Mozilla/5.0"}, allow_redirects=True
            )
            resp.raise_for_status()
            break
        except requests.exceptions.SSLError as e:
            last_err = e; continue
        except Exception as e:
            last_err = e; continue

    if resp is None:
        return [], last_endpoint, f"법제처 API 연결 실패: {last_err}"

    try:
        root = ET.fromstring(resp.text)
        result_code = (root.findtext(".//resultCode") or "").strip()
        result_msg  = (root.findtext(".//resultMsg")  or "").strip()
        if result_code and result_code != "00":
            return [], last_endpoint, f"법제처 API 오류 [{result_code}]: {result_msg or 'fail'}"

        item_tags = {
            "law": ["law"], "admrul": ["admrul"], "ordin": ["ordin"],
            "trty": ["Trty","trty"], "expc":["expc"], "detc":["Detc","detc"],
            "licbyl":["licbyl"], "lstrm":["lstrm"],
        }.get(target, ["law"])

        items = []
        for tag in item_tags: items.extend(root.findall(f".//{tag}"))

        normalized = []
        for el in items:
            normalized.append({
                "법령명": (el.findtext("법령명한글") or el.findtext("자치법규명") or el.findtext("조약명") or "").strip(),
                "법령명칭ID": (el.findtext("법령명칭ID") or "").strip(),
                "소관부처명": (el.findtext("소관부처명") or "").strip(),
                "법령구분": (el.findtext("법령구분") or el.findtext("자치법규종류") or el.findtext("조약구분명") or "").strip(),
                "시행일자": (el.findtext("시행일자") or "").strip(),
                "공포일자": (el.findtext("공포일자") or "").strip(),
                "MST": (el.findtext("MST") or el.findtext("법령ID") or el.findtext("법령일련번호") or "").strip(),
                "법령상세링크": normalize_law_link(
                    (el.findtext("법령상세링크") or el.findtext("자치법규상세링크") or el.findtext("조약상세링크") or "").strip()
                ),
            })

        return normalized, last_endpoint, None
    except Exception as e:
        return [], last_endpoint, f"응답 파싱 실패: {e}"

# 통합 미리보기 전용: 과한 문장부호/따옴표 제거 + '법령명 (제n조)'만 추출
def _clean_query_for_api(q: str) -> str:
    q = (q or "").strip()
    q = re.sub(r'[“”"\'‘’.,!?()<>\\[\\]{}:;~…]', ' ', q)
    q = re.sub(r'\\s+', ' ', q).strip()
    # 법령명(OO법/령/규칙/조례) + (제n조) 패턴
    name = re.search(r'([가-힣A-Za-z0-9·\\s]{1,40}?(법|령|규칙|조례))', q)
    article = re.search(r'제\\d+조(의\\d+)?', q)
    if name and article: return f"{name.group(0).strip()} {article.group(0)}"
    if name: return name.group(0).strip()
    return q

# === add: LLM 리랭커(맥락 필터) ===
def rerank_laws_with_llm(user_q: str, law_items: list[dict], top_k: int = 8) -> list[dict]:
    if not law_items or client is None:
        return law_items
    names = [d.get("법령명","").strip() for d in law_items if d.get("법령명")]
    names_txt = "\n".join(f"- {n}" for n in names[:25])

    SYS = (
        "너는 사건과 관련된 '법령명'만 남기는 필터야. 질문 맥락과 무관하면 제외하고, JSON만 반환해.\n"
        '형식: {"pick":["형법","산업안전보건법"]}'
    )
    prompt = (
        "사용자 질문:\n" + (user_q or "") + "\n\n"
        "후보 법령 목록:\n" + names_txt + "\n\n"
        "사건에 직접 관련된 것만 3~8개 고르고 나머지는 제외해."
    )

    try:
        resp = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=[{"role":"system","content": SYS},
                      {"role":"user","content": prompt}],
            temperature=0.0, max_tokens=96,
        )
        txt = (resp.choices[0].message.content or "").strip()
        import re, json as _json
        if "```" in txt:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt); 
            if m: txt = m.group(1).strip()
        if not txt.startswith("{"):
            m = re.search(r"\{[\s\S]*\}", txt); 
            if m: txt = m.group(0)
        data = _json.loads(txt)
        picks = [s.strip() for s in data.get("pick", []) if s.strip()]
        if not picks:
            return law_items
        name_to_item = {}
        for d in law_items:
            nm = d.get("법령명","").strip()
            if nm and nm not in name_to_item:
                name_to_item[nm] = d
        return [name_to_item[n] for n in picks if n in name_to_item][:top_k]
    except Exception:
        return law_items

def _filter_plans(user_q: str, plans: list[dict]) -> list[dict]:
    U = set(_canonize(_tok(user_q)))
    seen=set(); out=[]
    for p in plans or []:
        t = (p.get("target") or "").strip()
        q = (p.get("q") or "").strip()
        if not t or not q:
            continue
        T = set(_canonize(_tok(q)))
        if (U & T) or (p.get("must")):   # 사용자와 1토큰 이상 겹치거나, must가 있으면 통과
            key=(t,q)
            if key not in seen:
                seen.add(key)
                out.append(p)          # ← must/must_not 보존!
    return out[:10]


# === add/replace: 법령명 후보 추출기 (LLM, 견고 버전) ===
@st.cache_data(show_spinner=False, ttl=300)
def extract_law_candidates_llm(q: str) -> list[str]:
    """
    사용자 서술에서 관련 '법령명'만 1~3개 추출.
    - JSON 외 텍스트/코드펜스가 섞여도 파싱
    - 1차 실패 시 엄격 프롬프트로 1회 재시도
    """
    if not q or (client is None):
        return []

    def _parse_json_laws(txt: str) -> list[str]:
        import re, json as _json
        t = (txt or "").strip()
        # ```json ... ``` 또는 ``` ... ``` 제거
        if "```" in t:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
            if m:
                t = m.group(1).strip()
        # 본문 중 JSON 블록만 추출
        if not t.startswith("{"):
            m = re.search(r"\{[\s\S]*\}", t)
            if m:
                t = m.group(0)
        data = _json.loads(t)
        laws = [s.strip() for s in (data.get("laws", []) or []) if s and s.strip()]
        # 중복/길이 정리
        seen, out = set(), []
        for name in laws:
            nm = name[:40]
            if nm and nm not in seen:
                seen.add(nm); out.append(nm)
        return out

    # 1) 일반 프롬프트
    try:
        SYSTEM_EXTRACT1 = (
            "너는 한국 사건 설명에서 '관련 법령명'만 1~3개 추출하는 도우미다. "
            "설명 없이 JSON만 반환하라.\n"
            '형식: {"laws":["형법","산업안전보건법"]}'
        )
        resp = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=[{"role":"system","content": SYSTEM_EXTRACT1},
                      {"role":"user","content": q.strip()}],
            temperature=0.0,
            max_tokens=128,
        )
        laws = _parse_json_laws(resp.choices[0].message.content)
        if laws:
            return laws[:3]
    except Exception:
        pass

    # 2) 엄격 프롬프트로 1회 재시도
    try:
        SYSTEM_EXTRACT2 = (
            "JSON ONLY. No code fences. No commentary. "
            'Return exactly: {"laws":["법령명1","법령명2"]}'
        )
        resp2 = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=[{"role":"system","content": SYSTEM_EXTRACT2},
                      {"role":"user","content": q.strip()}],
            temperature=0.0,
            max_tokens=96,
        )
        laws2 = _parse_json_laws(resp2.choices[0].message.content)
        if laws2:
            return laws2[:3]
    except Exception:
        pass

    # 실패 시 빈 리스트
    return []

# === LLM 플래너 & 플랜 필터 ===
import re, json

# === LLM 플래너 & 플랜 필터 ===
def _filter_items_by_plan(user_q: str, items: list[dict], plan: dict) -> list[dict]:
    name_get = lambda d: (d.get("법령명") or "")
    must = set(_canonize(plan.get("must") or []))
    must_not = set(_canonize(plan.get("must_not") or []))
    qtok = set(_canonize(_tok(plan.get("q",""))))
    target = (plan.get("target") or "").strip()

    kept = []
    for it in (items or []):
        nm = name_get(it)
        N = set(_canonize(_tok(nm)))

        # 1) q 토큰은 하드 필터 (최소한의 정합성 확보)
        if qtok and not (N & qtok):
            continue

        # 2) 제외 토큰은 계속 하드 필터
        if must_not and (N & must_not):
            continue

        # 3) must는 '랭킹용'으로만 사용 (하드 필터 제거)
        kept.append((it, N))

    # 랭킹: 사용자/플랜 관련도 + must 매칭 보너스(-3씩)
    def score(pair):
        it, N = pair
        base = _rel_score(user_q, name_get(it), plan.get("q",""))
        bonus = -3 * len(N & must)
        return base + bonus

    kept.sort(key=score)
    return [it for it, _ in kept]

@st.cache_data(show_spinner=False, ttl=180)
def propose_api_queries_llm(user_q: str) -> list[dict]:
    if not user_q or client is None:
        return []

    SYS = (
        "너는 한국 법제처(Open API) 검색 쿼리를 설계한다. JSON ONLY.\n"
        '형식: {"queries":[{"target":"law|admrul|ordin|trty","q":"검색어",'
        '"must":["반드시 포함"], "must_not":["제외할 단어"]}, ...]}\n'
        # ★ 핵심 지시
        "- **반드시 `법령명`(예: 형법, 민법, 도로교통법, 교통사고처리 특례법) 또는 "
        "'법령명 + 핵심어(예: 형법 과실치상)` 형태로 질의를 만들 것.**\n"
        "- **사건 서술(예: 지하 주차장에서 과속…) 자체를 질의로 사용하지 말 것.**\n"
        "- must는 1~3개로 간결하게, must_not은 분명히 다른 축일 때만."
          # === 규칙(중요) ===
        "- target=law 인 경우, q에는 **항상 법령명만** 적는다. 예: 민법, 형법, 도로교통법.\n"
        "- 키워드(예: 손해배상, 과실치상, 과속 등)는 q에 붙이지 말고 **must**에만 넣는다.\n"
        "- 사건 서술(예: 주차장에서 사고…)을 q로 쓰지 말고 반드시 법령명/행정규칙명/조례명 등만 사용한다.\n"
        "- 예시1: '민법 손해배상' → {\"target\":\"law\",\"q\":\"민법\",\"must\":[\"손해배상\"]}\n"
        "- 예시2: '형법 과실치상' → {\"target\":\"law\",\"q\":\"형법\",\"must\":[\"과실치상\"]}\n"
        "- 예시3: '주차장에서 사고' → {\"target\":\"law\",\"q\":\"도로교통법\",\"must\":[\"주차장\",\"사고\"]}\n"
    )
   
    try:
        resp = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=[{"role":"system","content": SYS},
                      {"role":"user","content": user_q.strip()}],
            temperature=0.0, max_tokens=220,
        )
        txt = (resp.choices[0].message.content or "").strip()
        if "```" in txt:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt); 
            if m: txt = m.group(1).strip()
        if not txt.startswith("{"):
            m = re.search(r"\{[\s\S]*\}", txt); 
            if m: txt = m.group(0)

        data = json.loads(txt) if txt else {}
        out=[]
        for it in (data.get("queries") or []):
            t = (it.get("target") or "").strip()
            q = (it.get("q") or "").strip()
            must = [x.strip() for x in (it.get("must") or []) if x.strip()]
            must_not = [x.strip() for x in (it.get("must_not") or []) if x.strip()]
            if t in {"law","admrul","ordin","trty"} and q:
                out.append({"target":t,"q":q[:60],"must":must[:4],"must_not":must_not[:6]})
        return out[:10]
    except Exception:
        return []

# --- 관련도 스코어(작을수록 관련)
def _rel_score(user_q: str, item_name: str, plan_q: str) -> int:
    U = set(_canonize(_tok(user_q)))
    I = set(_canonize(_tok(item_name)))
    P = set(_canonize(_tok(plan_q)))
    if not I:
        return 999
    # 교집합이 많고, 사용자·플랜 토큰과 겹칠수록 가점
    inter_ui = len(U & I)
    inter_pi = len(P & I)
    score = 100 - 10*inter_ui - 5*inter_pi
    # 완전 무관(교집합 0)이라면 큰 패널티
    if inter_ui == 0 and inter_pi == 0:
        score += 100
    return max(score, 0)

# 파일 상단 아무 곳(유틸 근처)에 추가
_LAWISH_RE = re.compile(r"(법|령|규칙|조례|법률)|제\d+조")
def _lawish(q: str) -> bool:
    return bool(_LAWISH_RE.search(q or ""))

def find_all_law_data(query: str, num_rows: int = 3, hint_laws: list[str] | None = None):
    results = {}

    # 0) LLM 플랜 생성
    plans = propose_api_queries_llm(query)  # 기존 LLM 플래너 사용:contentReference[oaicite:1]{index=1}

    # ✅ 0-0) 답변/질문에서 얻은 '힌트 법령들'을 최우선 시드로 주입
    if hint_laws:
        seed = [{"target":"law","q":nm, "must":[nm], "must_not": []}
                for nm in hint_laws if nm]
        # 앞에 배치 + (target,q) 중복 제거
        seen=set(); merged = seed + (plans or [])
        plans = []
        for p in merged:
            key=(p.get("target"), p.get("q"))
            if key not in seen and p.get("target") and p.get("q"):
                seen.add(key); plans.append(p)

    # 오탈자 보정/정합성 필터/법령형 우선 흐름(기존) 유지:contentReference[oaicite:2]{index=2}
    for p in plans or []:
        p["q"] = _sanitize_plan_q(query, p.get("q",""))
    plans = _filter_plans(query, plans)                      # 사용자와 토큰 교집합 or must 있으면 통과:contentReference[oaicite:3]{index=3}

    good = [p for p in (plans or []) if _lawish(p.get("q",""))]  # 법/령/규칙/조례/제n조 포함:contentReference[oaicite:4]{index=4}
    if good:
        plans = good[:10]
    else:
        # LLM 후보(질문 기준) → 규칙 폴백(최소화) 순으로 구제
        names = extract_law_candidates_llm(query) or []      # LLM 기반 후보 추출기:contentReference[oaicite:5]{index=5}
        if not names:
            # 규칙 맵은 폴백용으로만 사용
            names = [v for k, v in KEYWORD_TO_LAW.items() if k in (query or "")]
        if names:
            plans = [{"target":"law","q":n,"must":[n],"must_not":[]} for n in names][:6]
        else:
            kw = (extract_keywords_llm(query) or [])[:5]     # 키워드 빅램 폴백:contentReference[oaicite:6]{index=6}
            tmp=[]
            for i in range(len(kw)):
                for j in range(i+1, len(kw)):
                    tmp.append({"target":"law","q":f"{kw[i]} {kw[j]}","must":[kw[i],kw[j]],"must_not":[]})
            plans = tmp[:8]

    # (이하 실행/리랭크/패킹은 기존과 동일):contentReference[oaicite:7]{index=7}
    tried, err = [], []
    buckets = {"법령":("law",[]), "행정규칙":("admrul",[]), "자치법규":("ordin",[]), "조약":("trty",[])}
    for plan in plans:
        t, qx = plan["target"], plan["q"]
        tried.append(f"{t}:{qx}")
        if not qx.strip():
            err.append(f"{t}:(blank) dropped"); continue
        try:
            items, endpoint, e = _call_moleg_list(t, qx, num_rows=num_rows)  # MOLEG API 호출:contentReference[oaicite:8]{index=8}
            items = _filter_items_by_plan(query, items, plan)                # 정합성 필터 + 정렬:contentReference[oaicite:9]{index=9}
            if items:
                for label,(tt,arr) in buckets.items():
                    if t==tt: arr.extend(items)
            if e: err.append(f"{t}:{qx} → {e}")
        except Exception as ex:
            err.append(f"{t}:{qx} → {ex}")

    for label,(tt,arr) in buckets.items():
        if arr and tt=="law" and len(arr)>=2:
            arr = rerank_laws_with_llm(query, arr, top_k=8)  # LLM 리랭커(맥락 필터):contentReference[oaicite:10]{index=10}
        results[label] = {
            "items": arr, "endpoint": None,
            "error": "; ".join(err) if err else None,
            "debug": {"plans": plans, "tried": tried},
        }
    return results


# 캐시된 단일 법령 검색
@st.cache_data(show_spinner=False, ttl=300)
def search_law_data(query: str, num_rows: int = 10):
    return _call_moleg_list("law", query, num_rows=num_rows)

# 🔽 여기에 추가 (search_law_data 아래)

# 자연어 → 대표 법령명 폴백용 맵
KEYWORD_TO_LAW = {
    "개인정보": "개인정보 보호법",
    "명함": "개인정보 보호법",
    "고객정보": "개인정보 보호법",
    # === 교통사고 계열(추가) ===
    "교통사고": "교통사고처리 특례법",
    "과실치상": "형법",          # LLM이 '형법 과실치상'으로 확장
    "과속": "도로교통법",
    "음주운전": "도로교통법",
    "주차장": "도로교통법",
}


SYSTEM_EXTRACT = """너는 한국 법령명을 추출하는 도우미야.
사용자 질문에서 관련 '법령명(공식명)' 후보를 1~3개 뽑아 JSON으로만 응답해.
형식: {"laws":["개인정보 보호법","개인정보 보호법 시행령"]} 다른 말 금지.
법령명이 애매하면 가장 유력한 것 1개만.
"""

# ===== 강건한 키워드 추출기 (교체) =====
@st.cache_data(show_spinner=False, ttl=300)
def extract_keywords_llm(q: str) -> list[str]:
    """
    사용자 질문에서 핵심 키워드 2~6개를 안정적으로 추출한다.
    파이프라인: LLM(표준) -> LLM(엄격 재시도) -> 규칙 기반 폴백.
    """
    if not q or (client is None):
        return []

    def _parse_json_keywords(txt: str) -> list[str]:
        # 코드펜스/잡텍스트 제거 + JSON 블럭만 추출
        import re, json as _json
        t = (txt or "").strip()
        if "```" in t:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
            if m:
                t = m.group(1).strip()
        if not t.startswith("{"):
            m = re.search(r"\{[\s\S]*\}", t)
            if m:
                t = m.group(0)
        data = _json.loads(t)
        kws = [s.strip() for s in (data.get("keywords", []) or []) if s and s.strip()]
        # 간단 정규화/중복제거
        seen, out = set(), []
        for k in kws:
            k2 = k[:20]  # 과도한 길이 컷
            if len(k2) >= 2 and k2 not in seen:
                seen.add(k2); out.append(k2)
        return out

    # 1) LLM 1차
    try:
        SYSTEM_KW = (
            "너는 한국 법률 질의의 핵심 키워드만 추출하는 도우미야. "
            "반드시 JSON만 반환하고, 설명/코드블록/주석은 금지.\n"
            '형식: {"keywords":["폭행","위협","정당방위","과잉방위","병원 이송"]}'
        )
        resp = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=[{"role":"system","content": SYSTEM_KW},
                      {"role":"user","content": q.strip()}],
            temperature=0.0, max_tokens=96,
        )
        kws = _parse_json_keywords(resp.choices[0].message.content)
        if kws:
            return kws[:6]
    except Exception as e:
        st.session_state["_kw_extract_err1"] = str(e)

    # 2) LLM 2차(엄격 재시도)
    try:
        SYSTEM_KW_STRICT = (
            "JSON ONLY. No code fences, no commentary. "
            'Format: {"keywords":["키워드1","키워드2","키워드3"]} '
            "키워드는 2~6개, 명사/짧은 구 중심."
        )
        resp2 = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=[{"role":"system","content": SYSTEM_KW_STRICT},
                      {"role":"user","content": q.strip()}],
            temperature=0.0, max_tokens=96,
        )
        kws2 = _parse_json_keywords(resp2.choices[0].message.content)
        if kws2:
            return kws2[:6]
    except Exception as e:
        st.session_state["_kw_extract_err2"] = str(e)

    # 3) 규칙 기반 폴백(LLM 실패/차단/네트워크 예외 대비)
    def _rule_based_kw(text: str) -> list[str]:
        t = (text or "")
        # 도메인 화이트리스트 매칭(등장하는 것만 채택)
        WL = [
            "폭행", "상해", "협박", "위협", "제지", "정당방위", "과잉방위",
            "살인", "사망", "부상", "응급", "병원", "이송", "경찰", "신고",
            "건설현장", "현장소장", "근로자", "산업안전", "중대재해",
        ]
        hits = [w for w in WL if w in t]
        # 추가: 간단 한글 토큰(2~6자) 추출로 빈칸 막기
        import re
        tokens = re.findall(r"[가-힣]{2,6}", t)
        # 기능어/불용어(간단) 제거
        STOP = {"그리고","하지만","그러나","때문","경우","관련","문제","어떤","어떻게","있는지"}
        tokens = [x for x in tokens if x not in STOP]
        # 합치고 중복 제거
        combined = hits + tokens
        seen, out = set(), []
        for k in combined:
            if k not in seen:
                seen.add(k); out.append(k)
        return out[:6]

    kws3 = _rule_based_kw(q)
    if kws3:
        # 빈 결과를 캐시에 남기지 않도록: 빈 리스트면 바로 반환 말고 예외로 흘리기
        return kws3

    # 최종적으로도 비면 캐시 방지용 디버그 힌트만 남기고 빈 리스트
    st.session_state["_kw_extract_debug"] = "all_stages_failed"
    return []


# 간단 폴백(예비 — 도구 모드 기본이므로 최소화)
def find_law_with_fallback(user_query: str, num_rows: int = 10):
    laws, endpoint, err = search_law_data(user_query, num_rows=num_rows)
    if laws: return laws, endpoint, err, "primary"
    keyword_map = {"정당방위":"형법","전세":"주택임대차보호법","상가임대차":"상가건물 임대차보호법","근로계약":"근로기준법","해고":"근로기준법","개인정보":"개인정보 보호법","산재":"산업재해보상보험법","이혼":"민법"}
    text = (user_query or "")
    for k, law_name in keyword_map.items():
        if k in text:
            laws2, ep2, err2 = search_law_data(law_name, num_rows=num_rows)
            if laws2: return laws2, ep2, err2, f"fallback:{law_name}"
    return [], endpoint, err, "none"

def _append_message(role: str, content: str, **extra):
    
    txt = (content or "").strip()
    is_code_only = (txt.startswith("```") and txt.endswith("```"))
    if not txt or is_code_only:
        return
    msgs = st.session_state.get("messages", [])
    if msgs and isinstance(msgs[-1], dict) and msgs[-1].get("role")==role and (msgs[-1].get("content") or "").strip()==txt:
        # skip exact duplicate of the last message (role+content)
        return
    st.session_state.messages.append({"role": role, "content": txt, **extra})



def format_law_context(law_data: list[dict]) -> str:
    if not law_data: return "관련 법령 검색 결과가 없습니다."
    rows = []
    for i, law in enumerate(law_data, 1):
        rows.append(
            f"{i}. {law['법령명']} ({law['법령구분']})\n"
            f"   - 소관부처: {law['소관부처명']}\n"
            f"   - 시행일자: {law['시행일자']} / 공포일자: {law['공포일자']}\n"
            f"   - 링크: {law['법령상세링크'] or '없음'}"
        )
    return "\n\n".join(rows)

def animate_law_results(law_data: list[dict], delay: float = 1.0):
    if not law_data:
        st.info("관련 법령 검색 결과가 없습니다.")
        return
    n = len(law_data)
    prog = st.progress(0.0, text="관련 법령 미리보기")
    placeholder = st.empty()
    for i, law in enumerate(law_data, 1):
        with placeholder.container():
            st.markdown(
                f"""
                <div class='law-slide'>
                    <div style='font-weight:700'>🔎 {i}. {law['법령명']} <span style='opacity:.7'>({law['법령구분']})</span></div>
                    <div style='margin-top:6px'>소관부처: {law['소관부처명']}</div>
                    <div>시행일자: {law['시행일자']} / 공포일자: {law['공포일자']}</div>
                    {f"<div style='margin-top:6px'><a href='{law['법령상세링크']}' target='_blank'>법령 상세보기</a></div>" if law.get('법령상세링크') else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )
        prog.progress(i / n, text=f"관련 법령 미리보기 {i}/{n}")
        time.sleep(max(0.0, delay))
    prog.empty()

# =============================
# Azure 함수콜(툴) — 래퍼 & 스키마 & 오케스트레이션
# =============================
SUPPORTED_TARGETS = ["law", "admrul", "ordin", "trty"]

def tool_search_one(target: str, query: str, num_rows: int = 5):
    if target not in SUPPORTED_TARGETS:
        return {"error": f"unsupported target: {target}"}
    items, endpoint, err = _call_moleg_list(target, query, num_rows=num_rows)
    return {"target": target, "query": query, "endpoint": endpoint, "error": err, "items": items}

def tool_search_multi(queries: list, num_rows: int = 5):
    out = []
    for q in queries:
        t = q.get("target","law"); s = q.get("query","")
        out.append(tool_search_one(t, s, num_rows=num_rows))
    return out

TOOLS = [
    {
        "type":"function",
        "function":{
            "name":"search_one",
            "description":"MOLEG 목록 API에서 단일 카테고리를 검색한다.",
            "parameters":{
                "type":"object",
                "properties":{
                    "target":{"type":"string","enum":SUPPORTED_TARGETS},
                    "query":{"type":"string"},
                    "num_rows":{"type":"integer","minimum":1,"maximum":10,"default":5}
                },
                "required":["target","query"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"search_multi",
            "description":"여러 카테고리/질의어를 한 번에 검색한다.",
            "parameters":{
                "type":"object",
                "properties":{
                    "queries":{
                        "type":"array",
                        "items":{
                            "type":"object",
                            "properties":{
                                "target":{"type":"string","enum":SUPPORTED_TARGETS},
                                "query":{"type":"string"}
                            },
                            "required":["target","query"]
                        }
                    },
                    "num_rows":{"type":"integer","minimum":1,"maximum":10,"default":5}
                },
                "required":["queries"]
            }
        }
    }
]

# ============================
# [GPT PATCH] app.py 연결부
# 붙여넣는 위치: client/AZURE/TOOLS 등 준비가 끝난 "아래",
#               사이드바/레이아웃 렌더링이 시작되기 "위"
# ============================

# 1) imports
from modules import AdviceEngine, Intent, classify_intent, pick_mode, build_sys_for_mode  # noqa: F401

# 2) 엔진 생성 (한 번만)
engine = None
try:
    # 아래 객체들은 app.py 상단에서 이미 정의되어 있어야 합니다.
    # - client, AZURE, TOOLS
    # - safe_chat_completion
    # - tool_search_one, tool_search_multi
    # - prefetch_law_context, _summarize_laws_for_primer
    if client and AZURE and TOOLS:
        engine = AdviceEngine(
            client=client,
            model=AZURE["deployment"],
            tools=TOOLS,
            safe_chat_completion=safe_chat_completion,
            tool_search_one=tool_search_one,
            tool_search_multi=tool_search_multi,
            prefetch_law_context=prefetch_law_context,            # 있으면 그대로
            summarize_laws_for_primer=_summarize_laws_for_primer, # 있으면 그대로
            temperature=0.2,
        )
except NameError:
    # 만약 위 객체들이 아직 정의되기 전 위치라면,
    # 이 패치를 해당 정의 '아래'로 옮겨 붙이세요.
    pass

# =============================
# 키워드 기본값/위젯 헬퍼 (with st.sidebar: 위에 배치)
# =============================

# 탭별 기본 키워드 1개(없으면 첫 항목 사용)
DEFAULT_KEYWORD = {
    "법령": "개정",
    "행정규칙": "개정",
    "자치법규": "개정",
    "조약": "비준",
    "판례": "대법원",
    "헌재": "위헌",
    "해석례": "유권해석",
    "용어/별표": "정의",   # ← '용어' 대신 '정의'를 기본으로 권장
}

def one_default(options, prefer=None):
    """옵션 목록에서 기본으로 1개만 선택해 반환"""
    if not options:
        return []
    if prefer and prefer in options:
        return [prefer]
    return [options[0]]

# st_tags가 있으면 태그 위젯, 없으면 multiselect로 동작
try:
    from streamlit_tags import st_tags
    def kw_input(label, options, key, tab_name=None):
        prefer = DEFAULT_KEYWORD.get(tab_name)
        return st_tags(
            label=label,
            text="쉼표(,) 또는 Enter로 추가/삭제",
            value=one_default(options, prefer),   # ✅ 기본 1개만
            suggestions=options,
            maxtags=len(options),
            key=key,
        )
except Exception:
    def kw_input(label, options, key, tab_name=None):
        prefer = DEFAULT_KEYWORD.get(tab_name)
        return st.multiselect(
            label=label,
            options=options,
            default=one_default(options, prefer), # ✅ 기본 1개만
            key=key,
            help="필요한 키워드만 추가로 선택하세요.",
        )

# =============================
# Sidebar: 링크 생성기 (무인증)
# =============================
with st.sidebar:
    # --- 사이드바: 새 대화 버튼(링크 생성기 위) ---
    if st.button("🆕 새 대화", type="primary", use_container_width=True, key="__btn_new_chat__"):
        for k in ("messages", "_last_user_nonce", "_pending_user_q", "_pending_user_nonce", "_last_ans_hash"):
            st.session_state.pop(k, None)
        st.session_state["_clear_input"] = True
        st.rerun()

    st.header("🔗 링크 생성기 (무인증)")
    tabs = st.tabs(["법령", "행정규칙", "자치법규", "조약", "판례", "헌재", "해석례", "용어/별표"])

    # persist/restore active sidebar tab across reruns
    st.markdown("""
<script>
(function(){
  const KEY = "left_sidebar_active_tab";
  function labelOf(btn){ return (btn?.innerText || btn?.textContent || "").trim(); }
  function restore(){
    const want = sessionStorage.getItem(KEY);
    if(!want) return false;
    const btns = Array.from(window.parent.document.querySelectorAll('[data-testid="stSidebar"] [role="tablist"] button[role="tab"]'));
    if(btns.length === 0) return false;
    const match = btns.find(b => labelOf(b) === want);
    if(!match) return false;
    if(match.getAttribute('aria-selected') !== 'true'){ match.click(); }
    return true;
  }
  function bind(){
    const root = window.parent.document.querySelector('[data-testid="stSidebar"]');
    if(!root) return;
    // Save when user clicks a tab
    root.addEventListener('click', (e)=>{
      const b = e.target.closest('button[role="tab"]');
      if(b){ sessionStorage.setItem(KEY, labelOf(b)); }
    }, true);
    // Keep trying to restore selection until ready
    const tid = setInterval(()=>{ if(restore()) clearInterval(tid); }, 100);
    setTimeout(()=>clearInterval(tid), 4000);
    // Also restore when DOM changes (e.g., reruns)
    new MutationObserver(()=>restore()).observe(root, {subtree:true, childList:true, attributes:true});
  }
  window.addEventListener('load', bind, {once:true});
  setTimeout(bind, 0);
})();
</script>
""", unsafe_allow_html=True)

    # 공통 추천 프리셋(모두 1개만 기본 선택되도록 kw_input + DEFAULT_KEYWORD 활용)
    adm_suggest    = cached_suggest_for_tab("admrul")
    ordin_suggest  = cached_suggest_for_tab("ordin")
    trty_suggest   = cached_suggest_for_tab("trty")
    case_suggest   = cached_suggest_for_tab("prec")
    cc_suggest     = cached_suggest_for_tab("cc")
    interp_suggest = cached_suggest_for_tab("expc")
    term_suggest   = ["정의", "용어", "별표", "서식"]

    # ───────────────────────── 법령
    with tabs[0]:
        law_name = st.text_input("법령명", value="민법", key="sb_law_name")
        # 법령명 기반 추천
        law_keys = kw_input("키워드(자동 추천)",
                            cached_suggest_for_law(law_name),
                            key="sb_law_keys",
                            tab_name="법령")

        if st.button("법령 상세 링크 만들기", key="sb_btn_law"):
            url = hangul_law_with_keys(law_name, law_keys) if law_keys else hangul_by_name("법령", law_name)
            st.session_state["gen_law"] = {"url": url, "kind": "law", "q": law_name}

        if "gen_law" in st.session_state:
            d = st.session_state["gen_law"]
            present_url_with_fallback(d["url"], d["kind"], d["q"], label_main="새 탭에서 열기")

    # ───────────────────────── 행정규칙
    with tabs[1]:
        adm_name = st.text_input("행정규칙명", value="수입통관사무처리에관한고시", key="sb_adm_name")
        dept     = st.selectbox("소관 부처(선택)", MINISTRIES, index=0, key="sb_adm_dept")
        adm_keys = kw_input("키워드(자동 추천)", adm_suggest, key="sb_adm_keys", tab_name="행정규칙")

        colA, colB = st.columns(2)
        with colA: issue_no = st.text_input("공포번호(선택)", value="", key="sb_adm_no")
        with colB: issue_dt = st.text_input("공포일자(YYYYMMDD, 선택)", value="", key="sb_adm_dt")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("행정규칙 링크 만들기", key="sb_btn_adm"):
                url = hangul_admrul_with_keys(adm_name, issue_no, issue_dt) if (issue_no and issue_dt) else hangul_by_name("행정규칙", adm_name)
                st.session_state["gen_adm"] = {"url": url, "kind": "admrul", "q": adm_name}
        with col2:
            if st.button("행정규칙(부처/키워드) 검색 링크", key="sb_btn_adm_dept"):
                keys = " ".join(adm_keys) if adm_keys else ""
                q = " ".join([x for x in [adm_name,
                                          (dept if dept and dept != MINISTRIES[0] else ""),
                                          keys] if x])
                url = build_fallback_search("admrul", q)
                st.session_state["gen_adm_dept"] = {"url": url, "kind": "admrul", "q": q}

        if "gen_adm" in st.session_state:
            d = st.session_state["gen_adm"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])
        if "gen_adm_dept" in st.session_state:
            d = st.session_state["gen_adm_dept"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])

    # ───────────────────────── 자치법규
    with tabs[2]:
        ordin_name = st.text_input("자치법규명", value="서울특별시경관조례", key="sb_ordin_name")
        local_keys = kw_input("키워드(자동 추천)", ordin_suggest, key="sb_local_keys", tab_name="자치법규")

        colA, colB = st.columns(2)
        with colA: ordin_no = st.text_input("공포번호(선택)", value="", key="sb_ordin_no")
        with colB: ordin_dt = st.text_input("공포일자(YYYYMMDD, 선택)", value="", key="sb_ordin_dt")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("자치법규 링크 만들기", key="sb_btn_ordin"):
                url = hangul_ordin_with_keys(ordin_name, ordin_no, ordin_dt) if (ordin_no and ordin_dt) else hangul_by_name("자치법규", ordin_name)
                st.session_state["gen_ordin"] = {"url": url, "kind": "ordin", "q": ordin_name}
        with col2:
            if st.button("자치법규(키워드) 검색 링크", key="sb_btn_ordin_kw"):
                q = " ".join([ordin_name] + (local_keys or []))
                url = build_fallback_search("ordin", q)
                st.session_state["gen_ordin_kw"] = {"url": url, "kind": "ordin", "q": q}

        if "gen_ordin" in st.session_state:
            d = st.session_state["gen_ordin"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])
        if "gen_ordin_kw" in st.session_state:
            d = st.session_state["gen_ordin_kw"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])

    # ───────────────────────── 조약
    with tabs[3]:
        trty_no = st.text_input("조약 번호", value="2193", key="sb_trty_no")
        eff_dt  = st.text_input("발효일자(YYYYMMDD)", value="20140701", key="sb_trty_eff")
        trty_keys = kw_input("키워드(자동 추천)", trty_suggest, key="sb_trty_keys", tab_name="조약")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("조약 상세 링크 만들기", key="sb_btn_trty"):
                url = hangul_trty_with_keys(trty_no, eff_dt)
                st.session_state["gen_trty"] = {"url": url, "kind": "trty", "q": trty_no}
        with col2:
            if st.button("조약(키워드) 검색 링크", key="sb_btn_trty_kw"):
                q = " ".join([trty_no] + (trty_keys or [])) if trty_no else " ".join(trty_keys or [])
                url = build_fallback_search("trty", q)
                st.session_state["gen_trty_kw"] = {"url": url, "kind": "trty", "q": q}

        if "gen_trty" in st.session_state:
            d = st.session_state["gen_trty"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])
        if "gen_trty_kw" in st.session_state:
            d = st.session_state["gen_trty_kw"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])

    # ───────────────────────── 판례
    with tabs[4]:
        case_no = st.text_input("사건번호(예: 2010다52349)", value="2010다52349", key="sb_case_no")
        case_keys = kw_input("키워드(자동 추천)", case_suggest, key="sb_case_keys", tab_name="판례")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("대법원 판례 링크 만들기", key="sb_btn_prec"):
                url = build_scourt_link(case_no)
                st.session_state["gen_prec"] = {"url": url, "kind": "prec", "q": case_no}
        with col2:
            if st.button("판례(키워드) 검색 링크", key="sb_btn_prec_kw"):
                q = " ".join([case_no] + (case_keys or [])) if case_no else " ".join(case_keys or [])
                url = build_fallback_search("prec", q)
                st.session_state["gen_prec_kw"] = {"url": url, "kind": "prec", "q": q}

        if "gen_prec" in st.session_state:
            d = st.session_state["gen_prec"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])
        if "gen_prec_kw" in st.session_state:
            d = st.session_state["gen_prec_kw"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])

    # ───────────────────────── 헌재
    with tabs[5]:
        cc_q = st.text_input("헌재 사건/키워드", value="2022헌마1312", key="sb_cc_q")
        cc_keys = kw_input("키워드(자동 추천)", cc_suggest, key="sb_cc_keys", tab_name="헌재")

        if st.button("헌재 검색 링크 만들기", key="sb_btn_cc"):
            q = " ".join([cc_q] + (cc_keys or [])) if cc_q else " ".join(cc_keys or [])
            url = build_fallback_search("cc", q)
            st.session_state["gen_cc"] = {"url": url, "kind": "cc", "q": q}

        if "gen_cc" in st.session_state:
            d = st.session_state["gen_cc"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])

    # ───────────────────────── 해석례
    with tabs[6]:
        colA, colB = st.columns(2)
        with colA:
            expc_id = st.text_input("해석례 ID", value="313107", key="sb_expc_id")
            if st.button("해석례 링크 만들기", key="sb_btn_expc"):
                url = expc_public_by_id(expc_id)
                st.session_state["gen_expc"] = {"url": url, "kind": "expc", "q": expc_id}
        with colB:
            interp_keys = kw_input("키워드(자동 추천)", interp_suggest, key="sb_interp_keys", tab_name="해석례")
            if st.button("해석례(키워드) 검색 링크", key="sb_btn_expc_kw"):
                q = " ".join([expc_id] + (interp_keys or [])) if expc_id else " ".join(interp_keys or [])
                url = build_fallback_search("expc", q)
                st.session_state["gen_expc_kw"] = {"url": url, "kind": "expc", "q": q}

        if "gen_expc" in st.session_state:
            d = st.session_state["gen_expc"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])
        if "gen_expc_kw" in st.session_state:
            d = st.session_state["gen_expc_kw"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])

    # ───────────────────────── 용어/별표
    with tabs[7]:
        col1, col2 = st.columns(2)
        with col1:
            term_id   = st.text_input("용어 ID", value="100034", key="sb_term_id")
            term_keys = kw_input("키워드(자동 추천)", term_suggest, key="sb_term_keys", tab_name="용어/별표")
            if st.button("용어사전 링크 만들기", key="sb_btn_term"):
                url = f"https://www.law.go.kr/LSW/termInfoR.do?termSeq={up.quote(term_id)}"
                st.session_state["gen_term"] = {"url": url, "kind": "term", "q": term_id}
        with col2:
            flseq = st.text_input("별표·서식 파일 ID", value="110728887", key="sb_flseq")
            if st.button("별표/서식 파일 다운로드", key="sb_btn_file"):
                url = licbyl_file_download(flseq)
                st.session_state["gen_file"] = {"url": url, "kind": "file", "q": flseq}

        if "gen_term" in st.session_state:
            d = st.session_state["gen_term"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])
        if "gen_file" in st.session_state:
            d = st.session_state["gen_file"]
            present_url_with_fallback(d["url"], d["kind"], d["q"])

# 1) pending → messages 먼저 옮김
user_q = _push_user_from_pending()

# capture the nonce associated with this pending input (if any)
# === 지금 턴이 '답변을 생성하는 런'인지 여부 (스트리밍 중 표시/숨김에 사용)
ANSWERING = bool(user_q)
st.session_state["__answering__"] = ANSWERING

# 2) 대화 시작 여부 계산 (교체된 함수)
chat_started = _chat_started()

# chat_started 계산 직후에 추가
st.markdown(f"""
<script>
document.body.classList.toggle('chat-started', {str(chat_started).lower()});
document.body.classList.toggle('answering', {str(ANSWERING).lower()});
</script>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* ✅ 포스트-챗 UI(업로더+입력폼)는 '답변 생성 중'에만 숨김 */
body.answering .post-chat-ui{ margin-top: 8px; }

/* ✅ 기존 chatbar 컴포넌트는 사용하지 않으므로 완전 숨김 */
#chatbar-fixed { display: none !important; }
/* 답변 중일 때만 하단 여백 축소 */
body.answering .block-container { 
    padding-bottom: calc(var(--chat-gap) + 24px) !important; 
}
</style>
""", unsafe_allow_html=True)

# ✅ PRE-CHAT: 완전 중앙(뷰포트 기준) + 여백 제거
if not chat_started:
    st.markdown("""
    <style>
      /* 프리챗: 우측 패널만 숨기고, 스크롤을 잠가 상단 고정 */
      #search-flyout{ display:none !important; }
      html, body{ height:100%; overflow-y:hidden !important; }
      .main > div:first-child{ height:100vh !important; }
      .block-container{ min-height:100vh !important; padding-top:12px !important; padding-bottom:0 !important; }
      /* 전역 가운데 정렬 규칙이 있어도 프리챗에선 히어로를 '위에서부터' 배치 */
      .center-hero{ min-height:auto !important; display:block !important; }
    </style>
    <script>
    (function(){
      try{ history.scrollRestoration='manual'; }catch(e){}
      const up=()=>{ window.scrollTo(0,0); if(document.activeElement) document.activeElement.blur(); };
      up(); setTimeout(up,0); setTimeout(up,50);
      document.addEventListener('focusin', up, true);
      new MutationObserver(up).observe(document.body, {subtree:true, childList:true});
    })();
    </script>
    """, unsafe_allow_html=True)

    st.markdown("""
    <style>
      /* 우측 패널만 숨김 */
      #search-flyout{ display:none !important; }

      /* ⛳️ 프리챗: 스크롤 생기지 않게 잠그고 상단 고정 */
      html, body{ height:100%; overflow-y:hidden !important; }
      .main > div:first-child{ height:100vh !important; }              /* Streamlit 루트 */
      .block-container{
        min-height:100vh !important;   /* 화면만큼만 */
        padding-top:12px !important;
        padding-bottom:0 !important;   /* 바닥 여백 제거 */
        margin-left:auto !important; margin-right:auto !important;
      }
    </style>
    <script>
    (function(){
      try{ history.scrollRestoration='manual'; }catch(e){}
      const up=()=>{ window.scrollTo(0,0); if(document.activeElement) document.activeElement.blur(); };
      up(); setTimeout(up,0); setTimeout(up,50);    // 자동 포커스 대비
      document.addEventListener('focusin', up, true);
      new MutationObserver(up).observe(document.body, {subtree:true, childList:true});
    })();
    </script>            
               
    """, unsafe_allow_html=True)

    render_pre_chat_center()
    st.stop()
    
else:
    st.markdown("""
    <style>
      /* 채팅 시작 후: 스크롤 정상 복원 */
      html, body{ overflow-y:auto !important; }
      .main > div:first-child{ height:auto !important; }
      .block-container{ min-height:auto !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <style>
      /* 📌 채팅 시작 후에는 정상 스크롤 */
      html, body{ overflow-y:auto !important; }
      .block-container{ min-height:auto !important; }
    </style>
    """, unsafe_allow_html=True)

    # ... 기존 렌더링 계속


# 🎯 대화 전에는 우측 패널 숨기고, 여백을 0으로 만들어 완전 중앙 정렬
if not chat_started:
    st.markdown("""
    <style>
      /* hide right rail before first message */
      #search-flyout { display: none !important; }
      /* remove right gutter so hero sits dead-center */
      @media (min-width:1280px) { .block-container { padding-right: 0 !important; } }
      /* bottom padding 크게 줄여서 화면 정중앙에 오도록 */
      .block-container { padding-bottom: 64px !important; }
      /* hero 높이 살짝 줄여 위/아래 균형 */
      .center-hero { min-height: calc(100vh - 160px) !important; }
    </style>
    """, unsafe_allow_html=True)

# 3) 화면 분기
if not chat_started:
    render_pre_chat_center()   # 중앙 히어로 + 중앙 업로더
    st.stop()
else:
    # 🔧 대화 시작 후에는 첨부파일 박스를 렌더링하지 않음 (완전히 제거)
    # 스트리밍 중에는 업로더 숨김 (렌더 자체 생략)
    # if not ANSWERING:
    #     render_bottom_uploader()   # 하단 고정 업로더 - 주석 처리
    pass

# === 대화 시작 후: 우측 레일을 피해서 배치(침범 방지) ===
# ----- RIGHT FLYOUT: align once to the question box, stable -----
st.markdown("""
<style>
  :root{
    --flyout-width: 360px;   /* 우측 패널 폭 */
    --flyout-gap:   80px;    /* 본문(답변영역)과의 가로 간격 */
  }

  /* 본문이 우측 패널을 피해 배치되도록 여백 확보 */
  @media (min-width:1280px){
    .block-container{
      padding-right: calc(var(--flyout-width) + var(--flyout-gap)) !important;
    }
  }

  /* ====== 패널 배치 모드 ======
     (A) 화면 고정(스크롤해도 항상 보임) → position: fixed (기본)
     (B) 따라오지 않게(본문과 함께 위로 올라가도록) → position: sticky 로 교체
     원하는 쪽 한 줄만 쓰세요.
  */
  @media (min-width:1280px){
    #search-flyout{
      position: fixed !important;                 /* ← A) 화면 고정 */
      /* position: sticky !important;             /* ← B) 따라오지 않게: 이 줄로 교체 */
      top: var(--flyout-top, 120px) !important;   /* JS가 한 번 계산해 넣음 */
      right: 24px !important;
      left: auto !important; bottom: auto !important;

      width: var(--flyout-width) !important;
      max-width: 38vw !important;
      max-height: calc(100vh - var(--flyout-top,120px) - 24px) !important;
      overflow: auto !important;
      z-index: 58 !important;                     /* 업로더(60), 입력창(70)보다 낮게 */
    }
  }

  /* 모바일/좁은 화면은 자연스럽게 문서 흐름 */
  @media (max-width:1279px){
    #search-flyout{ position: static !important; max-height:none !important; overflow:visible !important; }
    .block-container{ padding-right: 0 !important; }
  }
</style>

<script>
(() => {
  // 질문 입력 위치를 "한 번만" 읽어서 --flyout-top 을 설정
  const CANDIDATES = [
    '#chatbar-fixed',
    'section[data-testid="stChatInput"]',
    '.block-container textarea'
  ];
  let done = false;

  function alignOnce(){
    if (done) return;
    const fly = document.querySelector('#search-flyout');
    if (!fly) return;

    let target = null;
    for (const sel of CANDIDATES){
      target = document.querySelector(sel);
      if (target) break;
    }
    if (!target) return;

    const r = target.getBoundingClientRect();       // viewport 기준
    const top = Math.max(12, Math.round(r.top));
    document.documentElement.style.setProperty('--flyout-top', top + 'px');
    done = true;  // 한 번만
  }

  // 1) 첫 렌더 직후
  window.addEventListener('load', () => setTimeout(alignOnce, 0));

  // 2) 대상이 늦게 생겨도 한 번만 정렬
  const mo = new MutationObserver(() => alignOnce());
  mo.observe(document.body, {childList: true, subtree: true});
  (function stopWhenDone(){ if (done) mo.disconnect(); requestAnimationFrame(stopWhenDone); })();

  // 3) 창 크기 변경 시 한 번 재정렬
  window.addEventListener('resize', () => { done = false; alignOnce(); });
})();
</script>
""", unsafe_allow_html=True)




with st.container():
    st.session_state['_prev_assistant_txt'] = ''  # reset per rerun
    for i, m in enumerate(st.session_state.messages):
        # --- Hero above the most recent user question (shows during loading & after) ---
        if '_latest_user_index' not in st.session_state:
            _msgs = st.session_state.get('messages', [])
            _latest = None
            for _idx in range(len(_msgs)-1, -1, -1):
                _mm = _msgs[_idx]
                if isinstance(_mm, dict) and _mm.get('role') == 'user' and (_mm.get('content') or '').strip():
                    _latest = _idx
                    break
            st.session_state['_latest_user_index'] = _latest


        # --- UI dedup guard: skip if same assistant content as previous ---
        if isinstance(m, dict) and m.get('role')=='assistant':
            _t = (m.get('content') or '').strip()
            if '_prev_assistant_txt' not in st.session_state:
                st.session_state['_prev_assistant_txt'] = ''
            if _t and _t == st.session_state.get('_prev_assistant_txt',''):
                continue
            st.session_state['_prev_assistant_txt'] = _t
        role = m.get("role")
        content = (m.get("content") or "")
        if role == "assistant" and not content.strip():
            continue  # ✅ 내용이 비면 말풍선 자체를 만들지 않음
        # If this is the latest user bubble, show the shared hero just above it
        if (role == "user") and (st.session_state.get('_latest_user_index') == i):
            st.markdown('<div class="hero-in-chat">' + HERO_HTML + '</div>', unsafe_allow_html=True)


        with st.chat_message(role):
            if role == "assistant":
                render_bubble_with_copy(content, key=f"past-{i}")
                if m.get("law"):
                    with st.expander("📋 이 턴에서 참고한 법령 요약"):
                        for j, law in enumerate(m["law"], 1):
                            st.write(f"**{j}. {law['법령명']}** ({law['법령구분']})  | 시행 {law['시행일자']}  | 공포 {law['공포일자']}")
                            if law.get("법령상세링크"):
                                st.write(f"- 링크: {law['법령상세링크']}")
            else:
                st.markdown(content)


# ✅ 답변 말풍선 바로 아래에 입력/업로더 붙이기 (답변 생성 중이 아닐 때만)
if chat_started and not st.session_state.get("__answering__", False):
    render_post_chat_simple_ui()

# ✅ 메시지 루프 바로 아래(이미 _inject_right_rail_css() 다음 추천) — 항상 호출
def _current_q_and_answer():
    msgs = st.session_state.get("messages", [])
    last_q = next((m for m in reversed(msgs) if m.get("role")=="user" and (m.get("content") or "").strip()), None)
    last_a = next((m for m in reversed(msgs) if m.get("role")=="assistant" and (m.get("content") or "").strip()), None)
    return (last_q or {}).get("content",""), (last_a or {}).get("content","")

# 🔽 대화가 시작된 뒤에만 우측 패널 노출
# ✅ 로딩(스트리밍) 중에는 패널을 렌더링하지 않음
if chat_started and not st.session_state.get("__answering__", False):
    q_for_panel, ans_for_panel = _current_q_and_answer()
    hints = extract_law_names_from_answer(ans_for_panel) if ans_for_panel else None
    render_search_flyout(q_for_panel or user_q, num_rows=8, hint_laws=hints, show_debug=SHOW_SEARCH_DEBUG)

# ===============================
# 좌우 분리 레이아웃: 왼쪽(답변) / 오른쪽(통합검색)
# ===============================\n
if user_q:
    # --- streaming aggregator v2: keep deltas for preview, but FINAL wins ---
    stream_box = None
    deltas_only = ""
    final_payload = ""
    collected_laws = []

    if client and AZURE:
        stream_box = st.empty()

    try:
        if stream_box is not None:
            stream_box.markdown("_AI가 질의를 해석하고, 법제처 DB를 검색 중입니다._")

        for kind, payload, law_list in ask_llm_with_tools(user_q, num_rows=5, stream=True):
            if kind == "delta":
                if payload:
                    deltas_only += payload
                    if SHOW_STREAM_PREVIEW and stream_box is not None:
                        stream_box.markdown(_normalize_text(deltas_only[-1500:]))
            elif kind == "final":
                final_payload  = (payload or "")
                collected_laws = law_list or []
                break

    except Exception as e:
        # 예외 시 폴백
        laws, ep, err, mode = find_law_with_fallback(user_q, num_rows=10)
        collected_laws = laws
        law_ctx = format_law_context(laws)
        title = "법률 자문 메모"
        base_text = f"{title}\n\n{law_ctx}\n\n(오류: {e})"
    else:
        # 정상 경로: final이 있으면 final, 없으면 delta 누적 사용
        base_text = (final_payload.strip() or deltas_only)

    # --- Postprocess & de-dup ---
    final_text = apply_final_postprocess(base_text, collected_laws)
    final_text = _dedupe_repeats(final_text)

    # --- seatbelt: skip if same answer already stored this turn ---
    _ans_hash = _hash_text(final_text)
    if st.session_state.get('_last_ans_hash') == _ans_hash:
        final_text = ""
    else:
        st.session_state['_last_ans_hash'] = _ans_hash

    if final_text.strip():
        # --- per-turn nonce guard: allow only one assistant append per user turn ---
        _nonce = st.session_state.get('current_turn_nonce') or st.session_state.get('_pending_user_nonce')
        _done = st.session_state.get('_nonce_done', {})
        if not (_nonce and _done.get(_nonce)):
            _append_message('assistant', final_text, law=collected_laws)
            if _nonce:
                _done[_nonce] = True
                st.session_state['_nonce_done'] = _done
            st.session_state['last_q'] = user_q
            st.session_state.pop('_pending_user_q', None)
            st.session_state.pop('_pending_user_nonce', None)
            st.rerun()

    # 프리뷰 컨테이너 비우기
    if stream_box is not None:
        try:
            stream_box.empty()
        except Exception:
            pass

# (moved) post-chat UI is now rendered inline under the last assistant message.
