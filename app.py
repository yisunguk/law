# app.py — POSCO E&C Law Chat (stable, secrets-based)

import os
import time
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests
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
def law_search(keyword: str) -> List[str]:
    """법제처 간단 검색 → 리스트[str]"""
    if not LAW_API_KEY:
        return []
    try:
        url = "http://www.law.go.kr/DRF/lawSearch.do"
        params = {"OC": LAW_API_KEY, "target": "law", "query": keyword, "type": "XML"}
        res = requests.get(url, params=params, timeout=15)  # 타임아웃 증가
        
        if res.status_code != 200 or not res.text.strip():
            return []
        
        # XML 응답 디버깅을 위한 로그
        response_text = res.text.strip()
        if not response_text.startswith('<?xml') and not response_text.startswith('<'):
            st.warning(f"법제처 API가 XML이 아닌 응답을 반환했습니다: {response_text[:100]}...")
            return []
        
        try:
            import xml.etree.ElementTree as ET
            # XML 파싱 시도
            root = ET.fromstring(response_text)
            
            # 다양한 XML 구조 시도
            hits = []
            
            # 방법 1: 기본 law 태그 검색
            law_items = root.findall(".//law")
            if law_items:
                for item in law_items:
                    title = item.findtext("법령명한글") or item.findtext("법령명") or ""
                    date = item.findtext("시행일자") or item.findtext("시행일") or ""
                    if title:
                        hits.append(f"- {title} (시행일자: {date})")
            
            # 방법 2: 다른 가능한 태그들 검색
            if not hits:
                for tag_name in ["법령", "law", "item", "result"]:
                    items = root.findall(f".//{tag_name}")
                    if items:
                        for item in items:
                            # 모든 하위 태그에서 제목과 날짜 찾기
                            title = ""
                            date = ""
                            for child in item:
                                if "명" in child.tag or "title" in child.tag.lower():
                                    title = child.text or ""
                                elif "일" in child.tag or "date" in child.tag.lower():
                                    date = child.text or ""
                            
                            if title:
                                hits.append(f"- {title} (시행일자: {date})")
                        break
            
            # 방법 3: 텍스트 기반 검색 (XML 파싱이 실패한 경우)
            if not hits:
                # XML 태그를 제거하고 텍스트만 추출
                import re
                clean_text = re.sub(r'<[^>]+>', '', response_text)
                lines = clean_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 5 and ('법' in line or '규정' in line or '조례' in line):
                        hits.append(f"- {line}")
            
            return hits[:5]
            
        except ET.ParseError as xml_error:
            st.warning(f"XML 파싱 오류: {str(xml_error)}")
            # XML 파싱 실패 시 텍스트 기반 검색 시도
            import re
            clean_text = re.sub(r'<[^>]+>', '', response_text)
            lines = clean_text.split('\n')
            hits = []
            for line in lines:
                line = line.strip()
                if line and len(line) > 5 and ('법' in line or '규정' in line or '조례' in line):
                    hits.append(f"- {line}")
            return hits[:5]
            
    except Exception as e:
        st.warning(f"법제처 API 검색 중 오류: {str(e)}")
        return []

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