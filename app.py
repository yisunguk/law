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

# 공공데이터포털 ServiceKey
DATA_PORTAL_SERVICE_KEY = _get_secret(["DATA_PORTAL_SERVICE_KEY"], "")

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
# Styles (ChatGPT 스타일)
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

/* ChatGPT 스타일 채팅 */
.chat-container {
  max-width: 800px; margin: 0 auto; padding: 0 1rem;
}

.chat-message {
  display: flex; margin: 1.5rem 0; align-items: flex-start;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.chat-avatar {
  width: 30px; height: 30px; border-radius: 50%; 
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; margin: 0 12px; flex-shrink: 0;
}

.chat-avatar.user {
  background: #10a37f; color: white;
}

.chat-avatar.assistant {
  background: #f7f7f8; color: #374151;
}

.chat-content {
  background: #f7f7f8; padding: 1rem; border-radius: 18px;
  max-width: 70%; word-wrap: break-word;
}

.chat-message.user .chat-content {
  background: #10a37f; color: white;
}

/* 입력창 */
.chat-input-container {
  position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  width: 90%; max-width: 800px; background: white;
  border: 1px solid #e5e7eb; border-radius: 24px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1); z-index: 1000;
}

.chat-input-wrapper {
  display: flex; align-items: flex-end; padding: 8px;
}

.chat-textarea {
  flex: 1; border: none; outline: none; resize: none;
  padding: 12px 16px; font-size: 16px; line-height: 1.5;
  min-height: 24px; max-height: 200px; border-radius: 20px;
  background: transparent;
}

.chat-send-button {
  background: #10a37f; color: white; border: none; border-radius: 50%;
  width: 40px; height: 40px; margin-left: 8px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background-color 0.2s;
}

.chat-send-button:hover {
  background: #0d8f6f;
}

.chat-send-button:disabled {
  background: #d1d5db; cursor: not-allowed;
}

/* 본문이 입력창에 가리지 않게 하단 여백 확보 */
.block-container { padding-bottom: 120px; }

/* 로딩 애니메이션 */
.typing-indicator {
  display: flex; align-items: center; gap: 4px; padding: 12px 16px;
}

.typing-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #9ca3af;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-dot:nth-child(1) { animation-delay: -0.32s; }
.typing-dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}
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
  <p>공공데이터포털 + Azure OpenAI + ChatGPT 스타일 인터페이스</p>
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
    """국가법령 검색 - 공공데이터포털 사용"""
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

    # 공공데이터포털 API 호출
    if not DATA_PORTAL_SERVICE_KEY:
        st.warning("공공데이터포털 ServiceKey가 설정되지 않았습니다.")
        return []
    
    try:
        base = 'https://apis.data.go.kr/1170000/law/lawSearchList.do'
        params = {
            'serviceKey': DATA_PORTAL_SERVICE_KEY,
            'target': 'law',
            'query': keyword or '*',
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

    st.markdown("---")
    st.markdown("#### 대화 히스토리(최근)")
    for m in st.session_state.messages[-8:]:
        role = "사용자" if m.get("role") == "user" else "AI"
        preview = (m.get("content", "") or "").replace("\n", " ")[:42]
        st.markdown(f'<div class="chat-history-item">{role}: {preview}...</div>', unsafe_allow_html=True)

# =========================
# Chat Container
# =========================
st.markdown('<div class="chat-container">', unsafe_allow_html=True)

# Render history
for m in st.session_state.messages:
    role = m.get("role", "assistant")
    is_user = role == "user"
    
    st.markdown(
        f"""
        <div class="chat-message {'user' if is_user else 'assistant'}">
          <div class="chat-avatar {'user' if is_user else 'assistant'}">
            {'👤' if is_user else '⚖️'}
          </div>
          <div class="chat-content">
            {m.get("content", "")}
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# 환경 경고 배너(선택적)
if not client:
    st.info("Azure OpenAI 설정이 없으면 기본 안내만 표시됩니다. (Secrets에 api_key/endpoint/deployment/api_version 확인)")

st.markdown('</div>', unsafe_allow_html=True)

# =========================
# Custom chat input (ChatGPT 스타일)
# =========================
chat_input = st.empty()
with chat_input.container():
    st.markdown(
        """
        <div class="chat-input-container">
          <div class="chat-input-wrapper">
            <textarea 
              id="chat-textarea" 
              class="chat-textarea" 
              placeholder="법령에 대한 질문을 입력하세요... (Shift+Enter: 줄바꿈, Enter: 전송)"
              rows="1"
            ></textarea>
            <button id="chat-send-btn" class="chat-send-button" onclick="sendMessage()">
              ➤
            </button>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# =========================
# JavaScript for ChatGPT-style input
# =========================
st.markdown(
    """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        const textarea = document.getElementById('chat-textarea');
        const sendBtn = document.getElementById('chat-send-btn');
        
        if (textarea && sendBtn) {
            // 자동 높이 조절
            textarea.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 200) + 'px';
            });
            
            // Enter로 전송, Shift+Enter로 줄바꿈
            textarea.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            // 전송 버튼 클릭
            window.sendMessage = function() {
                const message = textarea.value.trim();
                if (message) {
                    // Streamlit 세션에 메시지 전달
                    const event = new CustomEvent('streamlit:sendMessage', {
                        detail: { message: message }
                    });
                    window.dispatchEvent(event);
                    
                    // 입력창 초기화
                    textarea.value = '';
                    textarea.style.height = '24px';
                }
            };
        }
    });
    </script>
    """,
    unsafe_allow_html=True
)

# =========================
# Handle message submission
# =========================
# JavaScript 이벤트를 감지하여 메시지 처리
if st.button("테스트 전송", key="test_send", help="JavaScript 이벤트 테스트용"):
    st.info("JavaScript 이벤트가 정상 작동하는지 확인하세요.")

# 사용자 입력을 받는 Streamlit 폼 (임시)
with st.form("chat_form", clear_on_submit=True):
    user_text = st.text_area(
        label="",
        key="draft_input",
        placeholder="법령에 대한 질문을 입력하세요... (Shift+Enter: 줄바꿈, Enter: 전송)",
        height=100,
    )
    submitted = st.form_submit_button("보내기")

if submitted:
    user_q = (user_text or "").strip()
    if user_q:
        ts = time.time()

        # 사용자 메시지
        st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
        save_message(st.session_state.thread_id, {"role": "user", "content": user_q, "ts": ts})

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
        with st.spinner("AI 답변 생성 중..."):
            if client is None:
                assistant_full = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + ctx
            else:
                try:
                    stream = client.chat.completions.create(
                        model=AZURE_OPENAI_DEPLOYMENT,
                        messages=history_for_model,
                        temperature=0.3,
                        top_p=1.0,
                        stream=True,
                        timeout=60,
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
                    st.error(f"상세 오류: {str(e)}")

        # 저장
        st.session_state.messages.append({"role": "assistant", "content": assistant_full, "ts": time.time()})
        save_message(st.session_state.thread_id, {"role": "assistant", "content": assistant_full, "ts": time.time()})
        
        # 페이지 새로고침으로 메시지 표시
        st.rerun()