# app.py — Chat-bubble + Copy (button below, no overlay) FINAL (No-Auth Sidebar Links)
import time, json, html, re, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI

# =============================
# Page & Global Styles
# =============================
st.set_page_config(
    page_title="법제처 AI 챗봇",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",  # ← ALWAYS show sidebar (changed)
)

st.markdown("""
<style>
  /* ❌ 기존: 사이드바/토글 숨김 → 주석 처리
  [data-testid="stSidebar"]{display:none!important;}
  [data-testid="collapsedControl"]{display:none!important;}
  */

  /* 폭 살짝 확대 */
  .block-container{max-width:1020px;margin:0 auto;}
  .stChatInput{max-width:1020px;margin-left:auto;margin-right:auto;}

  .header{
    text-align:center;padding:1rem;border-radius:12px;
    background:linear-gradient(135deg,#8b5cf6,#a78bfa);color:#fff;margin:0 0 1rem 0
  }

  /* 말풍선(가독성 압축) */
  .chat-bubble{
    background:var(--bubble-bg,#1f1f1f);
    color:var(--bubble-fg,#f5f5f5);
    border-radius:14px;
    padding:14px 16px;
    font-size:16px!important;
    line-height:1.6!important;
    white-space:pre-wrap;
    word-break:break-word;
    box-shadow:0 1px 8px rgba(0,0,0,.12);
  }
  /* 문단/목록/인용 마진 축소 */
  .chat-bubble p,
  .chat-bubble li,
  .chat-bubble blockquote{ margin:0 0 8px 0; }
  .chat-bubble blockquote{
    padding-left:12px;border-left:3px solid rgba(255,255,255,.2);
  }

  [data-theme="light"] .chat-bubble{
    --bubble-bg:#ffffff; --bubble-fg:#222222;
    box-shadow:0 1px 8px rgba(0,0,0,.06);
  }

  /* 말풍선 아래 줄의 복사 버튼 */
  .copy-row{ display:flex;justify-content:flex-end;margin:6px 4px 0 0; }
  .copy-btn{
    display:inline-flex;align-items:center;gap:6px;
    padding:6px 10px;border:1px solid rgba(255,255,255,.15);
    border-radius:10px;background:rgba(0,0,0,.25);
    backdrop-filter:blur(4px);cursor:pointer;font-size:12px;color:inherit;
  }
  [data-theme="light"] .copy-btn{background:rgba(255,255,255,.9);border-color:#ddd;}
  .copy-btn svg{pointer-events:none}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="header"><h2>⚖️ 법제처 인공지능 법률 상담 플랫폼</h2>'
    '<div>법제처 공식 데이터를 AI가 분석해 답변을 제공합니다</div>'
    '<div>당신의 문제를 입력하면 법률 자문서를 출력해 줍니다. 당신의 문제를 입력해 보세요</div></div>',
    unsafe_allow_html=True,
)

# =============================
# Text Normalization
# =============================
def _normalize_text(s: str) -> str:
    """
    - 개행 표준화
    - 앞/뒤 빈 줄 제거
    - 연속 빈 줄 최대 1개 허용
    - '번호만 있는 줄'을 다음 줄 제목과 합치기
      (1. / 1) / I. / iii) 등 폭넓게 처리)
    """
    # 개행 표준화
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # 라인 끝 공백 제거 + 앞/뒤 빈 줄 제거
    lines = [ln.rstrip() for ln in s.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    # 번호줄 + 제목 병합
    merged = []
    i = 0
    num_pat = re.compile(r'^\s*((\d+)|([IVXLC]+)|([ivxlc]+))\s*[\.\)]\s*$')  # 1. / 1) / III. / iii)
    while i < len(lines):
        cur = lines[i]
        m = num_pat.match(cur)
        if m:
            j = i + 1
            # 번호 뒤의 연속 빈 줄 건너뛰고 실제 텍스트 줄 찾기
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                number = (m.group(2) or m.group(3) or m.group(4)).upper()
                title = lines[j].lstrip()
                merged.append(f"{number}. {title}")
                i = j + 1
                continue
        merged.append(cur)
        i += 1

    # 연속 빈 줄 최대 1개 허용
    out, prev_blank = [], False
    for ln in merged:
        if ln.strip() == "":
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            prev_blank = False
            out.append(ln)

    return "\n".join(out)

# =============================
# Bubble Renderer (button below)
# =============================
def render_bubble_with_copy(message: str, key: str):
    """본문은 escape하여 안전하게 렌더, 복사 버튼은 '아래 줄'에 항상 보이게."""
    message = _normalize_text(message)
    safe_html = html.escape(message)     # 화면용
    safe_raw_json = json.dumps(message)  # 클립보드용

    st.markdown(f'<div class="chat-bubble" id="bubble-{key}">{safe_html}</div>',
                unsafe_allow_html=True)

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
            const old = btn.innerHTML;
            btn.innerHTML = "복사됨!";
            setTimeout(()=>btn.innerHTML = old, 1200);
          }} catch(e) {{
            alert("복사 실패: " + e);
          }}
        }});
      }})();
    </script>
    """, height=40)

# =============================
# Secrets
# =============================
def load_secrets():
    law_key = None; azure = None
    try:
        law_key = st.secrets["LAW_API_KEY"]
    except Exception:
        st.error("`LAW_API_KEY`가 없습니다. Streamlit → App settings → Secrets에 추가하세요.")
    try:
        azure = st.secrets["azure_openai"]
        _ = azure["api_key"]; _ = azure["endpoint"]; _ = azure["deployment"]; _ = azure["api_version"]
    except Exception:
        st.error("[azure_openai] 섹션(api_key, endpoint, deployment, api_version) 누락")
        azure = None
    return law_key, azure

LAW_API_KEY, AZURE = load_secrets()

# =============================
# Azure OpenAI
# =============================
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
# Session (Hardcoded Options)
# =============================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "settings" not in st.session_state:
    st.session_state.settings = {}
st.session_state.settings["num_rows"] = 5
st.session_state.settings["include_search"] = True   # 항상 켬
st.session_state.settings["safe_mode"] = False       # 스트리밍 사용

# =============================
# MOLEG API (Law Search)
# =============================
@st.cache_data(show_spinner=False, ttl=300)
def search_law_data(query: str, num_rows: int = 5):
    if not LAW_API_KEY:
        return [], None, "LAW_API_KEY 미설정"
    params = {
        "serviceKey": urllib.parse.quote_plus(LAW_API_KEY),
        "target": "law",
        "query": query,
        "numOfRows": max(1, min(10, int(num_rows))),
        "pageNo": 1,
    }
    endpoints = [
        "https://apis.data.go.kr/1170000/law/lawSearchList.do",
        "http://apis.data.go.kr/1170000/law/lawSearchList.do",
    ]
    last_err = None
    for url in endpoints:
        try:
            res = requests.get(url, params=params, timeout=15)
            res.raise_for_status()
            root = ET.fromstring(res.text)
            laws = []
            for law in root.findall(".//law"):
                laws.append({
                    "법령명": law.findtext("법령명한글", default=""),
                    "법령약칭명": law.findtext("법령약칭명", default=""),
                    "소관부처명": law.findtext("소관부처명", default=""),
                    "법령구분명": law.findtext("법령구분명", default=""),
                    "시행일자": law.findtext("시행일자", default=""),
                    "공포일자": law.findtext("공포일자", default=""),
                    "법령상세링크": law.findtext("법령상세링크", default=""),
                })
            return laws, url, None
        except Exception as e:
            last_err = e
            continue
    return [], None, f"법제처 API 연결 실패: {last_err}"

def format_law_context(law_data):
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
# ❗ No-Auth Public Link Builders (웹페이지용)
# =============================
# =============================
# law.go.kr 한글주소(Hangul Address) 빌더 (무인증)
# 규칙 요약:
#  - 기본형: https://www.law.go.kr/<분야>/<이름>
#  - 법령 정밀 식별: /법령/이름/(공포번호) 또는 (공포번호,공포일자) 또는 (시행일자,공포번호,공포일자)
#  - 조문/부칙/삼단비교 등: /법령/이름/제X조, /법령/이름/부칙, /법령/이름/삼단비교
#  - 행정규칙: /행정규칙/이름/(발령번호,발령일자)
#  - 자치법규: /자치법규/이름/(공포번호,공포일자)
#  - 조약: /조약/(조약번호,발효일자)  ※ 이름 없이 번호+일자만으로도 가능
# =============================
import urllib.parse as _hp

_HBASE = "https://www.law.go.kr"

def _henc(s: str) -> str:
    return _hp.quote((s or "").strip())

def hangul_by_name(domain: str, name: str) -> str:
    """기본형: /<분야>/<이름>"""
    return f"{_HBASE}/{_henc(domain)}/{_henc(name)}"

def hangul_law_with_keys(name: str, keys: list[str]) -> str:
    """법령 정밀 식별: (공포번호) | (공포번호,공포일자) | (시행일자,공포번호,공포일자)"""
    body = ",".join(_henc(k) for k in keys if k)
    return f"{_HBASE}/법령/{_henc(name)}/({body})"

def hangul_law_article(name: str, subpath: str) -> str:
    """조문/부칙/삼단비교 등: /법령/이름/제X조 | /부칙 | /삼단비교"""
    return f"{_HBASE}/법령/{_henc(name)}/{_henc(subpath)}"

def hangul_admrul_with_keys(name: str, issue_no: str, issue_date: str) -> str:
    """행정규칙: /행정규칙/이름/(발령번호,발령일자)"""
    return f"{_HBASE}/행정규칙/{_henc(name)}/({_henc(issue_no)},{_henc(issue_date)})"

def hangul_ordin_with_keys(name: str, no: str, date: str) -> str:
    """자치법규: /자치법규/이름/(공포번호,공포일자)"""
    return f"{_HBASE}/자치법규/{_henc(name)}/({_henc(no)},{_henc(date)})"

def hangul_trty_with_keys(no: str, eff_date: str) -> str:
    """조약: /조약/(조약번호,발효일자)  ※ 이름 없이도 동작"""
    return f"{_HBASE}/조약/({_henc(no)},{_henc(eff_date)})"

def law_public_by_name(kor_name: str) -> str:
    return f"https://www.law.go.kr/법령/{_up.quote(kor_name)}"

def admrul_public_by_name(kor_name: str) -> str:
    return f"https://www.law.go.kr/행정규칙/{_up.quote(kor_name)}"

def ordin_public_by_name(kor_name: str) -> str:
    return f"https://www.law.go.kr/자치법규/{_up.quote(kor_name)}"

def trty_public_by_name(kor_name: str) -> str:
    return f"https://www.law.go.kr/조약/{_up.quote(kor_name)}"

def detc_public_by_name_or_no(case_text: str) -> str:
    return f"https://www.law.go.kr/헌재결정례/{_up.quote(case_text)}"

def expc_public_by_id(expc_id: str) -> str:
    # 법령해석례 일반 페이지(무인증): expcSeq 필요
    return f"https://www.law.go.kr/LSW/expcInfoP.do?expcSeq={_up.quote(expc_id)}"

def lstrm_public_by_id(trm_seqs: str) -> str:
    # 법령용어 일반 페이지(무인증)
    return f"https://www.law.go.kr/LSW/lsTrmInfoR.do?trmSeqs={_up.quote(trm_seqs)}"

def licbyl_file_download(fl_seq: str) -> str:
    # 별표/서식 파일 다운로드(무인증)
    return f"https://www.law.go.kr/LSW/flDownload.do?flSeq={_up.quote(fl_seq)}"


# =============================
# Sidebar: 무인증 링크 생성기
# =============================
# =============================
# Sidebar: 링크 도구
# =============================
with st.sidebar:
    st.header("🔗 링크 도구")

    tab_pub, tab_hangul = st.tabs(["무인증 링크 생성기", "한글주소 빌더"])

    # ————————————————————————————
    # 탭 1) 무인증 링크 생성기 (이전 기능 그대로)
    # ————————————————————————————
    with tab_pub:
        st.caption("사람용 웹페이지 URL만 생성합니다. (DRF/OC 인증 불필요)")

        target = st.selectbox(
            "대상 선택",
            ["법령(law)", "행정규칙(admrul)", "자치법규(ordin)", "조약(trty)",
             "헌재결정례(detc)", "법령해석례(expc: ID 필요)", "법령용어(lstrm: ID 필요)",
             "별표·서식 파일(licbyl: 파일ID 필요)"]
        )

        out_url = None
        if target.startswith("법령("):
            name = st.text_input("법령명", placeholder="예) 개인정보 보호법")
            if st.button("링크 생성", use_container_width=True): out_url = law_public_by_name(name)

        elif target.startswith("행정규칙("):
            name = st.text_input("행정규칙명", placeholder="예) 112종합상황실 운영 및 신고처리 규칙")
            if st.button("링크 생성", use_container_width=True): out_url = admrul_public_by_name(name)

        elif target.startswith("자치법규("):
            name = st.text_input("자치법규명", placeholder="예) 서울특별시 경관 조례")
            if st.button("링크 생성", use_container_width=True): out_url = ordin_public_by_name(name)

        elif target.startswith("조약("):
            name = st.text_input("조약명", placeholder="예) 대한민국과 ○○국 간의 사회보장협정")
            if st.button("링크 생성", use_container_width=True): out_url = trty_public_by_name(name)

        elif target.startswith("헌재결정례("):
            name_or_no = st.text_input("사건명 또는 사건번호", placeholder="예) 2022헌마1312")
            if st.button("링크 생성", use_container_width=True): out_url = detc_public_by_name_or_no(name_or_no)

        elif target.startswith("법령해석례("):
            expc_id = st.text_input("해석례 ID(expcSeq)", placeholder="예) 313107")
            if st.button("링크 생성", use_container_width=True): out_url = expc_public_by_id(expc_id)

        elif target.startswith("법령용어("):
            trm = st.text_input("용어 ID(trmSeqs)", placeholder="예) 3945293")
            if st.button("링크 생성", use_container_width=True): out_url = lstrm_public_by_id(trm)

        elif target.startswith("별표·서식"):
            fl = st.text_input("파일 시퀀스(flSeq)", placeholder="예) 110728887 (PDF/파일)")
            if st.button("링크 생성", use_container_width=True): out_url = licbyl_file_download(fl)

        if out_url:
            st.success("생성된 링크")
            st.code(out_url, language="text")
            st.link_button("새 탭에서 열기", out_url, use_container_width=True)

    # ————————————————————————————
    # 탭 2) 한글주소 빌더 (새 기능)
    # ————————————————————————————
    with tab_hangul:
        st.caption("한글주소 규칙으로 law.go.kr에 직접 연결합니다. (무인증)")

        h_target = st.selectbox(
            "대상 선택",
            ["법령(기본형)", "법령(정밀 식별: 공포/시행/공포일자)", "법령(조문/부칙/삼단비교)",
             "행정규칙(발령번호,발령일자)", "자치법규(공포번호,공포일자)", "조약(번호,발효일자)",
             "판례(이름 기반)", "헌재결정례(사건명/번호)"],
            index=0
        )

        h_url = None

        if h_target == "법령(기본형)":
            name = st.text_input("법령명", placeholder="예) 자동차관리법")
            if st.button("생성", use_container_width=True) and name.strip():
                h_url = hangul_by_name("법령", name)

        elif h_target == "법령(정밀 식별: 공포/시행/공포일자)":
            name = st.text_input("법령명", placeholder="예) 자동차관리법")
            col1, col2, col3 = st.columns(3)
            with col1: g_no = st.text_input("공포번호", placeholder="예) 08358")
            with col2: g_dt = st.text_input("공포일자(YYYYMMDD)", placeholder="예) 20050331")
            with col3: ef  = st.text_input("시행일자(YYYYMMDD, 선택)", placeholder="예) 20060401")
            st.caption("입력 예: (08358) 또는 (07428,20050331) 또는 (20060401,07428,20050331)")
            if st.button("생성", use_container_width=True) and name.strip():
                keys = [k for k in [ef, g_no, g_dt] if k] if ef else [k for k in [g_no, g_dt] if k] if g_dt or g_no else [g_no]
                h_url = hangul_law_with_keys(name, keys)

        elif h_target == "법령(조문/부칙/삼단비교)":
            name = st.text_input("법령명", placeholder="예) 자동차관리법")
            sub  = st.text_input("하위 경로", placeholder="예) 제3조 / 부칙 / 삼단비교")
            if st.button("생성", use_container_width=True) and name.strip() and sub.strip():
                h_url = hangul_law_article(name, sub)

        elif h_target == "행정규칙(발령번호,발령일자)":
            name = st.text_input("행정규칙명", placeholder="예) 수입통관사무처리에관한고시")
            col1, col2 = st.columns(2)
            with col1: issue_no = st.text_input("발령번호", placeholder="예) 582")
            with col2: issue_dt = st.text_input("발령일자(YYYYMMDD)", placeholder="예) 20210122")
            if st.button("생성", use_container_width=True) and name.strip() and issue_no and issue_dt:
                h_url = hangul_admrul_with_keys(name, issue_no, issue_dt)

        elif h_target == "자치법규(공포번호,공포일자)":
            name = st.text_input("자치법규명", placeholder="예) 서울특별시경관조례")
            col1, col2 = st.columns(2)
            with col1: no = st.text_input("공포번호", placeholder="예) 2120")
            with col2: dt = st.text_input("공포일자(YYYYMMDD)", placeholder="예) 20150102")
            if st.button("생성", use_container_width=True) and name.strip() and no and dt:
                h_url = hangul_ordin_with_keys(name, no, dt)

        elif h_target == "조약(번호,발효일자)":
            col1, col2 = st.columns(2)
            with col1: tno = st.text_input("조약번호", placeholder="예) 2193")
            with col2: eff = st.text_input("발효일자(YYYYMMDD)", placeholder="예) 20140701")
            if st.button("생성", use_container_width=True) and tno and eff:
                h_url = hangul_trty_with_keys(tno, eff)

        elif h_target == "판례(이름 기반)":
            name = st.text_input("판례명", placeholder="예) 대법원 2009도1234 판결")
            if st.button("생성", use_container_width=True) and name.strip():
                h_url = hangul_by_name("판례", name)

        elif h_target == "헌재결정례(사건명/번호)":
            name_or_no = st.text_input("사건명 또는 사건번호", placeholder="예) 2022헌마1312")
            if st.button("생성", use_container_width=True) and name_or_no.strip():
                h_url = hangul_by_name("헌재결정례", name_or_no)

        if h_url:
            st.success("생성된 한글주소")
            st.code(h_url, language="text")
            st.link_button("새 탭에서 열기", h_url, use_container_width=True)
            st.caption("⚠️ 제목이 정확히 일치하지 않으면 404가 날 수 있습니다. (정확명/식별자 권장)")


# =============================
# Model Helpers
# =============================
def build_history_messages(max_turns=10):
    sys = {"role": "system", "content": "당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다."}
    msgs = [sys]
    history = st.session_state.messages[-max_turns*2:]
    for m in history:
        msgs.append({"role": m["role"], "content": m["content"]})
    return msgs

def stream_chat_completion(messages, temperature=0.7, max_tokens=1000):
    stream = client.chat.completions.create(
        model=AZURE["deployment"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        try:
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue
            c = chunk.choices[0]
            if getattr(c, "finish_reason", None):
                break
            d = getattr(c, "delta", None)
            txt = getattr(d, "content", None) if d else None
            if txt:
                yield txt
        except Exception:
            continue

def chat_completion(messages, temperature=0.7, max_tokens=1000):
    resp = client.chat.completions.create(
        model=AZURE["deployment"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    try:
        return resp.choices[0].message.content
    except Exception:
        return ""

# =============================
# Render History (bubble + copy)
# =============================
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

# =============================
# Input & Answer
# =============================
user_q = st.chat_input("법령에 대한 질문을 입력하세요… (Enter로 전송)")

if user_q:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 사용자 메시지
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
    with st.chat_message("user"):
        st.markdown(user_q)

    # 법제처 검색(항상 실행)
    with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
        law_data, used_endpoint, err = search_law_data(user_q, num_rows=st.session_state.settings["num_rows"])
    if used_endpoint: st.caption(f"법제처 API endpoint: `{used_endpoint}`")
    if err: st.warning(err)
    law_ctx = format_law_context(law_data)

    # 프롬프트
    model_messages = build_history_messages(max_turns=10)
    model_messages.append({
        "role": "user",
        "content": f"""사용자 질문: {user_q}

관련 법령 정보(분석):
{law_ctx}

[역할]
당신은 “대한민국 법령정보 챗봇”입니다.
모든 정보는 법제처 국가법령정보센터(www.law.go.kr)의 
“국가법령정보 공유서비스 Open API”를 기반으로 제공합니다.

[제공 범위]
1. 국가 법령(현행) - 법률, 시행령, 시행규칙 등 (law)
2. 행정규칙 - 예규, 고시, 훈령·지침 등 (admrul)
3. 자치법규 - 전국 지자체의 조례·규칙·훈령 (ordin)
4. 조약 - 양자·다자 조약 (trty)
5. 법령 해석례 - 법제처 유권해석 사례 (expc)
6. 헌법재판소 결정례 - 위헌·합헌·각하 등 (detc)
7. 별표·서식 - 법령에 첨부된 별표, 서식 (licbyl)
8. 법령 용어 사전 - 법령 용어·정의 (lstrm)

[운영 지침]
- 질의 의도에 맞는 target을 선택해 조회.
- 답변에 법령명, 공포일자, 시행일자, 소관부처 등 주요 메타데이터 포함.
- 링크는 반드시 “www.law.go.kr” 공식 주소 사용.
- DB는 매일 1회 갱신 → 최신 반영 시차 고지.
- 답변 마지막에 “출처: 법제처 국가법령정보센터” 표기.
- 해석 요청 시 원문 + 법제처 해석례·헌재 결정례 우선 안내.
- 법적 효력은 참고용임을 명시, 최종 판단은 관보·공포문 기준.

[금지]
- 법령 범위 밖 임의 해석.
- 출처 누락·변형.
- 최신성 확인 없는 단정 표현.

[출력 형식]
한국어로 간결하고 이해하기 쉽게 설명.

[응답 예시]
---
**법령명**: 개인정보 보호법  
**공포일자**: 2023-03-14  
**시행일자**: 2023-09-15  
**소관부처**: 행정안전부  
**법령구분**: 법률  
**개요**: 개인정보의 처리 및 보호에 관한 기본 원칙과 책임, 처리 제한, 정보주체의 권리 등을 규정한 법률입니다.  
**주요 내용**:  
1. 개인정보 수집·이용 시 동의 의무  
2. 민감정보 처리 제한  
3. 개인정보 침해 시 손해배상 책임  
4. 개인정보 보호위원회 설치·운영  

**관련 자료**:  
- [법령 전문 보기](https://www.law.go.kr/법령/개인정보보호법)
  (※ 해석례는 사이드바 ▶ 무인증 링크 생성기에서 ID로 생성하여 안내)
> **참고**: 본 내용은 법제처 국가법령정보센터 데이터 기준(매일 1회 갱신)이며, 최신 개정 사항은 관보·공포문을 반드시 확인하세요.  
출처: 법제처 국가법령정보센터
---
"""
    })

    # 스트리밍
    if client is None:
        final_text = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + law_ctx
        with st.chat_message("assistant"):
            render_bubble_with_copy(final_text, key=f"ans-{ts}")
    else:
        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_text, buffer = "", ""
            try:
                placeholder.markdown('<div class="chat-bubble"><span class="typing-indicator"></span> 답변 생성 중.</div>',
                                     unsafe_allow_html=True)
                for piece in stream_chat_completion(model_messages, temperature=0.7, max_tokens=1000):
                    buffer += piece
                    if len(buffer) >= 200:
                        full_text += buffer; buffer = ""
                        preview = html.escape(_normalize_text(full_text[-1500:]))
                        placeholder.markdown(f'<div class="chat-bubble">{preview}</div>',
                                             unsafe_allow_html=True)
                        time.sleep(0.05)
                if buffer:
                    full_text += buffer
                    preview = html.escape(_normalize_text(full_text))
                    placeholder.markdown(f'<div class="chat-bubble">{preview}</div>',
                                         unsafe_allow_html=True)
            except Exception as e:
                full_text = f"답변 생성 중 오류가 발생했습니다: {e}\n\n{law_ctx}"
                placeholder.markdown(f'<div class="chat-bubble">{html.escape(_normalize_text(full_text))}</div>',
                                     unsafe_allow_html=True)

        # 미리보기 지우고 최종 말풍선 1번만 출력
        placeholder.empty()
        final_text = _normalize_text(full_text)
        render_bubble_with_copy(final_text, key=f"ans-{ts}")

    # 히스토리에 저장
    st.session_state.messages.append({
        "role": "assistant", "content": final_text, "law": law_data, "ts": ts
    })
