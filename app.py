# app.py — POSCO E&C Law Chat (stable, secrets-based)

import os
import time
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests
import xml.etree.ElementTree as ET
import streamlit as st
from openai import AzureOpenAI

# =========================
# Page
# =========================
st.set_page_config(page_title="법제처 AI 챗봇", page_icon="⚖️", layout="wide")

# =========================
# Secrets (필수 설정 읽기)
# =========================
def _get_secret(path: list, default=None):
    try:
        base = st.secrets
        for p in path:
            base = base[p]
        return base
    except Exception:
        return default

# 법제처 DRF OC
LAW_API_KEY = _get_secret(["LAW_API_KEY"], "")

# Azure OpenAI
AZURE_OPENAI_API_KEY   = _get_secret(["azure_openai", "api_key"], "")
AZURE_OPENAI_API_BASE  = _get_secret(["azure_openai", "endpoint"], "")
AZURE_OPENAI_DEPLOYMENT= _get_secret(["azure_openai", "deployment"], "")
AZURE_OPENAI_API_VERSION = _get_secret(["azure_openai", "api_version"], "2024-06-01")

# Firebase
FIREBASE_CONFIG = _get_secret(["firebase"], None)

# =========================
# Firebase (optional)
# =========================
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:
    firebase_admin = None
    firestore = None

def init_firebase():
    if firebase_admin is None or FIREBASE_CONFIG is None:
        return None
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(dict(FIREBASE_CONFIG))  # secrets dict 그대로 사용
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_CONFIG["project_id"]})
        return firestore.client()
    except Exception:
        return None

db = init_firebase()

def _threads_col():
    return None if db is None else db.collection("threads")

def load_thread(thread_id: str) -> List[Dict[str, Any]]:
    if db is None:
        return []
    try:
        docs = (
            _threads_col()
            .document(thread_id)
            .collection("messages")
            .order_by("ts")
            .stream()
        )
        return [d.to_dict() for d in docs]
    except Exception:
        return []

def save_message(thread_id: str, msg: Dict[str, Any]):
    if db is None:
        return
    try:
        _threads_col().document(thread_id).set(
            {"updated_at": datetime.utcnow().isoformat()}, merge=True
        )
        _threads_col().document(thread_id).collection("messages").add(
            {**msg, "ts": msg.get("ts", time.time())}
        )
    except Exception:
        pass

# =========================
# Styles (minimal & safe)
# =========================
st.markdown(
    """
<style>
* {font-family: -apple-system, system-ui, Segoe UI, Roboto, 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif}

/* 헤더 */
.chat-header {
  text-align:center; padding:2rem 0; margin-bottom:1.25rem;
  color:white; border-radius:14px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

/* 사이드바 히스토리 (다크톤) */
.chat-history-item {
  background:#2b2d31; color:#e6e6e6;
  padding:.7rem; margin:.4rem 0; border-radius:10px;
  border-left:3px solid #667eea; font-size:.9rem;
}
.chat-history-item:hover { background:#3a3c42 }

/* ===== 커스텀 입력창 ===== */
#chatbar {
  position: fixed; left: 50%; bottom: 16px; transform: translateX(-50%);
  width: 960px; max-width: 95vw;
  background: #111418; border: 1px solid #32363b; border-radius: 24px;
  box-shadow: 0 8px 20px rgba(0,0,0,.25);
  z-index: 9999;
}
#chatbar .row { display:flex; gap:12px; align-items:center; padding:12px 14px; }
#chatbar textarea {
  width: 100%; background: #2a2d33; color:#e8eaed;
  border: 1px solid #3a3f45; border-radius: 18px; padding: 12px 14px;
  min-height: 110px; font-size: 16px; line-height: 1.5; resize: none;
}
#chatbar button {
  min-width: 76px; height: 40px; border-radius: 12px; border: 1px solid #4b5563;
  background: #3b82f6; color: white; font-weight: 600; cursor: pointer;
}
#chatbar button:hover { filter: brightness(1.05); }

/* 본문이 입력창에 가리지 않게 하단 여백 확보 */
.block-container { padding-bottom: 180px; }
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# Header
# =========================
st.markdown(
    """
<div class="chat-header">
  <h1>⚖️ 법제처 AI 챗봇</h1>
  <p>법제처 공식 데이터 + Azure OpenAI + Firebase 대화 메모리</p>
</div>
""",
    unsafe_allow_html=True,
)

# =========================
# Session
# =========================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []

def _get_thread_id_from_query() -> str:
    try:
        q = st.query_params or {}
        t = q.get("t", "")
        return t if isinstance(t, str) else (t[0] if t else "")
    except Exception:
        qp = st.experimental_get_query_params() or {}
        t = qp.get("t", [""])
        return t[0] if isinstance(t, list) else t

if "thread_id" not in st.session_state:
    st.session_state.thread_id = _get_thread_id_from_query() or uuid.uuid4().hex[:12]

# 과거 대화 복원
restored = load_thread(st.session_state.thread_id)
if restored:
    st.session_state.messages = restored

# =========================
# Utilities
# =========================

def law_search(keyword: str, rows: int = 5) -> List[str]:
    """국가법령 검색
    우선순위 1) 공공데이터포털(apis.data.go.kr, ServiceKey/XML) → 2) DRF(law.go.kr, OC/XML) 폴백
    반환: "- 제목 (시행일자: YYYYMMDD)" 최대 rows개
    """
    rows = max(1, min(int(rows or 5), 20))

    def _warn(msg: str, sample: str = ""):
        from textwrap import shorten
        st.warning(msg + (f" : {shorten(sample.strip(), width=160)}" if sample else ""))

    def _is_html(t: str) -> bool:
        t = (t or "").lstrip().lower()
        return t.startswith("<!doctype html") or t.startswith("<html")

    def _parse_xml(xml_text: str) -> List[str]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as pe:
            _warn(f"XML 파싱 오류: {pe}")
            return []
        rc = (root.findtext('.//resultCode') or '').strip()
        if rc and rc != '00':
            msg = (root.findtext('.//resultMsg') or '').strip()
            code_map = {'01':'잘못된 요청 파라미터','02':'인증키 오류','03':'필수 파라미터 누락','09':'일시적 시스템 오류','99':'정의되지 않은 오류'}
            _warn(f"API 오류(resultCode={rc}): {code_map.get(rc, msg or '오류')}")
            return []
        hits = []
        for node in root.findall('.//law'):
            title = (node.findtext('법령명한글') or node.findtext('법령명') or '').strip()
            date  = (node.findtext('시행일자') or node.findtext('공포일자') or '').strip()
            if title:
                hits.append(f"- {title} (시행일자: {date})")
        return hits[:rows]

    # 1) 공공데이터포털 (ServiceKey — 반드시 Decoding 값을 사용)
    if DATA_PORTAL_SERVICE_KEY:
        try:
            base = 'https://apis.data.go.kr/1170000/law/lawSearchList.do'
            params = {
                'serviceKey': DATA_PORTAL_SERVICE_KEY,
                'ServiceKey': DATA_PORTAL_SERVICE_KEY,
                'target': 'law',
                'query' : keyword or '*',
                'numOfRows': rows,
                'pageNo': 1,
            }
            res = requests.get(base, params=params, timeout=15)
            ctype = (res.headers.get('Content-Type') or '').lower()
            txt = res.text or ''
            if res.status_code != 200:
                _warn(f"공공데이터포털 오류(code={res.status_code})", txt)
            elif 'xml' in ctype or txt.strip().startswith('<'):
                if _is_html(txt):
                    _warn("공공데이터포털이 HTML(사람용 페이지)을 반환했습니다. ServiceKey/쿼터/파라미터를 확인하세요.", txt)
                else:
                    hits = _parse_xml(txt)
                    if hits:
                        return hits
            else:
                _warn(f"공공데이터포털이 XML이 아닌 응답을 반환했습니다(Content-Type={ctype})", txt)
        except Exception as e:
            _warn(f"공공데이터포털 호출 오류: {e}")

    # 2) DRF 폴백 (OC 키 — type=XML)
    if LAW_API_KEY:
        try:
            url = 'http://www.law.go.kr/DRF/lawSearch.do'
            params = {'OC': LAW_API_KEY, 'target': 'law', 'query': keyword, 'type': 'XML'}
            res = requests.get(url, params=params, timeout=15)
            ctype = (res.headers.get('Content-Type') or '').lower()
            txt = res.text or ''
            if res.status_code != 200:
                _warn(f"법제처 DRF 오류(code={res.status_code})", txt)
            elif 'xml' in ctype or txt.strip().startswith('<'):
                if _is_html(txt):
                    _warn("법제처 DRF가 HTML(오류 페이지)을 반환했습니다. OC 키/쿼터/파라미터를 확인하세요.", txt)
                else:
                    hits = _parse_xml(txt)
                    if hits:
                        return hits
            else:
                _warn(f"법제처 DRF가 XML이 아닌 응답을 반환했습니다(Content-Type={ctype})", txt)
        except Exception as e:
            _warn(f"법제처 DRF 호출 오류: {e}")

    return []

def law_context_str(hits: List[str]) -> str:
    return "\n".join(hits) if hits else "관련 검색 결과가 없습니다."
def law_context_str(hits: List[str]) -> str:
    return "\n".join(hits) if hits else "관련 검색 결과가 없습니다."
def law_context_str(hits: List[str]) -> str:
    return "\n".join(hits) if hits else "관련 검색 결과가 없습니다."

def get_client() -> Optional[AzureOpenAI]:
    """Azure OpenAI 클라이언트 생성 및 검증"""
    if not all([AZURE_OPENAI_API_BASE, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT]):
        missing = []
        if not AZURE_OPENAI_API_BASE: missing.append("endpoint")
        if not AZURE_OPENAI_API_KEY: missing.append("api_key")
        if not AZURE_OPENAI_DEPLOYMENT: missing.append("deployment")
        st.error(f"Azure OpenAI 설정 누락: {', '.join(missing)}")
        return None
    
    try:
        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_API_BASE,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
        # 간단한 연결 테스트
        return client
    except Exception as e:
        st.error(f"Azure OpenAI 연결 실패: {str(e)}")
        return None

client = get_client()

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.subheader("대화 관리")
    c1, c2 = st.columns(2)
    if c1.button("새 대화 시작", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = uuid.uuid4().hex[:12]
        st.rerun()
    if c2.button("요약 저장", use_container_width=True):
        st.success("요약 저장 완료!")

    # Thread ID/URL 표시는 숨김

    st.markdown("---")
    st.markdown("#### 대화 히스토리(최근)")
    for m in st.session_state.messages[-8:]:
        role = "사용자" if m.get("role") == "user" else "AI"
        preview = (m.get("content", "") or "").replace("\n", " ")[:42]
        st.markdown(f'<div class="chat-history-item">{role}: {preview}...</div>', unsafe_allow_html=True)

# =========================
# Render history
# =========================
for m in st.session_state.messages:
    role = m.get("role", "assistant")
    with st.chat_message(role if role in ("user", "assistant") else "assistant"):
        st.markdown(m.get("content", ""))

# 환경 경고 배너(선택적)
if not client:
    st.info("Azure OpenAI 설정이 없으면 기본 안내만 표시됩니다. (Secrets에 api_key/endpoint/deployment/api_version 확인)")

# =========================
# Custom chat bar (form)
# =========================
chatbar = st.empty()
with chatbar.container():
    st.markdown(
        """
        <div id="chatbar">
          <div class="row">
            <span style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:8px;background:#f59e0b;color:#111;font-weight:900">⚖️</span>
            <div style="flex:1">
        """,
        unsafe_allow_html=True,
    )

    # clear_on_submit=True → 제출 후 자동 초기화
    with st.form("chat_form", clear_on_submit=True):
        user_text = st.text_area(
            label="",
            key="draft_input",
            placeholder="법령에 대한 질문을 입력하세요... (Shift+Enter: 줄바꿈, Enter: 전송)",
            height=110,
        )
        cols = st.columns([1, 6])
        with cols[0]:
            submitted = st.form_submit_button("보내기")
        with cols[1]:
            st.caption("Shift+Enter로 줄바꿈, Enter로 전송")

    st.markdown(
        """
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================
# Handle submit
# =========================
if submitted:
    user_q = (user_text or "").strip()
    if user_q:
        ts = time.time()

        # 사용자 메시지
        st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
        save_message(st.session_state.thread_id, {"role": "user", "content": user_q, "ts": ts})

        with st.chat_message("user"):
            st.markdown(user_q)

        # 컨텍스트/버퍼 초기화
        ctx: str = ""
        assistant_full: str = ""

        # 보조 컨텍스트
        with st.spinner("법령 검색 중..."):
            hits = law_search(user_q)
            ctx = law_context_str(hits)

        # 모델 히스토리
        history_for_model = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[-12:]
        ]
        history_for_model.append(
            {
                "role": "user",
                "content": f"""사용자 질문: {user_q}

관련 법령 정보(요약):
{ctx}

요청: 위 법령 검색 결과를 참고해 질문에 답하세요.
필요하면 관련 조문도 함께 제시하세요.
한국어로 쉽게 설명하세요.""",
            }
        )

        # 어시스턴트(스트리밍: placeholder)
        with st.chat_message("assistant"):
            placeholder = st.empty()

            if client is None:
                assistant_full = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + ctx
                placeholder.markdown(assistant_full)
            else:
                try:
                    with st.spinner("AI 답변 생성 중..."):
                        stream = client.chat.completions.create(
                            model=AZURE_OPENAI_DEPLOYMENT,   # 배포 이름 그대로
                            messages=history_for_model,
                            temperature=0.3,
                            top_p=1.0,
                            stream=True,
                            timeout=60,  # 타임아웃 설정
                        )
                        buf = []
                        for ch in stream:
                            piece = ""
                            try:
                                piece = ch.choices[0].delta.get("content", "")
                            except Exception:
                                pass
                            if piece:
                                buf.append(piece)
                                assistant_full = "".join(buf)
                                placeholder.markdown(assistant_full)
                        assistant_full = "".join(buf)
                except Exception as e:
                    error_msg = f"답변 생성 중 오류가 발생했습니다: {str(e)}"
                    if "timeout" in str(e).lower():
                        error_msg = "응답 시간이 초과되었습니다. 다시 시도해주세요."
                    elif "rate limit" in str(e).lower():
                        error_msg = "API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
                    elif "authentication" in str(e).lower():
                        error_msg = "인증 오류가 발생했습니다. API 키를 확인해주세요."
                    
                    assistant_full = f"{error_msg}\n\n{ctx}"
                    placeholder.markdown(assistant_full)
                    st.error(f"상세 오류: {str(e)}")

        # 저장
        st.session_state.messages.append({"role": "assistant", "content": assistant_full, "ts": time.time()})
        save_message(st.session_state.thread_id, {"role": "assistant", "content": assistant_full, "ts": time.time()})

# =========================
# JavaScript for keyboard shortcuts
# =========================
st.markdown(
    """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        const textarea = document.querySelector('textarea[data-testid="stTextArea"]');
        if (textarea) {
            textarea.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const form = textarea.closest('form');
                    if (form) {
                        const submitButton = form.querySelector('button[type="submit"]');
                        if (submitButton) {
                            submitButton.click();
                        }
                    }
                }
            });
        }
    });
    </script>
    """,
    unsafe_allow_html=True
)