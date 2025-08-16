# app.py — Pro legal memo mode: router + ranked attachments + 2-pass verify + strict prompt
from __future__ import annotations

import io, os, re, json, time, html, math
from datetime import datetime
import urllib.parse as up
import xml.etree.ElementTree as ET
from collections import Counter

import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI

from chatbar import chatbar
from utils_extract import extract_text_from_pdf, extract_text_from_docx, read_txt, sanitize

# =============================
# Config & Style
# =============================
PAGE_MAX_WIDTH = 1020
BOTTOM_PADDING_PX = 120
KEY_PREFIX = "lawchat"

st.set_page_config(
    page_title="법제처 AI 챗봇",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

if st.session_state.pop("_clear_input", False):
    st.session_state[f"{KEY_PREFIX}-input"] = ""

st.markdown(f"""
<style>
.block-container {{ max-width:{PAGE_MAX_WIDTH}px; margin:0 auto; padding-bottom:{BOTTOM_PADDING_PX}px; }}
.stChatInput {{ max-width:{PAGE_MAX_WIDTH}px; margin-left:auto; margin-right:auto; }}
section.main {{ padding-bottom:0; }}

.header {{
  text-align:center; padding:1rem; border-radius:12px; background:transparent; color:inherit; margin:0 0 1rem 0;
  border: 1px solid rgba(127,127,127,.20);
}}
[data-theme="dark"] .header {{ border-color: rgba(255,255,255,.12); }}

h2, h3 {{ font-size:1.1rem !important; font-weight:600 !important; margin:0.8rem 0 0.4rem; }}
.stMarkdown > div {{
  background:var(--bubble-bg,#1f1f1f); color:var(--bubble-fg,#f5f5f5);
  border-radius:14px; padding:14px 16px; box-shadow:0 1px 8px rgba(0,0,0,.12);
}}
[data-theme="light"] .stMarkdown > div {{ --bubble-bg:#fff; --bubble-fg:#222; box-shadow:0 1px 8px rgba(0,0,0,.06); }}
.stMarkdown ul, .stMarkdown ol {{ margin-left:1.1rem; }}
.stMarkdown blockquote {{ margin:8px 0; padding-left:12px; border-left:3px solid rgba(255,255,255,.25); }}

.copy-row{{ display:flex; justify-content:flex-end; margin:6px 4px 0 0; }}
.copy-btn{{ display:inline-flex; align-items:center; gap:6px; padding:6px 10px; border:1px solid rgba(255,255,255,.15);
  border-radius:10px; background:rgba(0,0,0,.25); backdrop-filter:blur(4px); cursor:pointer; font-size:12px; color:inherit; }}
[data-theme="light"] .copy-btn{{ background:rgba(255,255,255,.9); border-color:#ddd; }}
.copy-btn svg{{ pointer-events:none }}

.pinned-q{{ position: sticky; top: 0; z-index: 900; margin: 8px 0 12px; padding: 10px 14px; border-radius: 12px;
  border: 1px solid rgba(255,255,255,.15); background: rgba(0,0,0,.35); backdrop-filter: blur(6px); }}
[data-theme="light"] .pinned-q{{ background: rgba(255,255,255,.85); border-color:#e5e5e5; }}
.pinned-q .label{{ font-size:12px; opacity:.8; margin-bottom:4px; }}
.pinned-q .text{{ font-weight:600; line-height:1.4; max-height:7.5rem; overflow:auto; }}

:root {{ --msg-max: {PAGE_MAX_WIDTH}px; }}
[data-testid="stChatMessage"] {{ background: transparent !important; border:none !important; box-shadow:none !important; }}
[data-testid="stChatMessage"] .stMarkdown {{
  background: transparent !important; color: inherit !important; border:none !important; box-shadow:none !important; padding:0 !important;
  max-width: {PAGE_MAX_WIDTH}px; margin: 0 auto; box-sizing: border-box;
}}
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

def _esc(s: str) -> str:
    return html.escape(s or "").replace("\n", "<br>")

def render_pinned_question():
    last_q = None
    for m in reversed(st.session_state.get("messages", [])):
        if m.get("role") == "user":
            last_q = m.get("content", "")
            break
    if not last_q: return
    st.markdown(f"""
    <div class="pinned-q">
      <div class="label">최근 질문</div>
      <div class="text">{_esc(last_q)}</div>
    </div>
    """, unsafe_allow_html=True)

# Replace law.go.kr URLs in the answer with official detail links from law_data
def fix_links_with_lawdata(markdown: str, law_data: list[dict]) -> str:
    if not markdown or not law_data: return markdown
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

if "messages" not in st.session_state: st.session_state.messages = []
if "settings" not in st.session_state: st.session_state.settings = {"num_rows": 5, "include_search": True, "safe_mode": False}
if "_last_user_nonce" not in st.session_state: st.session_state["_last_user_nonce"] = None
if "report_ctx" not in st.session_state: st.session_state["report_ctx"] = ""  # 첨부 요약 컨텍스트 저장

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
    last_err = None
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
# Attachment ranking helpers
# =============================
def _split_paragraphs(t: str) -> list[str]:
    paras = [p.strip() for p in (t or "").split("\n\n") if p.strip()]
    flat = []
    for p in paras:
        if len(p) > 1200:
            chunks = re.split(r'(?<=[.!?。…])\s+', p)
            buf = ""
            for c in chunks:
                if len(buf)+len(c) <= 800:
                    buf += (" " if buf else "") + c
                else:
                    flat.append(buf); buf = c
            if buf: flat.append(buf)
        else:
            flat.append(p)
    return flat

def _tokenize_ko(s: str) -> list[str]:
    s = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", s)
    return [w for w in s.lower().split() if w]

def _score(q_tokens: Counter, p_tokens: Counter) -> float:
    score = 0.0
    for t, qf in q_tokens.items():
        if not t or len(t) < 2: continue
        tf = p_tokens.get(t, 0)
        if tf > 0:
            score += (1 + math.log(1+tf)) * (1 + math.log(1+qf))
    return score

def rank_snippets_by_query(q: str, fulltext: str, topk: int = 12) -> str:
    paras = _split_paragraphs(fulltext)
    q_tok = Counter(_tokenize_ko(q or ""))
    scored = []
    for p in paras:
        p_tok = Counter(_tokenize_ko(p))
        scored.append((_score(q_tok, p_tok), p))
    scored.sort(key=lambda x: x[0], reverse=True)
    keep = [p for sc, p in scored[:topk] if sc > 0]
    return "\n\n".join(keep) if keep else "\n\n".join(paras[:min(len(paras), 6)])

# =============================
# Output routing (classifier)
# =============================
ROUTE_SYS = (
    "질문을 다음 라벨 중 하나로 분류: [단순, 민사, 형사, 행정노무, 복합]. "
    "반드시 라벨 한 단어만 출력."
)

def route_label(q: str) -> str:
    if not client or not AZURE:
        # 오프라인 시 휴리스틱 폴백
        t = (q or "").lower()
        if any(k in t for k in ("형사","고소","고발","벌금","기소","수사","압수수색","사기","폭행","절도","음주","약취","보이스피싱")): return "형사"
        if any(k in t for k in ("민사","손해배상","채무","계약","임대차","유치권","가압류","가처분","소송가액","지연손해금","불법행위")): return "민사"
        if any(k in t for k in ("행정심판","과징금","과태료","허가","인가","취소처분","해임","징계","해고","근로","연차","퇴직금","산재")): return "행정노무"
        return "단순"
    msgs = [{"role":"system","content":ROUTE_SYS},{"role":"user","content": q or ""}]
    try:
        resp = client.chat.completions.create(
            model=AZURE["deployment"], messages=msgs, temperature=0.0, max_tokens=10, stream=False
        )
        return (resp.choices[0].message.content or "단순").strip()
    except Exception:
        return "단순"

# 템플릿: 간결(섹션 헤더만) — 세부는 시스템 프롬프트가 강제
TEMPLATES = {
"형사": """[출력 서식 강제]
## 결론
## 사실관계(확정/가정 구분)
## 적용 법령(조문 직접 인용)
## 판례 요지
## 법리분석(구성요건·위법성·책임)
## 절차·전략
## 참고 자료
""",
"민사": """[출력 서식 강제]
## 결론
## 사실관계(확정/가정 구분)
## 적용 법령(조문 직접 인용)
## 판례 요지
## 법리분석(청구원인·항변·증명책임)
## 절차·전략
## 참고 자료
""",
"행정노무": """[출력 서식 강제]
## 결론
## 사실관계(확정/가정 구분)
## 관련 법령·행정규칙
## 판례/해석례 요지
## 법리분석(처분성·적법절차·비례원칙)
## 구제수단
## 참고 자료
""",
"복합": """[출력 서식 강제]
## 결론
## 사실관계(확정/가정 구분)
## 적용 법령 세트(조문 인용)
## 판례/해석례 교차 요지
## 쟁점별 법리분석(주장/반박/평가)
## 절차·전략
## 참고 자료
""",
"단순": """[출력 서식 강제]
## 결론
## 근거(조문/해석례 링크)
## 다음 확인이 필요한 사실(질문 2~3개)
## 참고 자료
"""
}

# =============================
# System prompt (STRICT — 변호사 메모 규칙)
# =============================
LEGAL_SYS = (
"당신은 대한민국 변호사다. 답변은 **법률 자문 메모** 형식으로 작성한다.\n"
"규칙(모두 강제):\n"
"1) **결론 한 문장**을 맨 앞에 제시하고, 맨 끝에서 다시 1문장으로 재확인한다.\n"
"2) 모든 주장/해석 뒤에는 **근거 각주**를 붙인다: `[법령명 제x조]`, `[대법원 yyyy도/다 nnnn, 선고일]`, `[법제처 해석례 expcSeq]`.\n"
"3) **조문은 1~2문장만 직접 인용**하며 blockquote로 표기한다.\n"
"4) 사실관계는 **확정/가정**을 구분하여 기술한다.\n"
"5) **모호한 표현 금지**(예: '~일 수 있다/보인다/가능성이 있다') — 사용 시 바로 뒤에 근거를 붙인다.\n"
"6) 링크는 **www.law.go.kr** 또는 **대법원 종합법률정보**만 사용한다.\n"
"7) 섹션 헤더는 템플릿에 따르며, 각 섹션은 **2~4문장 이상**으로 구체적으로 작성한다.\n"
"8) 말미에 반드시 `출처: 법제처 국가법령정보센터`와 `⚠️ 참고용 고지` 문구를 넣는다.\n"
)

# =============================
# Model helpers
# =============================
def build_history_messages(max_turns=10):
    msgs = [{"role":"system","content": LEGAL_SYS}]
    history = st.session_state.messages[-max_turns*2:]
    msgs.extend({"role": m["role"], "content": m["content"]} for m in history)
    return msgs

def stream_chat_completion(messages, temperature=0.2, max_tokens=2000):
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

def chat_completion(messages, temperature=0.2, max_tokens=2000) -> str:
    resp = client.chat.completions.create(
        model=AZURE["deployment"], messages=messages,
        temperature=temperature, max_tokens=max_tokens, stream=False,
    )
    try:
        return resp.choices[0].message.content or ""
    except Exception:
        return ""

# =============================
# Sidebar: 링크 생성기 (무인증) — (원본 유지)
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
# Chat flow helpers
# =============================
def _push_user_from_pending() -> str | None:
    q = st.session_state.pop("_pending_user_q", None)
    nonce = st.session_state.pop("_pending_user_nonce", None)
    if not q: return None
    if nonce and st.session_state.get("_last_user_nonce") == nonce: return None
    msgs = st.session_state.messages
    if msgs and msgs[-1].get("role") == "user" and msgs[-1].get("content") == q:
        st.session_state["_last_user_nonce"] = nonce
        return None
    msgs.append({"role": "user", "content": q, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    st.session_state["_last_user_nonce"] = nonce
    return q

def _build_user_context(user_q: str, law_ctx: str) -> str:
    report_ctx = st.session_state.get("report_ctx", "")
    return f"""사용자 질문: {user_q}

관련 법령 정보(분석):
{law_ctx}

[첨부 요약]
{report_ctx if report_ctx else '(없음)'}
"""

# =============================
# History render
# =============================
user_q = _push_user_from_pending()
render_pinned_question()

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

# =============================
# Answer generation (stream + verify pass)
# =============================
if user_q:
    with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
        law_data, used_endpoint, err = search_law_data(user_q, num_rows=st.session_state.settings["num_rows"])
    if used_endpoint: st.caption(f"법제처 API endpoint: `{used_endpoint}`")
    if err: st.warning(err)

    law_ctx = format_law_context(law_data)
    label = route_label(user_q)
    template_block = TEMPLATES.get(label, TEMPLATES["단순"])

    base_msgs = build_history_messages(max_turns=10)
    base_msgs.append({
        "role": "user",
        "content": _build_user_context(user_q, law_ctx) + "\n[템플릿]\n" + template_block + "\n(섹션 헤더는 유지)\n"
    })

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_text, buffer = "", ""
        try:
            placeholder.markdown("_답변 생성 중입니다._")
            if client is None:
                full_text = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + law_ctx
               
            else:
                # 1) Draft streaming
                for piece in stream_chat_completion(base_msgs, temperature=0.2, max_tokens=2000):
                    buffer += piece
                    if len(buffer) >= 200:
                        full_text += buffer; buffer = ""
                        placeholder.markdown(_normalize_text(full_text[-1500:]))
                if buffer:
                    full_text += buffer
                    placeholder.markdown(_normalize_text(full_text))

                # 2) Verify pass (short, non-stream) — 근거/표현/구조 점검
                draft_text = _normalize_text(full_text)
                verify_msgs = build_history_messages(max_turns=6)
                verify_msgs.append({"role":"system","content":
                    "너는 법률 문서 리뷰어다. 아래 초안을 다음 기준으로 교정한다: "
                    "①각 주장에 근거 각주가 있는지, ②누락된 핵심 조문/판례/해석례가 있는지, "
                    "③모호한 표현을 근거와 함께 수정, ④결론을 맨 앞·맨 뒤에 1문장씩 두도록 재배치. "
                    "직접 인용은 1~2문장 blockquote 유지. 섹션 헤더는 유지하라."
                })
                verify_msgs.append({"role":"user","content":
                    f"초안:\n\n{draft_text}\n\n[법령검색컨텍스트]\n{law_ctx}\n\n[첨부요약]\n{st.session_state.get('report_ctx','')}"
                })
                reviewed = chat_completion(verify_msgs, temperature=0.1, max_tokens=1800)
                full_text = reviewed or draft_text
                placeholder.markdown(_normalize_text(full_text))
        except Exception as e:
            full_text = f"**오류**: {e}\n\n{law_ctx}"
            placeholder.markdown(_normalize_text(full_text))

          # (검증 끝난 직후) 최종 텍스트 계산 후
            final_text = _normalize_text(full_text)
            final_text = fix_links_with_lawdata(final_text, law_data)

          # ✅ 이 줄 추가: 이전 placeholder 내용 제거
            placeholder.empty()

          # 그리고 딱 한 번만 말풍선으로 렌더
            render_bubble_with_copy(final_text, key=f"ans-{datetime.now().timestamp()}")


    st.session_state.messages.append({
        "role": "assistant", "content": final_text, "law": law_data, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# =============================
# ChatBar (bottom) — with attachment ranking
# =============================
submitted, typed_text, files = chatbar(
    placeholder="법령에 대한 질문을 입력하거나, 관련 문서를 첨부해서 문의해 보세요…",
    accept=["pdf", "docx", "txt"], max_files=5, max_size_mb=15, key_prefix=KEY_PREFIX,
)

# 첨부를 지금 턴에서 요약·랭킹해서 세션에 저장(다음 턴 모델 입력에 사용)
if files:
    snippets = []
    for f in files:
        name = f.name
        data = f.read()
        ext = os.path.splitext(name)[1].lower()
        if ext == ".pdf":
            txt = extract_text_from_pdf(io.BytesIO(data))
        elif ext == ".docx":
            txt = extract_text_from_docx(io.BytesIO(data))
        elif ext == ".txt":
            txt = read_txt(io.BytesIO(data))
        else:
            txt = f"(미지원 파일 형식: {ext})"
        ranked = rank_snippets_by_query(typed_text or "", txt, topk=12)
        ranked = sanitize(ranked)[:5000]
        snippets.append(f"# [첨부]{name}\n{ranked}")
    st.session_state["report_ctx"] = "\n\n".join(snippets)

if submitted:
    text = (typed_text or "").strip()
    if text:
        st.session_state["_pending_user_q"] = text
        st.session_state["_pending_user_nonce"] = time.time_ns()
    st.session_state["_clear_input"] = True
    st.rerun()

st.markdown('<div style="height: 8px"></div>', unsafe_allow_html=True)
