# app.py (stable full version)

import os
import time
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any

import requests
import streamlit as st
from openai import AzureOpenAI

# ============== Page & Env ==============
st.set_page_config(page_title="법제처 AI 챗봇", page_icon="⚖️", layout="wide")

AZURE_OPENAI_API_BASE = os.getenv("AZURE_OPENAI_API_BASE", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")

FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")

# ============== Firebase (optional) ==============
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:
    firebase_admin = None

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

# ============== Style ==============
st.markdown(
    """
<style>
* {font-family: -apple-system, system-ui, Segoe UI, Roboto, 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif}
.chat-header {
  text-align:center; padding:2rem 0; margin-bottom:1.25rem;
  color:white; border-radius:14px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.chat-history-item {
  background:#2b2d31; color:#e6e6e6;
  padding:.7rem; margin:.4rem 0; border-radius:10px;
  border-left:3px solid #667eea; font-size:.9rem;
}
.chat-history-item:hover { background:#3a3c42 }
div[data-testid="stChatInput"] textarea {
  min-height:110px; font-size:18px; line-height:1.5;
}
.block-container { padding-bottom: 6rem; }

/* Chat input가 다른 요소에 가려지지 않도록 보장 */
div[data-testid="stChatInput"] {
  position: sticky;  /* 기본 값 유지 + 컨텍스트에 고정 */
  bottom: 0;
  z-index: 9999 !important;   /* 최상위로 올림 */
}
/* 혹시 상위 요소가 pointer-events를 막는 경우 대비 */
div[data-testid="stChatInput"], 
div[data-testid="stChatInput"] * {
  pointer-events: auto !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ============== Header ==============
st.markdown(
    """
<div class="chat-header">
  <h1>⚖️ 법제처 AI 챗봇</h1>
  <p>법제처 공식 데이터 + Azure OpenAI + Firebase 대화 메모리</p>
</div>
""",
    unsafe_allow_html=True,
)

# ============== Session ==============
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []
if "thread_id" not in st.session_state:
    # querystring t 로 복원 (신/구 API 호환)
    t = ""
    try:
        t = st.query_params.get("t", "")
    except Exception:
        qp = st.experimental_get_query_params() or {}
        t = qp.get("t", [""])
        t = t[0] if isinstance(t, list) else t
    st.session_state.thread_id = t or uuid.uuid4().hex[:12]

# 복원
restored = load_thread(st.session_state.thread_id)
if restored:
    st.session_state.messages = restored

# ============== Utilities ==============
def law_search(keyword: str):
    """법제처 간단 검색 → 리스트[str]"""
    try:
        url = "http://www.law.go.kr/DRF/lawSearch.do"
        params = {"OC": os.getenv("MOLEG_OC", ""), "target": "law", "query": keyword, "type": "XML"}
        res = requests.get(url, params=params, timeout=10)
        if res.status_code != 200:
            return []
        import xml.etree.ElementTree as ET
        root = ET.fromstring(res.text)
        hits = []
        for item in root.findall(".//law"):
            title = item.findtext("법령명한글") or ""
            date = item.findtext("시행일자") or ""
            if title:
                hits.append(f"- {title} (시행일자: {date})")
        return hits[:5]
    except Exception:
        return []

def law_context_str(hits: List[str]) -> str:
    return "\n".join(hits) if hits else "관련 검색 결과가 없습니다."

def get_client():
    if not AZURE_OPENAI_API_BASE or not AZURE_OPENAI_API_KEY:
        return None
    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_API_BASE,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
    )

client = get_client()

# ============== Sidebar ==============
with st.sidebar:
    st.subheader("대화 관리")
    c1, c2 = st.columns(2)
    if c1.button("새 대화 시작", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = uuid.uuid4().hex[:12]
        st.rerun()
    if c2.button("요약 저장", use_container_width=True):
        st.success("요약 저장 완료!")

    # Thread ID/URL 표시는 요청에 따라 숨김

    st.markdown("---")
    st.markdown("#### 대화 히스토리(최근)")
    for m in st.session_state.messages[-8:]:
        role = "사용자" if m.get("role") == "user" else "AI"
        preview = (m.get("content", "") or "").replace("\n", " ")[:42]
        st.markdown(f'<div class="chat-history-item">{role}: {preview}...</div>', unsafe_allow_html=True)

# ============== Render history ==============
for m in st.session_state.messages:
    role = m.get("role", "assistant")
    with st.chat_message(role if role in ("user", "assistant") else "assistant"):
        st.markdown(m.get("content", ""))

# ============== Input & Response ==============
user_q = st.chat_input("법령에 대한 질문을 입력하세요... (Enter로 전송)")

if user_q:
    ts = time.time()
    # 사용자 메시지
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
    save_message(st.session_state.thread_id, {"role": "user", "content": user_q, "ts": ts})

    with st.chat_message("user"):
        st.markdown(user_q)

    # 컨텍스트/버퍼 **사전 초기화** (재실행 안전)
    ctx: str = ""
    assistant_full: str = ""

    # 보조 컨텍스트(법령 검색)
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

    # 어시스턴트(스트리밍: placeholder 방식으로 통일)
    with st.chat_message("assistant"):
        placeholder = st.empty()

        if client is None:
            assistant_full = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + ctx
            placeholder.markdown(assistant_full)
        else:
            try:
                stream = client.chat.completions.create(
                    model=AZURE_OPENAI_DEPLOYMENT,
                    messages=history_for_model,
                    temperature=0.3,
                    top_p=1.0,
                    stream=True,
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
                # 최종 반영
                assistant_full = "".join(buf)
            except Exception as e:
                assistant_full = f"답변 생성 중 오류가 발생했습니다: {e}\n\n{ctx}"
                placeholder.markdown(assistant_full)

    # 저장
    st.session_state.messages.append({"role": "assistant", "content": assistant_full, "ts": time.time()})
    save_message(st.session_state.thread_id, {"role": "assistant", "content": assistant_full, "ts": time.time()})
