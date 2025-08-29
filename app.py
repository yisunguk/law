# === BEGIN: bootstrap shims to avoid NameError and keep UX working ===
from __future__ import annotations
import os, sys, re, time, uuid, hashlib
import urllib.parse as up
from datetime import datetime
import streamlit as st

# ── 메시지 상태 보장 ─────────────────────────────────────────────
if "_ensure_messages" not in globals():
    def _ensure_messages() -> None:
        if not isinstance(st.session_state.get("messages"), list):
            st.session_state["messages"] = []

if "_safe_append_message" not in globals():
    def _safe_append_message(role: str, content: str, **extra) -> None:
        _ensure_messages()
        txt = (content or "").strip()
        if not txt:
            return
        if txt.startswith("```") and txt.endswith("```"):
            # 빈 코드블록/중복 방지
            return
        msgs = st.session_state["messages"]
        if msgs and isinstance(msgs[-1], dict):
            prev = msgs[-1]
            if prev.get("role") == role and (prev.get("content") or "").strip() == txt:
                return
        msgs.append({
            "role": role,
            "content": txt,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            **(extra or {})
        })

if "_append_message" not in globals():
    def _append_message(role: str, content: str, **extra) -> None:
        _safe_append_message(role, content, **extra)

# ── 이름 보정: 부처 선택 값 ──────────────────────────────────────
if "MINISTRIES" not in globals():
    MINISTRIES = [
        "부처 선택(선택)",
        "국무조정실", "기획재정부", "교육부", "과학기술정보통신부",
        "외교부", "통일부", "법무부", "행정안전부", "문화체육관광부",
        "농림축산식품부", "산업통상자원부", "보건복지부", "환경부",
        "고용노동부", "여성가족부", "국토교통부", "해양수산부",
        "중소벤처기업부", "금융위원회", "방송통신위원회", "공정거래위원회",
        "국가보훈부", "인사혁신처", "원자력안전위원회", "질병관리청",
    ]

# ── 검색/링크 유틸 폴백 ─────────────────────────────────────────
if "normalize_law_link" not in globals():
    def normalize_law_link(url: str) -> str:
        return (url or "").strip()

if "build_fallback_search" not in globals():
    def build_fallback_search(kind: str, q: str) -> str:
        base = {
            "law":   "https://www.law.go.kr/LSW/lsSc.do",
            "admrul":"https://www.law.go.kr/admRulSc.do",
            "ordin":"https://www.law.go.kr/ordinSc.do",
            "trty": "https://www.law.go.kr/trtySc.do",
            "prec": "https://www.law.go.kr/precSc.do",
            "cc":   "https://www.law.go.kr/precSc.do",
            "expc": "https://www.law.go.kr/expcInfoSc.do",
            "term": "https://www.law.go.kr/LSW/termInfoR.do",
            "file": "https://www.law.go.kr/LSW/lsBylInfoR.do",
        }.get(kind, "https://www.law.go.kr/LSW/lsSc.do")
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}query={up.quote((q or '').strip())}"

if "present_url_with_fallback" not in globals():
    def present_url_with_fallback(url: str, kind: str, q: str, label_main: str = "열기"):
        u = (url or "").strip() or build_fallback_search(kind, q)
        st.link_button(f"🔗 {label_main}", u, use_container_width=True)
        st.caption(u)

# ── 간단 링크 빌더(이름+키워드) ─────────────────────────────────
if "hangul_by_name" not in globals():
    def hangul_by_name(kind: str, name: str) -> str:
        return build_fallback_search(kind.lower(), name)

if "hangul_law_with_keys" not in globals():
    def hangul_law_with_keys(name: str, keys: list[str]) -> str:
        q = " ".join([name] + (keys or []))
        return build_fallback_search("law", q)

if "hangul_admrul_with_keys" not in globals():
    def hangul_admrul_with_keys(name: str, issue_no: str = "", issue_dt: str = "") -> str:
        q = " ".join([x for x in [name, issue_no, issue_dt] if x])
        return build_fallback_search("admrul", q)

if "hangul_ordin_with_keys" not in globals():
    def hangul_ordin_with_keys(name: str, no: str = "", dt: str = "") -> str:
        q = " ".join([x for x in [name, no, dt] if x])
        return build_fallback_search("ordin", q)

if "hangul_trty_with_keys" not in globals():
    def hangul_trty_with_keys(no: str, eff_dt: str) -> str:
        q = " ".join([x for x in [no, eff_dt] if x])
        return build_fallback_search("trty", q)

if "build_scourt_link" not in globals():
    def build_scourt_link(case_no: str) -> str:
        # 대법원/법제처 검색으로 폴백
        return build_fallback_search("prec", case_no)

if "expc_public_by_id" not in globals():
    def expc_public_by_id(expc_id: str) -> str:
        return build_fallback_search("expc", expc_id)

if "licbyl_file_download" not in globals():
    def licbyl_file_download(flseq: str) -> str:
        # 별표·서식 파일: 검색 폴백(직접 다운로드 링크는 케이스별로 상이)
        return build_fallback_search("file", flseq)

# ── 채팅 입력/진행 관련 ─────────────────────────────────────────
if "_hash_text" not in globals():
    def _hash_text(s: str) -> str:
        return hashlib.sha256((s or "").encode("utf-8")).hexdigest()

if "_chat_started" not in globals():
    def _chat_started() -> bool:
        _ensure_messages()
        if (st.session_state.get("_pending_user_q") or "").strip():
            return True
        for m in st.session_state["messages"]:
            if isinstance(m, dict) and m.get("role") == "user" and (m.get("content") or "").strip():
                return True
        return False

if "_push_user_from_pending" not in globals():
    def _push_user_from_pending() -> str:
        """하단 입력창 또는 프리챗 입력의 임시 버퍼를 대화로 편입"""
        q = (st.session_state.pop("_pending_user_q", "") or "").strip()
        if q:
            nonce = st.session_state.pop("_pending_user_nonce", str(uuid.uuid4()))
            st.session_state["current_turn_nonce"] = nonce
            _append_message("user", q)
        return q

if "render_post_chat_simple_ui" not in globals():
    def render_post_chat_simple_ui():
        txt = st.chat_input("질문을 입력하세요. (예: 민법 제83조 본문 보여줘 — 요약하지 말고)")
        if txt:
            st.session_state["_pending_user_q"] = txt.strip()
            st.session_state["_pending_user_nonce"] = str(uuid.uuid4())
            st.rerun()

if "render_pre_chat_center" not in globals():
    def render_pre_chat_center():
        st.markdown("## ⚖️ 법제처 법무 상담사\n원하시는 법령/조문을 입력해 보세요.")
        render_post_chat_simple_ui()

if "render_bubble_with_copy" not in globals():
    def render_bubble_with_copy(text: str, key: str | None = None):
        st.markdown(text)

if "render_api_diagnostics" not in globals():
    def render_api_diagnostics():
        # 디버그용(필요시 확장)
        return

# ── 디버그 플래그 기본값 ────────────────────────────────────────
if "SHOW_SEARCH_DEBUG" not in globals():
    SHOW_SEARCH_DEBUG = False
if "SHOW_STREAM_PREVIEW" not in globals():
    SHOW_STREAM_PREVIEW = False
# === END: bootstrap shims ===

# ✅ ROOT 반드시 먼저 정의 후 sys.path에 추가
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

def _ensure_messages() -> None:
    if not isinstance(st.session_state.get("messages"), list):
        st.session_state["messages"] = []

def _safe_append_message(role: str, content: str, **extra) -> None:
    _ensure_messages()
    txt = (content or "").strip()
    if not txt:
        return
    if txt.startswith("```") and txt.endswith("```"):
        return
    msgs = st.session_state["messages"]
    if msgs and isinstance(msgs[-1], dict):
        prev = msgs[-1]
        if prev.get("role") == role and (prev.get("content") or "").strip() == txt:
            return
    msgs.append({
        "role": role,
        "content": txt,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **(extra or {})
    })



# === HOTFIX: define early fallbacks so calls never raise NameError ===
if "cached_suggest_for_tab" not in globals():
    def cached_suggest_for_tab(tab_key: str):
        _DEFAULT = {
            "admrul": ["고시", "훈령", "예규", "지침", "개정"],
            "ordin":  ["조례", "규칙", "규정", "시행", "개정"],
            "trty":   ["비준", "발효", "양자", "다자", "협정"],
            "prec":   ["손해배상", "대여금", "사기", "이혼", "근로"],
            "cc":     ["위헌", "합헌", "각하", "침해", "기각"],
            "expc":   ["유권해석", "법령해석", "질의회신", "적용범위"],
        }
        try:
            from modules import suggest_keywords_for_tab
            import streamlit as st
            store = st.session_state.setdefault("__tab_suggest__", {})
            if tab_key not in store:
                store[tab_key] = suggest_keywords_for_tab(tab_key) or _DEFAULT.get(tab_key, [])
            return store[tab_key]
        except Exception:
            return _DEFAULT.get(tab_key, [])

if "cached_suggest_for_law" not in globals():
    def cached_suggest_for_law(law_name: str):
        _DEFAULT_LAW = {
            "민법": ["제839조", "재산분할", "이혼", "제840조", "친권"],
            "형법": ["제307조", "명예훼손", "사기", "폭행", "상해"],
        }
        try:
            from modules import suggest_keywords_for_law
            import streamlit as st
            store = st.session_state.setdefault("__law_suggest__", {})
            if law_name not in store:
                store[law_name] = suggest_keywords_for_law(law_name) or _DEFAULT_LAW.get(law_name, ["정의","목적","벌칙"])
            return store[law_name]
        except Exception:
            return _DEFAULT_LAW.get(law_name, ["정의","목적","벌칙"])

# --- CONSTANT: central ministries list (used by selectbox) ---
if "MINISTRIES" not in globals():
    MINISTRIES = [
        "부처 선택(선택)",
        "국무조정실", "기획재정부", "교육부", "과학기술정보통신부",
        "외교부", "통일부", "법무부", "행정안전부", "문화체육관광부",
        "농림축산식품부", "산업통상자원부", "보건복지부", "환경부",
        "고용노동부", "여성가족부", "국토교통부", "해양수산부",
        "중소벤처기업부", "금융위원회", "방송통신위원회", "공정거래위원회",
        "국가보훈부", "인사혁신처", "원자력안전위원회", "질병관리청",
    ]
# -------------------------------------------------------------
# === END HOTFIX ===
    if not isinstance(st.session_state.get("messages"), list):
        st.session_state["messages"] = []

def _safe_append_message(role: str, content: str, **extra) -> None:
    _ensure_messages()

def format_law_context(law_data: list[dict]) -> str:
    """
    검색된 법령 목록을 안전하게 문자열로 포맷한다.
    누락 키에 대비해 .get()과 기본값을 사용하고, 링크가 없으면 '없음'으로 표시한다.
    """
    if not law_data:
        return "관련 법령 검색 결과가 없습니다."

    rows = []
    normalizer = globals().get("normalize_law_link")  # 선택적: 있으면 링크 정규화

    for i, law in enumerate(law_data, 1):
        if not isinstance(law, dict):
            rows.append(f"{i}. (알 수 없는 항목)")
            continue

        name = law.get("법령명") or law.get("법령명한글") or law.get("title") or "(제목 없음)"
        kind = law.get("법령구분") or law.get("kind") or "-"
        dept = law.get("소관부처명") or law.get("부처명") or "-"
        eff  = law.get("시행일자") or law.get("effective_date") or "-"
        pub  = law.get("공포일자") or law.get("promulgation_date") or "-"

        link = (
            law.get("법령상세링크")
            or law.get("상세링크")
            or law.get("detail_url")
            or ""
        )
        if callable(normalizer) and link:
            try:
                link = normalizer(link) or link
            except Exception:
                pass

        rows.append(
            f"{i}. {name} ({kind})\n"
            f"   - 소관부처: {dept}\n"
            f"   - 시행일자: {eff} / 공포일자: {pub}\n"
            f"   - 링크: {link if link else '없음'}"
        )

    return "\n\n".join(rows) if rows else "관련 법령 검색 결과가 없습니다."



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
#from modules import AdviceEngine, Intent, classify_intent, pick_mode, build_sys_for_mode  # noqa: F401

# 2) 엔진 생성 (한 번만)
#engine = None
#try:
    # 아래 객체들은 app.py 상단에서 이미 정의되어 있어야 합니다.
    # - client, AZURE, TOOLS
    # - safe_chat_completion
    # - tool_search_one, tool_search_multi
    # - prefetch_law_context, _summarize_laws_for_primer
    #if client and AZURE and TOOLS:
     #   engine = AdviceEngine(
      #      client=client,
       #     model=AZURE["deployment"],
        #    tools=TOOLS,
          #  safe_chat_completion=safe_chat_completion,
           # tool_search_one=tool_search_one,
 #           tool_search_multi=tool_search_multi,
  #          prefetch_law_context=prefetch_law_context,            # 있으면 그대로
   #         summarize_laws_for_primer=_summarize_laws_for_primer, # 있으면 그대로
    #        temperature=0.2,
        #)
#except NameError:
    # 만약 위 객체들이 아직 정의되기 전 위치라면,
    # 이 패치를 해당 정의 '아래'로 옮겨 붙이세요.
 #   pass

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
    
render_api_diagnostics()   

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
    for i, m in enumerate(st.session_state.get("messages", [])):
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

        with st.chat_message(role):
            if role == "assistant":
                render_bubble_with_copy(content, key=f"past-{i}")

        # 안전하게 꺼내기
                laws = (m.get("law") or []) if isinstance(m, dict) else []
                if laws:
                    with st.expander("📋 이 턴에서 참고한 법령 요약"):
                        for j, law in enumerate(laws, 1):
                            if not isinstance(law, dict):
                                continue

                            name = law.get('법령명') or law.get('법령명한글') or law.get('title') or '(제목 없음)'
                            kind = law.get('법령구분') or law.get('kind') or '-'
                            eff  = law.get('시행일자') or law.get('effective_date') or '-'
                            pub  = law.get('공포일자') or law.get('promulgation_date') or '-'
                            st.write(f"**{j}. {name}** ({kind})  | 시행 {eff}  | 공포 {pub}")

                            link = law.get('법령상세링크') or law.get('상세링크') or law.get('detail_url') or ''
                            if link:
                                st.write(f"- 링크: {link}")
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
# 🔽 대화가 시작된 뒤에만 우측 패널 노출
# ✅ 로딩(스트리밍) 중에는 패널을 렌더링하지 않음
if chat_started and not st.session_state.get("__answering__", False):
    q_for_panel, ans_for_panel = _current_q_and_answer()

    # 함수들이 파일의 더 아래에서 정의되어 있을 수 있으므로 안전 가드
    _ext_names = globals().get("extract_law_names_from_answer")
    _ext_arts  = globals().get("extract_article_pairs_from_answer")

    hints = _ext_names(ans_for_panel) if (_ext_names and ans_for_panel) else None
    arts  = _ext_arts(ans_for_panel)  if (_ext_arts  and ans_for_panel) else None

    render_search_flyout(
        q_for_panel or user_q,
        num_rows=8,
        hint_laws=hints,
        hint_articles=arts,   # ← 조문 힌트도 함께 전달
        show_debug=SHOW_SEARCH_DEBUG,
    )


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
            stream_box.markdown("_AI가 질의를 해석하고, 국가법령정보 DB를 검색 중입니다._")

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
        # (추가) 사용자가 '본문/원문/요약하지 말' 요청 + '제n조'가 있으면 DRF 본문을 강제 인용
from modules.law_fetch import fetch_article_block_by_mst  # 안전하게 여기서 임포트해도 OK
import re




if re.search(r'(본문|원문|요약\s*하지\s*말)', user_q or '', re.I):
    m = re.search(r'제\d{1,4}조(의\d{1,3})?', user_q or '')
    if m and collected_laws:
        want_article = m.group(0)

        # 1) 후보 중 '법령명' 매칭 강화 (공백 제거·양방향 contains)
        def _nm(it: dict) -> str:
            return (it.get('법령명') or it.get('법령명한글') or '').replace(' ', '').strip()

        uq = (user_q or '').replace(' ', '')
        # 질문에서 '...법' 토큰 하나 추출해 힌트로 사용
        m_name = re.search(r'([가-힣0-9·\s]+법)', user_q or '')
        hint = (m_name.group(1).replace(' ', '') if m_name else '')

        law_pick = next(
            (it for it in collected_laws
             if (_nm(it) and ((hint and hint in _nm(it)) or (_nm(it) in uq) or (uq in _nm(it))))),
            collected_laws[0]
        )

        # 2) 법령명으로 DRF 링크 → MST 추출 (정확도 우선)
        mst_from_name = ''
        if hint:
            try:
                from modules.linking import fetch_drf_law_link_by_name
                from urllib.parse import urlsplit, parse_qsl
                drf_url = fetch_drf_law_link_by_name(hint)  # DRF 메인 링크 (쿼리에 MST 포함)
                if drf_url:
                    qs = dict(parse_qsl(urlsplit(drf_url).query))
                    mst_from_name = (qs.get('MST') or qs.get('mst') or '').strip()
            except Exception:
                mst_from_name = ''

        # 3) 우선 mst_from_name 사용, 없으면 law_pick에서 폴백
        mst = mst_from_name or (law_pick.get('MST') or law_pick.get('법령ID') or law_pick.get('법령일련번호') or '').strip()
        if mst:
            eff = (law_pick.get('시행일자') or law_pick.get('공포일자') or '').strip().replace('-', '') or None
            body, link = fetch_article_block_by_mst(mst, want_article, prefer='JSON', efYd=eff)
            if body:
                head = f"### 요청하신 {want_article}\n\n"
                if link:
                    head += f"[법제처 원문 보기]({link})\n\n"
                # DRF에서 가져온 원문을 답변 맨 위에 그대로 인용
                base_text = head + "```\n" + body + "\n```\n\n" + (base_text or "")


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

