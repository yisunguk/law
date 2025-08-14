import os
import time
import json
import math
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import uuid
from typing import List, Dict, Any

import requests
import streamlit as st
from openai import AzureOpenAI

# Firebase
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:
    firebase_admin = None

# =============================
# 페이지 설정 & ChatGPT 스타일 UI
# =============================
st.set_page_config(
    page_title="법제처 AI 챗봇",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================
# 환경 설정
# =============================
AZURE_OPENAI_API_BASE = os.getenv("AZURE_OPENAI_API_BASE", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")

FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")

# =============================
# Firebase 초기화
# =============================
def init_firebase():
    if firebase_admin is None:
        return None
    if not FIREBASE_CREDENTIALS or not FIREBASE_PROJECT_ID:
        return None
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS))
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        return firestore.client()
    except Exception:
        return None

db = init_firebase()

# =============================
# 스타일
# =============================
st.markdown("""
<style>
    html, body { scroll-behavior: smooth; }

    /* 전체 폰트 */
    * { font-family: -apple-system, system-ui, Segoe UI, Roboto, 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif; }

    /* 메시지 버블 */
    .chat-message {
        margin: 1.5rem 0;
        padding: 1rem;
        border-radius: 18px;
        position: relative;
    }
    .user-message {
        background: #007bff;
        color: white;
        margin-left: 20%;
        border-radius: 18px 18px 4px 18px;
    }
    .assistant-message {
        background: #f8f9fa;
        color: #333;
        margin-right: 20%;
        border-radius: 18px 18px 18px 4px;
        border: 1px solid #e9ecef;
    }

    /* 입력창 스타일 - 크기 키움 (업데이트) */
    .stChatInput {
        position: fixed;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 960px;
        max-width: 95vw;
        background: white;
        padding: 1.5rem;
        border-top: 1px solid #e9ecef;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
        z-index: 1000;
        border-radius: 16px 16px 0 0;
    }
    /* 입력창 텍스트 영역 크기 키움 */
    .stChatInput textarea {
        border-radius: 20px;
        border: 2px solid #e9ecef;
        padding: 1rem 1.5rem;
        font-size: 18px;
        resize: none;
        min-height: 110px;
        line-height: 1.5;
    }

    /* 타이핑 인디케이터 */
    .typing-indicator {
        display: inline-block;
        width: 20px;
        height: 12px;
        background:
          radial-gradient(circle closest-side, #999 90%, #0000) 0%   50%/4px 4px,
          radial-gradient(circle closest-side, #999 90%, #0000) 50%  50%/4px 4px,
          radial-gradient(circle closest-side, #999 90%, #0000) 100% 50%/4px 4px;
        background-repeat: no-repeat;
        animation: typing 1s infinite linear;
    }
    @keyframes typing {
      0%   { background-position: 0% 50%, 50% 50%, 100% 50%; opacity: .2; }
      33%  { background-position: 0% 50%, 50% 20%, 100% 50%; opacity: .5; }
      66%  { background-position: 0% 50%, 50% 80%, 100% 50%; opacity: .8; }
      100% { background-position: 0% 50%, 50% 50%, 100% 50%; opacity: 1; }
    }

    /* 복사 버튼 */
    .copy-btn {
        position: absolute;
        top: 10px; right: 10px;
        padding: 4px 10px;
        border-radius: 10px;
        border: 1px solid #e9ecef;
        background: white;
        cursor: pointer;
        font-size: 12px;
    }
    .copy-btn:hover {
        background: #f1f3f5;
    }

    /* 하단 여백 */
    .bottom-spacer {
        height: 180px;
    }

    /* 사이드바 대화 히스토리 (다크톤) */
    .chat-history-item {
        background: #2b2d31;
        color: #e6e6e6;
        padding: 0.75rem;
        margin: 0.5rem 0;
        border-radius: 10px;
        border-left: 3px solid #667eea;
        font-size: 0.9rem;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .chat-history-item:hover {
        background: #3a3c42;
        transform: translateX(2px);
    }
    .chat-history-item.user { border-left-color: #007bff; }
    .chat-history-item.assistant { border-left-color: #28a745; }

    /* 헤더 */
    .chat-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 15px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# =============================
# 헤더
# =============================
st.markdown("""
<div class="chat-header">
    <h1>⚖️ 법제처 AI 챗봇</h1>
    <p>법제처 공식 데이터 + Azure OpenAI + Firebase 대화 메모리</p>
</div>
""", unsafe_allow_html=True)

# =============================
# 세션 상태
# =============================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []
if "thread_id" not in st.session_state:
    # URL 파라미터 t 로 복원
    t_from_url = st.query_params.get("t", [""])[0] if hasattr(st, "query_params") else ""
    st.session_state.thread_id = t_from_url or uuid.uuid4().hex[:12]
if "settings" not in st.session_state:
    st.session_state.settings = {
        "include_search": True,
        "law_search_endpoint": "http://www.law.go.kr/DRF/lawSearch.do",
    }

# =============================
# Firebase 유틸
# =============================
def _threads_col():
    if db is None:
        return None
    return db.collection("threads")

def load_thread(thread_id: str) -> List[Dict[str, Any]]:
    if db is None:
        return []
    try:
        msgs_ref = _threads_col().document(thread_id).collection("messages").order_by("ts")
        docs = msgs_ref.stream()
        return [d.to_dict() for d in docs]
    except Exception:
        return []

def save_message(thread_id: str, msg: Dict[str, Any]):
    if db is None:
        return
    try:
        _threads_col().document(thread_id).set({
            "updated_at": datetime.utcnow().isoformat()
        }, merge=True)
        _threads_col().document(thread_id).collection("messages").add({
            **msg,
            "ts": msg.get("ts", time.time())
        })
    except Exception:
        pass

def save_summary(thread_id: str, summary: str):
    if db is None:
        return
    try:
        _threads_col().document(thread_id).set({
            "summary": summary,
            "updated_at": datetime.utcnow().isoformat()
        }, merge=True)
    except Exception:
        pass

def get_summary(thread_id: str) -> str:
    if db is None:
        return ""
    try:
        doc = _threads_col().document(thread_id).get()
        data = doc.to_dict() if doc and doc.exists else {}
        return data.get("summary", "") if data else ""
    except Exception:
        return ""

# 과거 대화 복원
restored = load_thread(st.session_state.thread_id)
if restored:
    st.session_state.messages = restored

# =============================
# 법령 검색 유틸
# =============================
def law_search(keyword: str) -> Dict[str, Any]:
    """법제처 공개 API 간단 래핑"""
    try:
        params = {
            "OC": os.getenv("MOLEG_OC", ""),
            "target": "law",
            "query": keyword,
            "type": "XML",
        }
        url = st.session_state.settings["law_search_endpoint"]
        res = requests.get(url, params=params, timeout=10)
        used = res.url
        data = {}
        if res.status_code == 200 and res.text.strip():
            root = ET.fromstring(res.text)
            titles = []
            for item in root.findall(".//law"):
                title = item.findtext("법령명한글") or ""
                no = item.findtext("법령ID") or ""
                date = item.findtext("시행일자") or ""
                titles.append({"title": title, "id": no, "date": date})
            data["hits"] = titles[:5]
        return {"endpoint": used, "data": data, "error": None}
    except Exception as e:
        return {"endpoint": "", "data": {}, "error": str(e)}

def format_law_context(result: Dict[str, Any]) -> str:
    if not result or not result.get("data"):
        return "관련 검색 결과가 없습니다."
    hits = result["data"].get("hits", [])
    if not hits:
        return "관련 검색 결과가 없습니다."
    lines = []
    for h in hits:
        lines.append(f"- {h['title']} (시행일자: {h['date']})")
    return "\n".join(lines)

# =============================
# 모델 클라이언트
# =============================
def get_client():
    if not AZURE_OPENAI_API_BASE or not AZURE_OPENAI_API_KEY:
        return None
    client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_API_BASE,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION
    )
    return client

client = get_client()

# =============================
# 사이드바
# =============================
with st.sidebar:
    st.subheader("대화 관리")
    colA, colB = st.columns(2)
    with colA:
        if st.button("새 대화 시작", use_container_width=True):
            st.session_state.messages = []
            st.session_state.thread_id = uuid.uuid4().hex[:12]
            st.rerun()
    with colB:
        if st.button("요약 저장", use_container_width=True):
            long_summary = get_summary(st.session_state.thread_id)
            st.success("요약 저장 완료!" if long_summary else "저장할 요약이 없습니다.")

    # === Thread ID/URL 노출 제거(요청 반영) ===
    # st.caption(f"Thread ID: `{st.session_state.thread_id}`")
    # st.caption("URL에 `?t={thread_id}` 를 붙여 공유 가능")

    st.markdown
