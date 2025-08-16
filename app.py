# app.py — Optimized single chat window (past → present) with bottom streaming
from __future__ import annotations

import io, os, re, json, time
from datetime import datetime
import urllib.parse as up
import xml.etree.ElementTree as ET

import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI

# ===== Local modules =====
from chatbar import chatbar
# (첨부 파일을 나중에 확장할 수 있도록 import만 유지)
from utils_extract import extract_text_from_pdf, extract_text_from_docx, read_txt, sanitize

# =============================
# Config & Style
# =============================
PAGE_MAX_WIDTH = 1020
BOTTOM_PADDING_PX = 120   # 고정 ChatBar와 겹침 방지용

st.set_page_config(
    page_title="법제처 AI 챗봇",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
/* Layout width */
.block-container {{ max-width:{PAGE_MAX_WIDTH}px; margin:0 auto; padding-bottom:{BOTTOM_PADDING_PX}px; }}
.stChatInput    {{ max-width:{PAGE_MAX_WIDTH}px; margin-left:auto; margin-right:auto; }}
section.main    {{ padding-bottom:0; }}

/* Header */
.header {{
  text-align:center; padding:1rem; border-radius:12px;
  background:linear-gradient(135deg,#8b5cf6,#a78bfa); color:#fff; margin:0 0 1rem 0;
}}
h2, h3 {{ font-size:1.1rem !important; font-weight:600 !important; margin:0.8rem 0 0.4rem; }}

/* Bubble-like markdown */
.stMarkdown > div {{
  background:var(--bubble-bg,#1f1f1f); color:var(--bubble-fg,#f5f5f5);
  border-radius:14px; padding:14px 16px; box-shadow:0 1px 8px rgba(0,0,0,.12);
}}
[data-theme="light"] .stMarkdown > div {{
  --bubble-bg:#fff; --bubble-fg:#222; box-shadow:0 1px 8px rgba(0,0,0,.06);
}}
.stMarkdown ul, .stMarkdown ol {{ margin-left:1.1rem; }}
.stMarkdown blockquote {{ margin:8px 0; padding-left:12px; border-left:3px solid rgba(255,255,255,.25); }}

/* Copy button under bubbles */
.copy-row{{ display:flex; justify-content:flex-end; margin:6px 4px 0 0; }}
.copy-btn{{
  display:inline-flex; align-items:center; gap:6px; padding:6px 10px;
  border:1px solid rgba(255,255,255,.15); border-radius:10px; background:rgba(0,0,0,.25);
  backdrop-filter:blur(4px); cursor:pointer; font-size:12px; color:inherit;
}}
[data-theme="light"] .copy-btn{{ background:rgba(255,255,255,.9); border-color:#ddd; }}
.copy-btn svg{{ pointer-events:none }}
</style>
""", unsafe_allow_html=True)

st.markdown(
    """
    <div class="header">
        <h2>⚖️ 법제처 인공지능 법률 상담 플랫폼</h2>
        <div>법제처 공식 데이터를 AI가 분석해 답변을 제공합니다</div>
        <div>당신의 문제를 입력하면 법률 자문서를 출력해 줍니다. 당신의 문제를 입력해 보세요</div>
        <hr style="margin:1rem 0;border:0;border-top:1px solid rgba(255,255,255,0.4)">
        <div style="text-align:left;font-size:0.9rem;line-height:1.4">
            📌 <b>제공 범위</b><br>
            1. 국가 법령(법률·시행령·시행규칙 등)<br>
            2. 행정규칙 (예규·고시·훈령·지침)<br>
            3. 자치법규 (조례·규칙 등)<br>
            4. 조약 (양자·다자)<br>
            5. 법령 해석례 (법제처 유권해석)<br>
            6. 헌법재판소 결정례 (위헌·합헌·각하 등)<br>
            7. 별표·서식<br>
            8. 법령 용어 사전
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =============================
# Utilities
# =============================
_CASE_NO_RE = re.compile(r'(19|20)\d{2}[가-힣]{1,3}\d{1,6}')
_HBASE = "https://www.law.go.kr"

def _normalize_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in s.split("\n")]
    while lines and not lines[0].strip(): lines.pop(0)
    while lines and not lines[-1].strip(): lines.pop()
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

def render_bubble_with_copy(message: str, key: str):
    message = _normalize_text(message)
    st.markdown(message)
    safe_raw_json = json.dumps(message)
    components.html(f"""
    <div class="copy-row">
      <button id="copy-{key}" class="copy-btn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <path d="M9 9h9v12H9z" stroke="currentColor"/>
          <path d="M6 3h9v3" stroke="currentColor"/>
          <path d="M6 6h3v3" stroke="currentColor"/>
        </svg>
        복사
      </button>
    </div>
    <script>
    (function(){{
      const btn = document.getElementById("copy-{key}");
      if (!btn) return;
      btn.addEventListener("click", async () => {{
        try {{
          await navigator.clipboard.writeText({safe_raw_json});
          const old = btn.innerHTML; btn.innerHTML = "복사됨!";
          setTimeout(()=>btn.innerHTML = old, 1200);
        }} catch(e) {{ alert("복사 실패: " + e); }}
      }});
    }})();
    </script>
    """, height=40)

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
def hangul_law_with_keys(name: str, keys): return f"{_HBASE}/법령/{_henc(name)}/({','.join(_henc(k) for k in keys if k)})"
def hangul_law_article(name: str, subpath: str) -> str: return f"{_HBASE}/법령/{_henc(name)}/{_henc(subpath)}"
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
        return 200 <= r.status_code < 400
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

if "messages" not in st.session_state: st.session_state.messages = []
if "settings" not in st.session_state: st.session_state.settings = {
    "num_rows": 5,
    "include_search": True,
    "safe_mode": False,
}

# =============================
# MOLEG API (Law Search)
# =============================
@st.cache_data(show_spinner=False, ttl=300)
def search_law_data(query: str, num_rows: int = 5):
    """법제처 API로 관련 법령 메타데이터 조회"""
    if not LAW_API_KEY:
        return [], None, "LAW_API_KEY 미설정"
    params = {
        "serviceKey": up.quote_plus(LAW_API_KEY),
        "target": "law",
        "query": query,
        "numOfRows": max(1, min(10, int(num_rows))),
        "pageNo": 1,
    }
    for url in ("https://apis.data.go.kr/1170000/law/lawSearchList.do",
                "http://apis.data.go.kr/1170000/law/lawSearchList.do"):
        try:
            res = requests.get(url, params=params, timeout=15)
            res.raise_for_status()
            root = ET.fromstring(res.text)
            laws = [{
                "법령명": law.findtext("법령명한글", default=""),
                "법령약칭명": law.findtext("법령약칭명", default=""),
                "소관부처명": law.findtext("소관부처명", default=""),
                "법령구분명": law.findtext("법령구분명", default=""),
                "시행일자": law.findtext("시행일자", default=""),
                "공포일자": law.findtext("공포일자", default=""),
                "법령상세링크": law.findtext("법령상세링크", default=""),
            } for law in root.findall(".//law")]
            return laws, url, None
        except Exception as e:
            last_err = e
    return [], None, f"법제처 API 연결 실패: {last_err}"

def format_law_context(law_data: list[dict]) -> str:
    if not law_data: return "관련 법령 검색 결과가 없습니다."
    rows = []
    for i, law in enumerate(law_data, 1):
        rows.append(
            f"{i}. {law['법령명']} ({law['법령구분명']})\n"
            f"   - 소관부처: {law['소관부처명']}\n"
            f"   - 시행일자: {law['시행일자']} / 공포일자: {law['공포일자']}\n"
            f"   - 링크: {law['법령상세링크'] or '없음'}"
        )
    return "\n\n".join(rows)

# =============================
# Output templating (heuristic)
# =============================
_CRIMINAL_HINTS = ("형사","고소","고발","벌금","기소","수사","압수수색","사기","폭행","절도","음주","약취","보이스피싱")
_CIVIL_HINTS    = ("민사","손해배상","채무","계약","임대차","유치권","가압류","가처분","소송가액","지연손해금","불법행위")
_ADMIN_LABOR    = ("행정심판","과징금","과태료","허가","인가","취소처분","해임","징계","해고","근로","연차","퇴직금","산재")

def choose_output_template(q: str) -> str:
    t = (q or "").lower()
    has = lambda ks: any(k.lower() in t for k in ks)
    if has(_CRIMINAL_HINTS):
        return """[출력 서식 강제]
## 1) 사건 개요(형사)
## 2) 적용/관련 법령
## 3) 쟁점과 해석(피의자/피고인 관점 포함)
## 4) 절차·증거·유의사항
## 5) 참고 자료
> **유의**: 본 답변은 참고용입니다. 최종 효력은 관보·공포문 및 법제처 고시·공시 기준.
"""
    if has(_CIVIL_HINTS):
        return """[출력 서식 강제]
## 1) 사건 개요(민사)
## 2) 적용/관련 법령
## 3) 쟁점과 해석(원고/피고 관점)
## 4) 절차·증거·전략
## 5) 참고 자료
> **유의**: 본 답변은 참고용입니다. 최종 효력은 관보·공포문 및 법제처 고시·공시 기준.
"""
    if has(_ADMIN_LABOR):
        return """[출력 서식 강제]
## 1) 사안 개요(노무/행정)
## 2) 적용/관련 법령
## 3) 쟁점과 해석(각 당사자 관점)
## 4) 절차·구제수단
## 5) 참고 자료
> **유의**: 본 답변은 참고용입니다. 최종 효력은 관보·공포문 및 법제처 고시·공시 기준.
"""
    return """[출력 서식 강제]
## 1) 질문 요약
## 2) 적용/관련 법령
## 3) 해석 및 실무 포인트
## 4) 참고 자료
> **유의**: 본 답변은 참고용입니다. 최종 효력은 관보·공포문 및 법제처 고시·공시 기준.
"""

# =============================
# Model helpers
# =============================
def build_history_messages(max_turns=10):
    sys = {
        "role": "system",
        "content": (
            "당신은 대한민국의 변호사이자 법률 전문가입니다. "
            "답변은 실제 변호사 자문서처럼 **체계적·조문/판례 근거 중심**으로 작성합니다. "
            "형사·민사·행정·노무 사건에서 각 당사자 관점(원고/피고, 피의자/검사)을 균형 있게 제시하세요.\n\n"
            "### 답변 지침\n"
            "1) 항상 **한국어 마크다운**으로 작성.\n"
            "2) 구조: 사건/사안 개요 → 적용/관련 법령 → 쟁점 및 해석(근거: 조문·판례·유권해석) "
            "→ 절차·전략(증거·관할·제출서류 등) → 참고 자료.\n"
            "3) 각 섹션은 **2~4문장 이상**으로 구체적으로 기술(불필요한 수사는 금지, 핵심만).\n"
            "4) 법령 표기는 **정식 명칭+조문 번호**로 병기.\n"
            "5) 판례는 **법원·사건번호·선고일**을 함께 표기.\n"
            "6) 링크는 반드시 **www.law.go.kr** 등 공식 출처만 사용.\n"
            "7) 말미에 다음 2문구를 넣는다: 출처 고지 및 참고용 고지.\n"
        ),
    }
    msgs = [sys]
    history = st.session_state.messages[-max_turns*2:]
    msgs.extend({"role": m["role"], "content": m["content"]} for m in history)
    return msgs

def stream_chat_completion(messages, temperature=0.7, max_tokens=1200):
    stream = client.chat.completions.create(
        model=AZURE["deployment"], messages=messages,
        temperature=temperature, max_tokens=max_tokens, stream=True,
    )
    for chunk in stream:
        try:
            c = chunk.choices[0]
            if getattr(c, "finish_reason", None): break
            d = getattr(c, "delta", None)
            txt = getattr(d, "content", None) if d else None
            if txt: yield txt
        except Exception:
            continue

# =============================
# Sidebar: 링크 생성기 (무인증)
# =============================
with st.sidebar:
    st.header("🔗 링크 생성기 (무인증)")
    DEFAULTS = {
        "법령명": "민법",
        "법령_공포번호": "",
        "법령_공포일자": "",
        "법령_시행일자": "",
        "행정규칙명": "수입통관사무처리에관한고시",
        "자치법규명": "서울특별시경관조례",
        "조약번호": "2193",
        "조약발효일": "20140701",
        "판례_사건번호": "2010다52349",
        "헌재사건": "2022헌마1312",
        "해석례ID": "313107",
        "용어ID": "3945293",
        "별표파일ID": "110728887",
    }
    target = st.selectbox(
        "대상 선택",
        [
            "법령(한글주소)", "법령(정밀: 공포/시행/공포일자)", "법령(조문/부칙/삼단비교)",
            "행정규칙(한글주소)", "자치법규(한글주소)", "조약(한글주소 또는 번호/발효일자)",
            "판례(대표: 법제처 한글주소 + 전체: 대법원 검색)", "헌재결정례(한글주소)",
            "법령해석례(ID 전용)", "법령용어(ID 전용)", "별표·서식 파일(ID 전용)"
        ], index=0
    )

    url = None; out_kind = None; out_q = ""
    if target == "법령(한글주소)":
        name = st.text_input("법령명", value=DEFAULTS["법령명"])
        if st.button("생성", use_container_width=True):
            url = hangul_by_name("법령", name); out_kind="law"; out_q=name

    elif target == "법령(정밀: 공포/시행/공포일자)":
        name = st.text_input("법령명", value=DEFAULTS["법령명"])
        c1, c2, c3 = st.columns(3)
        with c1: g_no = st.text_input("공포번호", value=DEFAULTS["법령_공포번호"])
        with c2: g_dt = st.text_input("공포일자(YYYYMMDD)", value=DEFAULTS["법령_공포일자"])
        with c3: ef   = st.text_input("시행일자(YYYYMMDD, 선택)", value=DEFAULTS["법령_시행일자"])
        st.caption("예: (08358) / (07428,20050331) / (20060401,07428,20050331)")
        if st.button("생성", use_container_width=True):
            keys = [k for k in [ef, g_no, g_dt] if k] if ef else [k for k in [g_no, g_dt] if k] if (g_dt or g_no) else [g_no]
            url = hangul_law_with_keys(name, keys); out_kind="law"; out_q=name

    elif target == "법령(조문/부칙/삼단비교)":
        name = st.text_input("법령명", value=DEFAULTS["법령명"])
        sub  = st.text_input("하위 경로", value="제3조")
        if st.button("생성", use_container_width=True):
            url = hangul_law_article(name, sub); out_kind="law"; out_q=f"{name} {sub}"

    elif target == "행정규칙(한글주소)":
        name = st.text_input("행정규칙명", value=DEFAULTS["행정규칙명"])
        use_keys = st.checkbox("발령번호/발령일자로 특정", value=False)
        if use_keys:
            c1, c2 = st.columns(2)
            with c1: issue_no = st.text_input("발령번호", value="")
            with c2: issue_dt = st.text_input("발령일자(YYYYMMDD)", value="")
            if st.button("생성", use_container_width=True):
                url = hangul_admrul_with_keys(name, issue_no, issue_dt); out_kind="admrul"; out_q=name
        else:
            if st.button("생성", use_container_width=True):
                url = hangul_by_name("행정규칙", name); out_kind="admrul"; out_q=name

    elif target == "자치법규(한글주소)":
        name = st.text_input("자치법규명", value=DEFAULTS["자치법규명"])
        use_keys = st.checkbox("공포번호/공포일자로 특정", value=False)
        if use_keys:
            c1, c2 = st.columns(2)
            with c1: no = st.text_input("공포번호", value="")
            with c2: dt = st.text_input("공포일자(YYYYMMDD)", value="")
            if st.button("생성", use_container_width=True):
                url = hangul_ordin_with_keys(name, no, dt); out_kind="ordin"; out_q=name
        else:
            if st.button("생성", use_container_width=True):
                url = hangul_by_name("자치법규", name); out_kind="ordin"; out_q=name

    elif target == "조약(한글주소 또는 번호/발효일자)":
        mode = st.radio("방식", ["이름(직접입력)", "번호/발효일자(권장)"], horizontal=True, index=1)
        if mode.startswith("이름"):
            name = st.text_input("조약명", value="한-불 사회보장협정")
            if st.button("생성", use_container_width=True):
                url = hangul_by_name("조약", name); out_kind="trty"; out_q=name
        else:
            c1, c2 = st.columns(2)
            with c1: tno = st.text_input("조약번호", value=DEFAULTS["조약번호"])
            with c2: eff = st.text_input("발효일자(YYYYMMDD)", value=DEFAULTS["조약발효일"])
            if st.button("생성", use_container_width=True):
                url = hangul_trty_with_keys(tno, eff); out_kind="trty"; out_q=tno

    elif target == "판례(대표: 법제처 한글주소 + 전체: 대법원 검색)":
        mode = st.radio("입력 방식", ["사건번호로 만들기(권장)", "사건명 직접 입력"], index=0)
        law_url = None; scourt_url = None
        if mode.startswith("사건번호"):
            cno = st.text_input("사건번호", value=DEFAULTS["판례_사건번호"])
            colA, colB = st.columns(2)
            with colA:  court = st.selectbox("법원", ["대법원"], index=0)
            with colB:  dispo = st.selectbox("선고유형", ["판결", "결정"], index=0)
            if st.button("링크 생성", use_container_width=True):
                name = build_case_name_from_no(cno, court=court, disposition=dispo)
                if not name: st.error("사건번호 형식이 올바르지 않습니다. 예) 2010다52349, 2009도1234")
                else:
                    law_url = hangul_by_name("판례", name); scourt_url = build_scourt_link(cno)
        else:
            name = st.text_input("판례명", value=f"대법원 {DEFAULTS['판례_사건번호']} 판결")
            found_no = extract_case_no(name)
            if st.button("링크 생성", use_container_width=True):
                law_url = hangul_by_name("판례", name)
                if found_no: scourt_url = build_scourt_link(found_no)
        if law_url or scourt_url:
            st.subheader("생성된 링크")
            if law_url:
                st.write("• 법제처 한글주소(대표 판례)")
                present_url_with_fallback(law_url, kind="prec", q=(cno if mode.startswith("사건번호") else (name or "")))
                st.caption("※ 등록된 대표 판례만 직접 열립니다. 실패 시 아래 대체(대법원) 링크 사용.")
            if scourt_url:
                st.write("• 대법원 종합법률정보(전체 판례 검색)")
                st.code(scourt_url, language="text")
                st.link_button("새 탭에서 열기", scourt_url, use_container_width=True)
                copy_url_button(scourt_url, key=str(abs(hash(scourt_url))), label="대법원 링크 복사")

    elif target == "헌재결정례(한글주소)":
        name_or_no = st.text_input("사건명 또는 사건번호", value=DEFAULTS["헌재사건"])
        if st.button("생성", use_container_width=True):
            url = hangul_by_name("헌재결정례", name_or_no); out_kind="cc"; out_q=name_or_no

    elif target == "법령해석례(ID 전용)":
        expc_id = st.text_input("해석례 ID(expcSeq)", value=DEFAULTS["해석례ID"])
        if st.button("생성", use_container_width=True):
            url = expc_public_by_id(expc_id); out_kind="expc"; out_q=expc_id

    elif target == "법령용어(ID 전용)":
        trm = st.text_input("용어 ID(trmSeqs)", value=DEFAULTS["용어ID"])
        if st.button("생성", use_container_width=True):
            url = lstrm_public_by_id(trm); out_kind="term"; out_q=trm

    elif target == "별표·서식 파일(ID 전용)":
        fl = st.text_input("파일 시퀀스(flSeq)", value=DEFAULTS["별표파일ID"])
        if st.button("생성", use_container_width=True):
            url = licbyl_file_download(fl); out_kind="file"; out_q=fl

    if url:
        st.success("생성된 링크")
        present_url_with_fallback(url, kind=(out_kind or "law"), q=(out_q or ""))
        st.caption("⚠️ 한글주소는 ‘정확한 명칭’이 필요합니다. 괄호 식별자(공포번호·일자 등) 사용 권장.")

# =============================
# Chat flow
# =============================
# 1) ChatBar는 '파일 맨 끝'에서 호출 → 여기선 사용자 입력만 읽음
submitted, typed_text, files = False, "", []

# 2) (다음 rerun까지) 방금 입력된 메시지 먼저 저장
user_q = st.session_state.pop("_pending_user_q", None)  # ChatBar에서 전달 예정
if user_q:
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

# 3) 히스토리 정방향 렌더
with st.container():
    for i, m in enumerate(st.session_state.messages):
        with st.chat_message(m["role"]):
            if m["role"] == "assistant":
                render_bubble_with_copy(m["content"], key=f"past-{i}")
                if m.get("law"):
                    with st.expander("📋 이 턴에서 참고한 법령 요약"):
                        for j, law in enumerate(m["law"], 1):
                            st.write(f"**{j}. {law['법령명']}** ({law['법령구분명']})  | 시행 {law['시행일자']}  | 공포 {law['공포일자']}")
                            if law.get("법령상세링크"):
                                st.write(f"- 링크: {law['법령상세링크']}")
            else:
                st.markdown(m["content"])

# 4) 방금 입력이 있었다면 맨 아래에서 스트리밍
if user_q:
    # MOLEG 검색
    with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
        law_data, used_endpoint, err = search_law_data(user_q, num_rows=st.session_state.settings["num_rows"])
    if used_endpoint: st.caption(f"법제처 API endpoint: `{used_endpoint}`")
    if err: st.warning(err)
    law_ctx = format_law_context(law_data)
    report_ctx = ""  # 파일 컨텍스트를 붙일 땐 여기 추가

    template_block = choose_output_template(user_q)
    model_messages = build_history_messages(max_turns=10) + [{
        "role": "user",
        "content": f"""사용자 질문: {user_q}

관련 법령 정보(분석):
{law_ctx}

[운영 지침]
- 답변에 법령명·공포/시행일·소관부처 등 메타데이터 포함.
- 링크는 반드시 www.law.go.kr 사용.
- 말미에 출처 표기 + 참고용 고지.
{template_block}
"""
    }]

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_text, buffer = "", ""
        try:
            placeholder.markdown("_답변 생성 중입니다._")
            if client is None:
                full_text = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + law_ctx + (("\n\n" + report_ctx) if report_ctx else "")
                placeholder.markdown(_normalize_text(full_text))
            else:
                for piece in stream_chat_completion(model_messages, temperature=0.7, max_tokens=1200):
                    buffer += piece
                    if len(buffer) >= 200:
                        full_text += buffer; buffer = ""
                        placeholder.markdown(_normalize_text(full_text[-1500:]))
                if buffer:
                    full_text += buffer
                    placeholder.markdown(_normalize_text(full_text))
        except Exception as e:
            full_text = f"**오류**: {e}\n\n{law_ctx}"
            placeholder.markdown(_normalize_text(full_text))

        placeholder.empty()
        final_text = _normalize_text(full_text)
        render_bubble_with_copy(final_text, key=f"ans-{datetime.now().timestamp()}")

    st.session_state.messages.append({"role": "assistant", "content": final_text, "law": law_data, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

# =============================
# ChatBar (맨 아래 고정) — 여기서만 한 번 호출
# =============================
submitted, typed_text, files = chatbar(
    placeholder="법령에 대한 질문을 입력하거나, 관련 문서를 첨부해서 문의해 보세요…",
    accept=["pdf", "docx", "txt"], max_files=5, max_size_mb=15, key_prefix="lawchat",
)

# 제출 즉시 messages에 넣지 않고, 다음 rerun에서 반영
if submitted:
    st.session_state["_pending_user_q"] = (typed_text or "").strip()

# (선택) 아주 작은 바닥 여백
st.markdown('<div style="height: 8px"></div>', unsafe_allow_html=True)
