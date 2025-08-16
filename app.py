# app.py — Chat-bubble + Copy (button below) FINAL
# (Sidebar: No-Autocomplete, 판례 = 법제처 한글주소(대표) + 대법원 종합법률정보(전체))
import time, json, html, re
from datetime import datetime
import urllib.parse as up
import xml.etree.ElementTree as ET

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
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container{max-width:1020px;margin:0 auto;}
  .stChatInput{max-width:1020px;margin-left:auto;margin-right:auto;}
  .header{
    text-align:center;padding:1rem;border-radius:12px;
    background:linear-gradient(135deg,#8b5cf6,#a78bfa);color:#fff;margin:0 0 1rem 0
  }
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
  .chat-bubble p, .chat-bubble li, .chat-bubble blockquote{ margin:0 0 8px 0; }
  .chat-bubble blockquote{ padding-left:12px;border-left:3px solid rgba(255,255,255,.2); }
  [data-theme="light"] .chat-bubble{
    --bubble-bg:#ffffff; --bubble-fg:#222222;
    box-shadow:0 1px 8px rgba(0,0,0,.06);
  }
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
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in s.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    merged, i = [], 0
    num_pat = re.compile(r'^\s*((\d+)|([IVXLC]+)|([ivxlc]+))\s*[\.\)]\s*$')
    while i < len(lines):
        cur = lines[i]
        m = num_pat.match(cur)
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                number = (m.group(2) or m.group(3) or m.group(4)).upper()
                title = lines[j].lstrip()
                merged.append(f"{number}. {title}")
                i = j + 1
                continue
        merged.append(cur); i += 1
    out, prev_blank = [], False
    for ln in merged:
        if ln.strip() == "":
            if not prev_blank: out.append("")
            prev_blank = True
        else:
            prev_blank = False; out.append(ln)
    return "\n".join(out)

# =============================
# Bubble Renderer (button below)
# =============================
def render_bubble_with_copy(message: str, key: str):
    message = _normalize_text(message)
    safe_html = html.escape(message)
    safe_raw_json = json.dumps(message)
    st.markdown(f'<div class="chat-bubble" id="bubble-{key}">{safe_html}</div>', unsafe_allow_html=True)
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
        st.warning("Azure OpenAI 설정이 없으므로 기본 안내만 제공합니다.")
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
# Session
# =============================
if "messages" not in st.session_state: st.session_state.messages = []
if "settings" not in st.session_state: st.session_state.settings = {}
st.session_state.settings["num_rows"] = 5
st.session_state.settings["include_search"] = True
st.session_state.settings["safe_mode"] = False

# =============================
# MOLEG API (Law Search)
# =============================
@st.cache_data(show_spinner=False, ttl=300)
def search_law_data(query: str, num_rows: int = 5):
    if not LAW_API_KEY:
        return [], None, "LAW_API_KEY 미설정"
    params = {
        "serviceKey": up.quote_plus(LAW_API_KEY),
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
# No-Auth Public Link Builders (웹페이지용)
# =============================
_HBASE = "https://www.law.go.kr"

def _henc(s: str) -> str:
    return up.quote((s or "").strip())

def hangul_by_name(domain: str, name: str) -> str:
    return f"{_HBASE}/{_henc(domain)}/{_henc(name)}"

def hangul_law_with_keys(name: str, keys):
    body = ",".join(_henc(k) for k in keys if k)
    return f"{_HBASE}/법령/{_henc(name)}/({body})"

def hangul_law_article(name: str, subpath: str) -> str:
    return f"{_HBASE}/법령/{_henc(name)}/{_henc(subpath)}"

def hangul_admrul_with_keys(name: str, issue_no: str, issue_date: str) -> str:
    return f"{_HBASE}/행정규칙/{_henc(name)}/({_henc(issue_no)},{_henc(issue_date)})"

def hangul_ordin_with_keys(name: str, no: str, date: str) -> str:
    return f"{_HBASE}/자치법규/{_henc(name)}/({_henc(no)},{_henc(date)})"

def hangul_trty_with_keys(no: str, eff_date: str) -> str:
    return f"{_HBASE}/조약/({_henc(no)},{_henc(eff_date)})"

def expc_public_by_id(expc_id: str) -> str:
    return f"https://www.law.go.kr/LSW/expcInfoP.do?expcSeq={up.quote(expc_id)}"

def lstrm_public_by_id(trm_seqs: str) -> str:
    return f"https://www.law.go.kr/LSW/lsTrmInfoR.do?trmSeqs={up.quote(trm_seqs)}"

def licbyl_file_download(fl_seq: str) -> str:
    return f"https://www.law.go.kr/LSW/flDownload.do?flSeq={up.quote(fl_seq)}"

# =============================
# 판례: 사건번호 유효성 + 이름 생성 + Scourt 링크
# =============================
_CASE_NO_RE = re.compile(r'(19|20)\d{2}[가-힣]{1,3}\d{1,6}')

def extract_case_no(text: str) -> str | None:
    if not text: return None
    m = _CASE_NO_RE.search(text.replace(" ", ""))
    return m.group(0) if m else None

def validate_case_no(case_no: str) -> bool:
    case_no = (case_no or "").replace(" ", "")
    return bool(_CASE_NO_RE.fullmatch(case_no))

def build_case_name_from_no(case_no: str, court: str = "대법원", disposition: str = "판결") -> str | None:
    case_no = (case_no or "").replace(" ", "")
    if not validate_case_no(case_no):
        return None
    return f"{court} {case_no} {disposition}"

def build_scourt_link(case_no: str) -> str:
    # 대법원 종합법률정보 판례 검색: 사건번호 파라미터
    return f"https://glaw.scourt.go.kr/wsjo/panre/sjo050.do?saNo={up.quote(case_no)}"

def copy_url_button(url: str, key: str, label: str = "링크 복사"):
    if not url: return
    safe = json.dumps(url)
    components.html(f"""
      <div style="display:flex;gap:8px;align-items:center;margin-top:6px">
        <button id="copy-url-{key}" style="padding:6px 10px;border:1px solid #ddd;border-radius:8px;cursor:pointer">
          {label}
        </button>
        <span id="copied-{key}" style="font-size:12px;color:var(--text-color,#888)"></span>
      </div>
      <script>
        (function(){{
          const btn = document.getElementById("copy-url-{key}");
          const msg = document.getElementById("copied-{key}");
          if(!btn) return;
          btn.addEventListener("click", async () => {{
            try {{
              await navigator.clipboard.writeText({safe});
              msg.textContent = "복사됨!";
              setTimeout(()=>msg.textContent="", 1200);
            }} catch(e) {{
              msg.textContent = "복사 실패";
            }}
          }});
        }})();
      </script>
    """, height=40)

# =============================
# Sidebar: 링크 생성기 (무인증)
# =============================
# =============================
# Sidebar: 링크 생성기 (무인증, 기본값=실제 동작 예시)
# =============================
with st.sidebar:
    st.header("🔗 링크 생성기 (무인증)")

    # ✅ 실제로 열리는 기본 예시들
    DEFAULTS = {
        "법령명": "개인정보보호법",                          # https://www.law.go.kr/법령/개인정보보호법
        "법령_공포번호": "",                                # 비워둬도 '법령명'만으로 동작
        "법령_공포일자": "",
        "법령_시행일자": "",
        "행정규칙명": "수입통관사무처리에관한고시",         # https://www.law.go.kr/행정규칙/수입통관사무처리에관한고시
        "자치법규명": "서울특별시경관조례",                 # https://www.law.go.kr/자치법규/서울특별시경관조례
        "조약번호": "2193",                                 # https://www.law.go.kr/조약/(2193,20140701)
        "조약발효일": "20140701",
        "판례_사건번호": "2010다52349",                     # 대법원 검색은 항상 동작
        "헌재사건": "2022헌마1312",                         # https://www.law.go.kr/헌재결정례/2022헌마1312
        "해석례ID": "313107",                               # https://www.law.go.kr/LSW/expcInfoP.do?expcSeq=313107
        "용어ID": "3945293",                                # https://www.law.go.kr/LSW/lsTrmInfoR.do?trmSeqs=3945293
        "별표파일ID": "110728887",                          # https://www.law.go.kr/LSW/flDownload.do?flSeq=110728887
    }

    target = st.selectbox(
        "대상 선택",
        [
            "법령(한글주소)", "법령(정밀: 공포/시행/공포일자)", "법령(조문/부칙/삼단비교)",
            "행정규칙(한글주소)", "자치법규(한글주소)", "조약(한글주소 또는 번호/발효일자)",
            "판례(대표: 법제처 한글주소 + 전체: 대법원 검색)", "헌재결정례(한글주소)",
            "법령해석례(ID 전용)", "법령용어(ID 전용)", "별표·서식 파일(ID 전용)"
        ],
        index=0
    )

    url = None

    # ——— 한글주소 계열 ———
    if target == "법령(한글주소)":
        name = st.text_input("법령명", value=DEFAULTS["법령명"])
        if st.button("생성", use_container_width=True):
            url = hangul_by_name("법령", name)

    elif target == "법령(정밀: 공포/시행/공포일자)":
        name = st.text_input("법령명", value=DEFAULTS["법령명"])
        c1, c2, c3 = st.columns(3)
        with c1: g_no = st.text_input("공포번호", value=DEFAULTS["법령_공포번호"])
        with c2: g_dt = st.text_input("공포일자(YYYYMMDD)", value=DEFAULTS["법령_공포일자"])
        with c3: ef   = st.text_input("시행일자(YYYYMMDD, 선택)", value=DEFAULTS["법령_시행일자"])
        st.caption("예시: (08358) / (07428,20050331) / (20060401,07428,20050331)")
        if st.button("생성", use_container_width=True):
            keys = [k for k in [ef, g_no, g_dt] if k] if ef else [k for k in [g_no, g_dt] if k] if (g_dt or g_no) else [g_no]
            url = hangul_law_with_keys(name, keys)

    elif target == "법령(조문/부칙/삼단비교)":
        name = st.text_input("법령명", value=DEFAULTS["법령명"])
        sub  = st.text_input("하위 경로", value="제3조")  # 바로 열리는 조문 예시
        if st.button("생성", use_container_width=True):
            url = hangul_law_article(name, sub)

    elif target == "행정규칙(한글주소)":
        name = st.text_input("행정규칙명", value=DEFAULTS["행정규칙명"])
        use_keys = st.checkbox("발령번호/발령일자로 특정", value=False)
        if use_keys:
            c1, c2 = st.columns(2)
            with c1: issue_no = st.text_input("발령번호", value="")
            with c2: issue_dt = st.text_input("발령일자(YYYYMMDD)", value="")
            if st.button("생성", use_container_width=True):
                url = hangul_admrul_with_keys(name, issue_no, issue_dt)
        else:
            if st.button("생성", use_container_width=True):
                url = hangul_by_name("행정규칙", name)

    elif target == "자치법규(한글주소)":
        name = st.text_input("자치법규명", value=DEFAULTS["자치법규명"])
        use_keys = st.checkbox("공포번호/공포일자로 특정", value=False)
        if use_keys:
            c1, c2 = st.columns(2)
            with c1: no = st.text_input("공포번호", value="")
            with c2: dt = st.text_input("공포일자(YYYYMMDD)", value="")
            if st.button("생성", use_container_width=True):
                url = hangul_ordin_with_keys(name, no, dt)
        else:
            if st.button("생성", use_container_width=True):
                url = hangul_by_name("자치법규", name)

    elif target == "조약(한글주소 또는 번호/발효일자)":
        mode = st.radio("방식", ["이름(직접입력)", "번호/발효일자(권장)"], horizontal=True, index=1)
        if mode.startswith("이름"):
            name = st.text_input("조약명", value="한-불 사회보장협정")  # 예시(이름은 사이트마다 표기가 달라 실패할 수 있음)
            if st.button("생성", use_container_width=True):
                url = hangul_by_name("조약", name)
        else:
            c1, c2 = st.columns(2)
            with c1: tno = st.text_input("조약번호", value=DEFAULTS["조약번호"])
            with c2: eff = st.text_input("발효일자(YYYYMMDD)", value=DEFAULTS["조약발효일"])
            if st.button("생성", use_container_width=True):
                url = hangul_trty_with_keys(tno, eff)

    elif target == "판례(대표: 법제처 한글주소 + 전체: 대법원 검색)":
        mode = st.radio("입력 방식", ["사건번호로 만들기(권장)", "사건명 직접 입력"], horizontal=False, index=0)

        law_url = None
        scourt_url = None

        if mode.startswith("사건번호"):
            cno = st.text_input("사건번호", value=DEFAULTS["판례_사건번호"])
            colA, colB = st.columns(2)
            with colA:  court = st.selectbox("법원", ["대법원"], index=0)
            with colB:  dispo = st.selectbox("선고유형", ["판결", "결정"], index=0)
            if st.button("생성", use_container_width=True):
                name = build_case_name_from_no(cno, court=court, disposition=dispo)
                if not name:
                    st.error("사건번호 형식이 올바르지 않습니다. 예) 2010다52349, 2009도1234")
                else:
                    law_url = hangul_by_name("판례", name)   # 대표 판례만 열림
                    scourt_url = build_scourt_link(cno)       # 대법원 검색(항상 동작)
        else:
            name = st.text_input("판례명", value=f"대법원 {DEFAULTS['판례_사건번호']} 판결")
            found_no = extract_case_no(name)
            if st.button("생성", use_container_width=True):
                law_url = hangul_by_name("판례", name)
                if found_no:
                    scourt_url = build_scourt_link(found_no)

        if law_url or scourt_url:
            st.subheader("생성된 링크")
            if law_url:
                st.write("• 법제처 한글주소(대표 판례)")
                st.code(law_url, language="text")
                st.link_button("새 탭에서 열기", law_url, use_container_width=True)
                copy_url_button(law_url, key=str(abs(hash(law_url))), label="법제처 링크 복사")
                st.caption("※ 등록된 대표 판례만 열립니다. 404가 뜨면 아래 대법원 검색 링크를 이용하세요.")
            if scourt_url:
                st.write("• 대법원 종합법률정보(전체 판례 검색)")
                st.code(scourt_url, language="text")
                st.link_button("새 탭에서 열기", scourt_url, use_container_width=True)
                copy_url_button(scourt_url, key=str(abs(hash(scourt_url))), label="대법원 링크 복사")

    elif target == "헌재결정례(한글주소)":
        name_or_no = st.text_input("사건명 또는 사건번호", value=DEFAULTS["헌재사건"])
        if st.button("생성", use_container_width=True):
            url = hangul_by_name("헌재결정례", name_or_no)

    # ——— 예외 3종: ID 전용 무인증 URL ———
    elif target == "법령해석례(ID 전용)":
        expc_id = st.text_input("해석례 ID(expcSeq)", value=DEFAULTS["해석례ID"])
        if st.button("생성", use_container_width=True):
            url = expc_public_by_id(expc_id)

    elif target == "법령용어(ID 전용)":
        trm = st.text_input("용어 ID(trmSeqs)", value=DEFAULTS["용어ID"])
        if st.button("생성", use_container_width=True):
            url = lstrm_public_by_id(trm)

    elif target == "별표·서식 파일(ID 전용)":
        fl = st.text_input("파일 시퀀스(flSeq)", value=DEFAULTS["별표파일ID"])
        if st.button("생성", use_container_width=True):
            url = licbyl_file_download(fl)

    # 단일 URL 생성 케이스 출력
    if url:
        st.success("생성된 링크")
        st.code(url, language="text")
        st.link_button("새 탭에서 열기", url, use_container_width=True)
        copy_url_button(url, key=str(abs(hash(url))))
        st.caption("⚠️ 한글주소는 ‘정확한 명칭’이 필요합니다. 확실한 식별이 필요하면 괄호 식별자(공포번호·일자 등)를 사용하세요.")

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
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
    with st.chat_message("user"): st.markdown(user_q)

    with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
        law_data, used_endpoint, err = search_law_data(user_q, num_rows=st.session_state.settings["num_rows"])
    if used_endpoint: st.caption(f"법제처 API endpoint: `{used_endpoint}`")
    if err: st.warning(err)
    law_ctx = format_law_context(law_data)

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
- 법령 범위를 벗어난 임의 해석.
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

    if client is None:
        final_text = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + law_ctx
        with st.chat_message("assistant"):
            render_bubble_with_copy(final_text, key=f"ans-{ts}")
    else:
        with st.chat_message("assistant"):
            placeholder = st.empty(); full_text, buffer = "", ""
            try:
                placeholder.markdown('<div class="chat-bubble"><span class="typing-indicator"></span> 답변 생성 중.</div>', unsafe_allow_html=True)
                for piece in stream_chat_completion(model_messages, temperature=0.7, max_tokens=1000):
                    buffer += piece
                    if len(buffer) >= 200:
                        full_text += buffer; buffer = ""
                        preview = html.escape(_normalize_text(full_text[-1500:]))
                        placeholder.markdown(f'<div class="chat-bubble">{preview}</div>', unsafe_allow_html=True)
                        time.sleep(0.05)
                if buffer:
                    full_text += buffer
                    preview = html.escape(_normalize_text(full_text))
                    placeholder.markdown(f'<div class="chat-bubble">{preview}</div>', unsafe_allow_html=True)
            except Exception as e:
                full_text = f"답변 생성 중 오류가 발생했습니다: {e}\n\n{law_ctx}"
                placeholder.markdown(f'<div class="chat-bubble">{html.escape(_normalize_text(full_text))}</div>', unsafe_allow_html=True)
        placeholder.empty()
        final_text = _normalize_text(full_text)
        with st.chat_message("assistant"):
            render_bubble_with_copy(final_text, key=f"ans-{ts}")

    st.session_state.messages.append({
        "role": "assistant", "content": final_text, "law": law_data, "ts": ts
    })
