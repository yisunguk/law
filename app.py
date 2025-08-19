# app.py — Single-window chat with bottom streaming + robust dedupe + pinned question
from __future__ import annotations

import io, os, re, json, time, html
from datetime import datetime
import urllib.parse as up
import xml.etree.ElementTree as ET

import requests
import streamlit as st
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

# 입력창 초기화 플래그가 켜져 있으면, 위젯 생성 전에 값 비움
if st.session_state.pop("_clear_input", False):
    st.session_state[f"{KEY_PREFIX}-input"] = ""

st.markdown(f"""
<style>
.block-container {{ max-width:{PAGE_MAX_WIDTH}px; margin:0 auto; padding-bottom:{BOTTOM_PADDING_PX}px; }}
.stChatInput    {{ max-width:{PAGE_MAX_WIDTH}px; margin-left:auto; margin-right:auto; }}
section.main    {{ padding-bottom:0; }}
.header {{
  text-align:center; padding:1rem; border-radius:12px; background:transparent; color:inherit;
  margin:0 0 1rem 0; border:1px solid rgba(127,127,127,.20);
}}
[data-theme="dark"] .header {{ border-color: rgba(255,255,255,.12); }}
h2, h3 {{ font-size:1.1rem !important; font-weight:600 !important; margin:0.8rem 0 0.4rem; }}
.stMarkdown > div {{ background:var(--bubble-bg,#1f1f1f); color:var(--bubble-fg,#f5f5f5); border-radius:14px; padding:14px 16px; box-shadow:0 1px 8px rgba(0,0,0,.12); }}
[data-theme="light"] .stMarkdown > div {{ --bubble-bg:#fff; --bubble-fg:#222; box-shadow:0 1px 8px rgba(0,0,0,.06); }}
.stMarkdown ul, .stMarkdown ol {{ margin-left:1.1rem; }}
.stMarkdown blockquote {{ margin:8px 0; padding-left:12px; border-left:3px solid rgba(255,255,255,.25); }}
.copy-row{{ display:flex; justify-content:flex-end; margin:6px 4px 0 0; }}
.copy-btn{{ display:inline-flex; align-items:center; gap:6px; padding:6px 10px; border:1px solid rgba(255,255,255,.15); border-radius:10px; background:rgba(0,0,0,.25);
  backdrop-filter:blur(4px); cursor:pointer; font-size:12px; color:inherit; }}
[data-theme="light"] .copy-btn{{ background:rgba(255,255,255,.9); border-color:#ddd; }}
.copy-btn svg{{ pointer-events:none }}
.pinned-q{{ position: sticky; top: 0; z-index: 900; margin: 8px 0 12px; padding: 10px 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,.15);
  background: rgba(0,0,0,.35); backdrop-filter: blur(6px); }}
[data-theme="light"] .pinned-q{{ background: rgba(255,255,255,.85); border-color:#e5e5e5; }}
.pinned-q .label{{ font-size:12px; opacity:.8; margin-bottom:4px; }}
.pinned-q .text{{ font-weight:600; line-height:1.4; max-height:7.5rem; overflow:auto; }}
:root {{ --msg-max: 100%; }}
[data-testid="stChatMessage"] {{ max-width: var(--msg-max) !important; width: 100% !important; }}
[data-testid="stChatMessage"] .stMarkdown, [data-testid="stChatMessage"] .stMarkdown > div {{ width: 100% !important; }}
.law-slide {{ border:1px solid rgba(127,127,127,.25); border-radius:12px; padding:12px 14px; margin:8px 0; }}
[data-theme="light"] .law-slide {{ border-color:#e5e5e5; }}
</style>
""", unsafe_allow_html=True)

# ---- 오른쪽 플로팅 패널용 CSS ----
def _inject_right_rail_css():
    st.markdown("""
<style>
#search-flyout details { margin-top: 6px; }
#search-flyout h4 { font-size: 1rem; }
</style>
""", unsafe_allow_html=True)

    st.markdown("""
    <style>
    /* 채팅 본문이 가려지지 않도록 오른쪽 여백 확보 */
    .block-container { padding-right: 380px !important; }

    /* 오른쪽 고정 패널 */
    #search-flyout {
      position: fixed; right: 18px; top: 88px;
      width: 360px; max-width: 38vw;
      height: calc(100vh - 130px); overflow: auto;
      border-radius: 12px; padding: 12px 14px; z-index: 1000;
      border: 1px solid rgba(127,127,127,.25);
      background: rgba(0,0,0,.35); backdrop-filter: blur(6px);
    }
    [data-theme="light"] #search-flyout {
      background: #fff; color: #222; border-color: #e5e5e5;
    }
    [data-theme="dark"] #search-flyout {
      background: #1f1f1f; color: #eee; border-color: rgba(255,255,255,.16);
    }

    /* 좁은 화면(모바일/태블릿)은 상하 스택 */
    @media (max-width: 1024px) {
      .block-container { padding-right: 0 !important; }
      #search-flyout   { position: static; width: auto; height: auto; }
    }
    </style>
    """, unsafe_allow_html=True)

# ---- 오른쪽 플로팅 패널 렌더러 ----
def render_search_flyout(user_q: str, num_rows: int = 3):
    """오른쪽 고정 패널: 통합 검색 결과 (순수 HTML 렌더링)"""
    results = find_all_law_data(user_q, num_rows=num_rows)

    esc = html.escape
    html_parts = []
    html_parts.append('<div id="search-flyout">')
    html_parts.append('<h3>📚 통합 검색 결과</h3>')
    html_parts.append('<details open><summary style="cursor:pointer;font-weight:600">열기/접기</summary>')

    for label, pack in results.items():
        items = pack.get("items") or []
        err   = pack.get("error")

        html_parts.append(f'<h4 style="margin:10px 0 6px">🔎 {esc(label)}</h4>')

        if err:
            html_parts.append(f'<div style="opacity:.85">⚠️ {esc(err)}</div>')
            continue
        if not items:
            html_parts.append('<div style="opacity:.65">검색 결과 없음</div>')
            continue

        # 결과 카드 목록
        for i, law in enumerate(items, 1):
            nm   = esc(law.get("법령명",""))
            kind = esc(law.get("법령구분",""))
            dept = esc(law.get("소관부처명",""))
            eff  = esc(law.get("시행일자","-"))
            pub  = esc(law.get("공포일자","-"))
            link = law.get("법령상세링크")

            html_parts.append('<div style="border:1px solid rgba(127,127,127,.25);'
                              'border-radius:12px;padding:10px 12px;margin:8px 0">')
            html_parts.append(f'<div style="font-weight:700">{i}. {nm} '
                              f'<span style="opacity:.7">({kind})</span></div>')
            html_parts.append(f'<div style="margin-top:4px">소관부처: {dept}</div>')
            html_parts.append(f'<div>시행일자: {eff} / 공포일자: {pub}</div>')
            if link:
                html_parts.append(f'<div style="margin-top:6px">'
                                  f'<a href="{esc(link)}" target="_blank">법령 상세보기</a>'
                                  f'</div>')
            html_parts.append('</div>')

    html_parts.append('</details>')
    html_parts.append('</div>')  # #search-flyout

    st.markdown("\n".join(html_parts), unsafe_allow_html=True)


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
LAW_PORTAL_BASE = "https://www.law.go.kr/"

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
def choose_law_queries_llm_first(user_q: str) -> list[str]:
    ordered: list[str] = []

    # 1) LLM 후보 우선
    llm_candidates = extract_law_candidates_llm(user_q) or []
    for nm in llm_candidates:
        if nm and nm not in ordered:
            ordered.append(nm)

    # 2) 후보가 '없을 때만' 폴백 질의 추가
    if not ordered:
        cleaned = _clean_query_for_api(user_q)
        if cleaned:
            ordered.append(cleaned)

        # (옵션) 키워드 맵 폴백
        for kw, mapped in KEYWORD_TO_LAW.items():
            if kw in (user_q or "") and mapped not in ordered:
                ordered.append(mapped)

    return ordered

def render_bubble_with_copy(message: str, key: str):
    """어시스턴트 말풍선 전용 복사 버튼"""
    message = _normalize_text(message or "")
    st.markdown(message)
    safe_raw_json = json.dumps(message)
    html_tpl = '''
    <div class="copy-row">
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

# ===== Pinned Question helper =====
def _esc(s: str) -> str:
    return html.escape(s or "").replace("\n", "<br>")

def render_pinned_question():
    last_q = None
    for m in reversed(st.session_state.get("messages", [])):
        if m.get("role") == "user":
            last_q = m.get("content", "")
            break
    if not last_q:
        return
    st.markdown(f"""
    <div class="pinned-q">
      <div class="label">최근 질문</div>
      <div class="text">{_esc(last_q)}</div>
    </div>
    """, unsafe_allow_html=True)

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

if "messages" not in st.session_state: st.session_state.messages = []
if "settings" not in st.session_state:
    st.session_state.settings = {
        "num_rows": 10,
        "include_search": True,
        "safe_mode": False,
        "animate": True,
        "animate_delay": 0.9,
    }
if "_last_user_nonce" not in st.session_state: st.session_state["_last_user_nonce"] = None

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

    api_key = (LAW_API_KEY or "").strip().strip('"').strip("'")
    if "%" in api_key and any(t in api_key.upper() for t in ("%2B", "%2F", "%3D")):
        try: api_key = up.unquote(api_key)
        except Exception: pass

    params = {
        "serviceKey": api_key,
        "target": target,
        "query": query or "*",
        "numOfRows": max(1, min(10, int(num_rows))),
        "pageNo": max(1, int(page_no)),
    }

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

# === add: LLM 기반 키워드 추출기 ===
@st.cache_data(show_spinner=False, ttl=300)
def extract_keywords_llm(q: str) -> list[str]:
    """
    사용자 질문에서 '짧은 핵심 키워드' 2~6개만 JSON으로 뽑는다.
    예: {"keywords":["건설현장","사망사고","살인","현장소장"]}
    """
    if not q or (client is None):
        return []
    SYSTEM_KW = (
        "너는 한국 법률 질의의 핵심 키워드만 추출하는 도우미야. "
        "반드시 JSON만 반환해. 설명 금지.\n"
        '형식: {"keywords":["건설현장","사망사고","형사책임","안전보건"]}'
    )
    try:
        resp = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=[{"role":"system","content": SYSTEM_KW},
                      {"role":"user","content": q.strip()}],
            temperature=0.0, max_tokens=96,
        )
        txt = (resp.choices[0].message.content or "").strip()
        # 코드펜스/잡텍스트 제거 (법령 추출기와 동일 방식)
        if "```" in txt:
            import re
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
            if m: txt = m.group(1).strip()
        if not txt.startswith("{"):
            import re
            m = re.search(r"\{[\s\S]*\}", txt)
            if m: txt = m.group(0)

        data = json.loads(txt)
        kws = [s.strip() for s in data.get("keywords", []) if s.strip()]
        # 과도한 일반어 제거(선택): 한 글자/두 글자 일반명사 등
        kws = [k for k in kws if len(k) >= 2]
        return kws[:6]
    except Exception:
        return []

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



# 통합 검색(Expander용) — 교체본
def find_all_law_data(query: str, num_rows: int = 3):
    results = {}

    # --- 1) 키워드/후보 준비 ---
    kw_list = extract_keywords_llm(query)                         # LLM 키워드 추출
    q_clean = _clean_query_for_api(query)                         # 폴백 전처리
    law_name_candidates = extract_law_candidates_llm(query) or [] # 법령명 후보

    # --- 2) 키워드 → 복합(2~3그램) 질의어 생성 ---
    top = kw_list[:5]
    keyword_queries: list[str] = []

    # bigrams
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            keyword_queries.append(f"{top[i]} {top[j]}")

    # trigrams (최대 3개만 사용)
    for i in range(min(3, len(top))):
        for j in range(i + 1, min(3, len(top))):
            for k in range(j + 1, min(3, len(top))):
                keyword_queries.append(f"{top[i]} {top[j]} {top[k]}")

    # 중복 제거(순서 보존) + 개수 제한
    _seen = set()
    keyword_queries = [q for q in keyword_queries if not (q in _seen or _seen.add(q))]
    keyword_queries = keyword_queries[:10]

    # --- 3) 법령명 후보(LLM) 보조 추가 ---
    for nm in law_name_candidates:
        if nm and nm not in keyword_queries:
            keyword_queries.append(nm)

    # --- 4) 폴백은 '아무 후보도 없을 때만' ---
    if not keyword_queries and q_clean:
        keyword_queries.append(q_clean)

    # (선택) 키워드→대표 법령명 맵 보조
    for kw, mapped in KEYWORD_TO_LAW.items():
        if kw in (query or "") and mapped not in keyword_queries:
            keyword_queries.append(mapped)

    # --- 5) '법령' 섹션 검색 ---
    law_items_all, law_errs, law_endpoint = [], [], None
    for qx in keyword_queries[:10]:
        try:
            items, endpoint, err = _call_moleg_list("law", qx, num_rows=num_rows)
            if items:
                law_items_all.extend(items)
                law_endpoint = endpoint
            if err:
                law_errs.append(f"{qx}: {err}")
        except Exception as e:
            law_errs.append(f"{qx}: {e}")

    # --- 6) LLM 리랭커(맥락 필터) + 소프트 정렬 ---
    if law_items_all:
        # LLM이 질문 맥락과 무관한 법령(예: 군/국방) 제외/후순위
        law_items_all = rerank_laws_with_llm(query, law_items_all, top_k=8)

        # 군 맥락이 없으면 군/국방 계열을 뒤로 미는 소프트 스코어
        def _score_by_ctx(item: dict) -> int:
            name = (item.get("법령명") or "")
            dept = (item.get("소관부처명") or "")
            score = 0
            has_mil = any(x in (query or "") for x in ["군", "국방", "군인", "부대", "장병"])
            if not has_mil and ("국방부" in dept or any(x in name for x in ["군에서", "군형법", "군사", "군인"])):
                score += 50
            return score

        law_items_all.sort(key=_score_by_ctx)

    # --- 7) 패킹 ---
    results["법령"] = {
        "items": law_items_all,
        "endpoint": law_endpoint,
        "error": "; ".join(law_errs) if law_errs else None,
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
    # 필요 시 확장...
}

SYSTEM_EXTRACT = """너는 한국 법령명을 추출하는 도우미야.
사용자 질문에서 관련 '법령명(공식명)' 후보를 1~3개 뽑아 JSON으로만 응답해.
형식: {"laws":["개인정보 보호법","개인정보 보호법 시행령"]} 다른 말 금지.
법령명이 애매하면 가장 유력한 것 1개만.
"""

@st.cache_data(show_spinner=False, ttl=300)
def extract_law_candidates_llm(q: str) -> list[str]:
    if not q or (client is None):
        return []
    try:
        resp = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=[
                {"role": "system", "content": SYSTEM_EXTRACT},
                {"role": "user", "content": q.strip()},
            ],
            temperature=0.0,
            max_tokens=128,
        )
        txt = (resp.choices[0].message.content or "").strip()

        # --- 추가: 코드펜스/잡텍스트 제거 ---
        if "```" in txt:
            import re
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
            if m:
                txt = m.group(1).strip()

        if not txt.startswith("{"):
            import re
            m = re.search(r"\{[\s\S]*\}", txt)
            if m:
                txt = m.group(0)

        # --- JSON 파싱 ---
        data = json.loads(txt)
        laws = [s.strip() for s in data.get("laws", []) if s.strip()]
        return laws[:3]

    except Exception:
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
# 출력 템플릿 · 분류기 (강제 최소화)
# =============================
def choose_output_template(q: str) -> str:
    return "가능하면 대한민국의 최고 변호사처럼 답변해 주세요.\n"

# =============================
# System prompt (법률 메모 + 도구 사용 규칙)
# =============================
LEGAL_SYS = (
"당신은 대한민국 변호사다. 답변은 **법률 자문 메모** 형식으로 간결하게 작성한다.\n"
"출력 규칙(강제):\n"
"- 내부적으로 의도 분석/검색/재검색은 수행하되, **그 절차를 출력하지 말 것**.\n"
"- 형식은 사용자의 의도에 맞게 내용을 작성하되 근거 요약(조문 1~2문장 인용 가능), 출처 링크[법령명](URL)는 제공해야 함.\n"
"- 같은 내용이나 섹션을 **반복 출력 금지**. 메모는 한 번만 쓴다.\n"
"- 링크는 반드시 www.law.go.kr(또는 glaw.scourt.go.kr)만 사용. 상대경로는 절대URL로.\n"
"- 확실치 않으면 단정 금지, ‘추가 확인 필요’ 사유를 짧게 적시.\n"
"- 어구: 과장/군더더기 금지, 문장은 짧게.\n"
"\n"
)

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

def ask_llm_with_tools(user_q: str, num_rows: int = 5, stream: bool = True):
    # 0) 메시지 구성
    msgs = [
        {"role": "system", "content": LEGAL_SYS},
        {"role": "user", "content": user_q},
    ]

    # 0-1) 관련 법령 프리패치 → 프라이머(system) 1회 주입
    try:
        pre_laws = prefetch_law_context(user_q, num_rows_per_law=3)
        primer = _summarize_laws_for_primer(pre_laws, max_items=6)
        if primer:
            msgs.insert(1, {"role": "system", "content": primer})
    except Exception:
        pass

    # 1) 1차 호출: 툴콜 유도 (스트리밍 아님)
    resp1 = safe_chat_completion(
        client,
        messages=msgs,
        model=AZURE["deployment"],
        stream=False,
        allow_retry=True,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.2,
        max_tokens=1200,
    )
    if resp1.get("type") == "blocked_by_content_filter":
        yield ("final", resp1["message"], [])
        return

    msg1 = resp1["resp"].choices[0].message
    law_for_links = []

    # 2) 툴 실행 (있을 때)
    if getattr(msg1, "tool_calls", None):
        msgs.append({"role": "assistant", "tool_calls": msg1.tool_calls})
        for call in msg1.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            if name == "search_one":
                result = tool_search_one(**args)
            elif name == "search_multi":
                result = tool_search_multi(**args)
            else:
                result = {"error": f"unknown tool: {name}"}

            # 링크 교정용 법령 누적
            if isinstance(result, dict) and result.get("items"):
                law_for_links.extend(result["items"])
            elif isinstance(result, list):
                for r in result:
                    if r.get("items"):
                        law_for_links.extend(r["items"])

            msgs.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False)
            })

    # 3) 2차 호출: 최종 답변 생성 (stream 여부에 따라)
    if stream:
        resp2 = safe_chat_completion(
            client,
            messages=msgs,
            model=AZURE["deployment"],
            stream=True,
            allow_retry=True,
            temperature=0.2,
            max_tokens=1400,
        )
        if resp2.get("type") == "blocked_by_content_filter":
            yield ("final", resp2["message"], law_for_links)
            return

        out = ""
        for ch in resp2["stream"]:
            try:
                c = ch.choices[0]
                if getattr(c, "finish_reason", None):
                    break
                d = getattr(c, "delta", None)
                txt = getattr(d, "content", None) if d else None
                if txt:
                    out += txt
                    yield ("delta", txt, law_for_links)
            except Exception:
                continue
        yield ("final", out, law_for_links)
    else:
        resp2 = safe_chat_completion(
            client,
            messages=msgs,
            model=AZURE["deployment"],
            stream=False,
            allow_retry=True,
            temperature=0.2,
            max_tokens=1400,
        )
        if resp2.get("type") == "blocked_by_content_filter":
            yield ("final", resp2["message"], law_for_links)
            return
        final_text = resp2["resp"].choices[0].message.content or ""
        yield ("final", final_text, law_for_links)

    # === add: LLM 호출 전에 '여러 법령 컨텍스트' 프라이머를 시스템 메시지로 주입 ===
    try:
        pre_laws = prefetch_law_context(user_q, num_rows_per_law=3)   # 위에서 만든 프리패치
        primer = _summarize_laws_for_primer(pre_laws, max_items=6)
        if primer:
            msgs.insert(1, {"role":"system","content": primer})
    except Exception:
        pass  # 프리패치 실패 시 조용히 진행

    # ---------- [변경 없음] 이후 기존 safe_chat_completion 로직, tools, 스트리밍 등 유지 ----------
    resp_dict = safe_chat_completion(
        client,
        messages=msgs,
        model=AZURE["deployment"],
        stream=False,
        allow_retry=True,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.2,
        max_tokens=1200,
    )
    # 이하 원래 코드 그대로...


# =============================
# Sidebar: 링크 생성기 (무인증)
# =============================
with st.sidebar:
    st.header("🔗 링크 생성기 (무인증)")
    tabs = st.tabs(["법령", "행정규칙", "자치법규", "조약", "판례", "헌재", "해석례", "용어/별표"])

    # ───────────────────────── 법령
    with tabs[0]:
        law_name = st.text_input("법령명", value="민법", key="sb_law_name")

        # 자동 추천 키워드(멀티선택)
        law_suggest = suggest_keywords_for_law(law_name)
        law_keys_ms = st.multiselect("키워드(자동 추천)", options=law_suggest, default=law_suggest[:2], key="sb_law_keys_ms")

        if st.button("법령 상세 링크 만들기", key="sb_btn_law"):
            keys = list(law_keys_ms) if law_keys_ms else []
            url = hangul_law_with_keys(law_name, keys) if keys else hangul_by_name("법령", law_name)
            st.session_state["gen_law"] = {"url": url, "kind": "law", "q": law_name}
    
        if "gen_law" in st.session_state:
            d = st.session_state["gen_law"]
            present_url_with_fallback(d["url"], d["kind"], d["q"], label_main="새 탭에서 열기")

    # ───────────────────────── 행정규칙
    with tabs[1]:
        adm_name = st.text_input("행정규칙명", value="수입통관사무처리에관한고시", key="sb_adm_name")
        dept     = st.selectbox("소관 부처(선택)", MINISTRIES, index=0, key="sb_adm_dept")

        colA, colB = st.columns(2)
        with colA: issue_no = st.text_input("공포번호(선택)", value="", key="sb_adm_no")
        with colB: issue_dt = st.text_input("공포일자(YYYYMMDD, 선택)", value="", key="sb_adm_dt")

        adm_keys_ms = st.multiselect("키워드(자동 추천)", options=suggest_keywords_for_tab("admrul"),
                                     default=["고시", "개정"], key="sb_adm_keys_ms")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("행정규칙 링크 만들기", key="sb_btn_adm"):
                if issue_no and issue_dt:
                    url = hangul_admrul_with_keys(adm_name, issue_no, issue_dt)
                else:
                    url = hangul_by_name("행정규칙", adm_name)
                st.session_state["gen_adm"] = {"url": url, "kind": "admrul", "q": adm_name}
        with col2:
            if st.button("행정규칙(부처/키워드) 검색 링크", key="sb_btn_adm_dept"):
                keys = " ".join(adm_keys_ms) if adm_keys_ms else ""
                q = " ".join(x for x in [adm_name, dept if dept and dept != MINISTRIES[0] else "", keys] if x)
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
        colA, colB = st.columns(2)
        with colA: ordin_no = st.text_input("공포번호(선택)", value="", key="sb_ordin_no")
        with colB: ordin_dt = st.text_input("공포일자(YYYYMMDD, 선택)", value="", key="sb_ordin_dt")

        # 추천 키워드(검색용)
        ordin_keys_ms = st.multiselect("키워드(자동 추천)", options=suggest_keywords_for_tab("ordin"),
                                       default=["조례", "개정"], key="sb_ordin_keys_ms")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("자치법규 링크 만들기", key="sb_btn_ordin"):
                if ordin_no and ordin_dt:
                    url = hangul_ordin_with_keys(ordin_name, ordin_no, ordin_dt)
                else:
                    url = hangul_by_name("자치법규", ordin_name)
                st.session_state["gen_ordin"] = {"url": url, "kind": "ordin", "q": ordin_name}
        with col2:
            if st.button("자치법규(키워드) 검색 링크", key="sb_btn_ordin_kw"):
                keys = " ".join(ordin_keys_ms) if ordin_keys_ms else ""
                q = " ".join(x for x in [ordin_name, keys] if x)
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
        trty_keys_ms = st.multiselect("키워드(자동 추천)", options=suggest_keywords_for_tab("trty"),
                                      default=["발효"], key="sb_trty_keys_ms")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("조약 상세 링크 만들기", key="sb_btn_trty"):
                url = hangul_trty_with_keys(trty_no, eff_dt)
                st.session_state["gen_trty"] = {"url": url, "kind": "trty", "q": trty_no}
        with col2:
            if st.button("조약(키워드) 검색 링크", key="sb_btn_trty_kw"):
                q = " ".join([trty_no] + trty_keys_ms) if trty_keys_ms else trty_no
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
        prec_keys_ms = st.multiselect("키워드(자동 추천·검색용)", options=suggest_keywords_for_tab("prec"),
                                      default=["손해배상"], key="sb_prec_keys_ms")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("대법원 판례 링크 만들기", key="sb_btn_prec"):
                url = build_scourt_link(case_no)
                st.session_state["gen_prec"] = {"url": url, "kind": "prec", "q": case_no}
        with col2:
            if st.button("판례(키워드) 검색 링크", key="sb_btn_prec_kw"):
                q = " ".join([case_no] + prec_keys_ms) if case_no else " ".join(prec_keys_ms)
                url = build_fallback_search("prec", q)   # 키워드→law.go.kr로 보조 검색
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
        cc_keys_ms = st.multiselect("키워드(자동 추천·검색용)", options=suggest_keywords_for_tab("cc"),
                                    default=["위헌"], key="sb_cc_keys_ms")

        if st.button("헌재 검색 링크 만들기", key="sb_btn_cc"):
            q = " ".join([cc_q] + cc_keys_ms) if cc_q else " ".join(cc_keys_ms)
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
            expc_keys_ms = st.multiselect("키워드(자동 추천·검색용)", options=suggest_keywords_for_tab("expc"),
                                          default=["유권해석"], key="sb_expc_keys_ms")
            if st.button("해석례(키워드) 검색 링크", key="sb_btn_expc_kw"):
                q = " ".join([expc_id] + expc_keys_ms) if expc_id else " ".join(expc_keys_ms)
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
            term_id = st.text_input("법령용어 ID", value="3945293", key="sb_term_id")
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

# =============================
# Chat flow
# =============================
def _push_user_from_pending() -> str | None:
    q = st.session_state.pop("_pending_user_q", None)
    nonce = st.session_state.pop("_pending_user_nonce", None)
    if not q: return None
    if nonce and st.session_state.get("_last_user_nonce") == nonce: return None
    msgs = st.session_state.messages
    if msgs and msgs[-1].get("role") == "user" and msgs[-1].get("content") == q:
        st.session_state["_last_user_nonce"] = nonce; return None
    msgs.append({"role":"user","content": q, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    st.session_state["_last_user_nonce"] = nonce
    return q

user_q = _push_user_from_pending()
render_pinned_question()
msgs = st.session_state.get("messages", [])
st.session_state.messages = [
    m for m in msgs if not (m.get("role")=="assistant" and not (m.get("content") or "").strip())
]

with st.container():
    for i, m in enumerate(st.session_state.messages):
        role = m.get("role")
        content = (m.get("content") or "")
        if role == "assistant" and not content.strip():
            continue  # ✅ 내용이 비면 말풍선 자체를 만들지 않음

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


# 🔻 어시스턴트 답변 출력은 반드시 user_q가 있을 때만 실행 (초기 빈 말풍선 방지)
# ===============================
# 좌우 분리 레이아웃 (교체용)
# ===============================
# ===============================
# 좌우 분리 레이아웃: 왼쪽(답변) / 오른쪽(통합검색)
# ===============================
if user_q:
    _inject_right_rail_css()
    render_search_flyout(user_q, num_rows=3)

    if client and AZURE:
        # 1) 말풍선 없이 임시 컨테이너로 스트리밍
        stream_box = st.empty()
        full_text, buffer, collected_laws = "", "", []
        try:
            stream_box.markdown("_AI가 질의를 해석하고, 법제처 DB를 검색 중입니다._")
            for kind, payload, law_list in ask_llm_with_tools(user_q, num_rows=5, stream=True):
                if kind == "delta":
                    buffer += (payload or "")
                    if len(buffer) >= 200:
                        full_text += buffer; buffer = ""
                        stream_box.markdown(_normalize_text(full_text[-1500:]))
                elif kind == "final":
                    full_text += (payload or "")
                    collected_laws = law_list or []
                    break
            if buffer:
                full_text += buffer
        except Exception as e:
            laws, ep, err, mode = find_law_with_fallback(user_q, num_rows=10)
            collected_laws = laws
            law_ctx = format_law_context(laws)
            tpl = choose_output_template(user_q)
            full_text = f"{tpl}\n\n{law_ctx}\n\n(오류: {e})"

        # 2) 후처리
        final_text = _normalize_text(full_text)
        final_text = fix_links_with_lawdata(final_text, collected_laws)
        final_text = _dedupe_blocks(final_text)

        stream_box.empty()  # 임시 표시 제거

        # 3) 본문이 있을 때만 말풍선 생성
        if final_text.strip():
            with st.chat_message("assistant"):
                render_bubble_with_copy(final_text, key=f"ans-{datetime.now().timestamp()}")
            st.session_state.messages.append({
                "role": "assistant",
                "content": final_text,
                "law": collected_laws,
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        else:
            # ✅ 말풍선 만들지 않음 (회색 버블 방지)
            st.info("현재 모델이 오프라인이거나 오류로 인해 답변을 생성하지 못했습니다.")
    else:
        st.info("답변 엔진이 아직 설정되지 않았습니다. API 키/엔드포인트를 확인해 주세요.")



        # --- 최종 후처리 ---
        final_text = _normalize_text(full_text)
        final_text = fix_links_with_lawdata(final_text, collected_laws)
        final_text = _dedupe_blocks(final_text)

        # --- 빈 답변 가드 ---
        if not final_text.strip():
            # 스트리밍 중 띄운 문구만 지우고, 빈 말풍선은 남기지 않음
            placeholder.empty()
            st.info("현재 모델이 오프라인이거나 오류로 인해 답변을 생성하지 못했습니다.")
        else:
            # 로딩/중간 출력 지우기 → 최종 말풍선 렌더
            placeholder.empty()
            with placeholder.container():
                render_bubble_with_copy(final_text, key=f"ans-{datetime.now().timestamp()}")

            # 대화 기록 저장 (내용 있을 때만)
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": final_text,
                    "law": collected_laws,
                    "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

   # 4) ChatBar (맨 아래 고정)
submitted, typed_text, files = chatbar(
    placeholder="법령에 대한 질문을 입력하거나, 인터넷 URL, 관련 문서를 첨부해서 문의해 보세요…",
    accept=["pdf", "docx", "txt"], max_files=5, max_size_mb=15, key_prefix=KEY_PREFIX,
)
if submitted:
    text = (typed_text or "").strip()
    if text:
        st.session_state["_pending_user_q"] = text
        st.session_state["_pending_user_nonce"] = time.time_ns()
    st.session_state["_clear_input"] = True
    st.rerun()

st.markdown('<div style="height: 8px"></div>', unsafe_allow_html=True)
