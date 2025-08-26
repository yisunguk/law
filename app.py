
from __future__ import annotations

import time
import streamlit as st

# ---------------- Page setup ----------------
st.set_page_config(page_title="법무 상담사", page_icon="⚖️", layout="wide")

# --------------- Session state ---------------
if "messages" not in st.session_state:
    st.session_state["messages"] = []  # [{"role":"user"/"assistant","content":str}]
if "_pending_user_q" not in st.session_state:
    st.session_state["_pending_user_q"] = None
if "_pending_user_files" not in st.session_state:
    st.session_state["_pending_user_files"] = []

# --------------- Conversation starters ---------------
STARTERS_DEFAULT = [
    "민법 제839조의2 재산분할 기준 알려줘",
    "주택임대차보호법 보증금 우선변제권 요건은?",
    "개인정보 보호법 유출 통지의무와 과징금은?",
    "교통사고처리 특례법 적용 대상과 처벌 수위는?",
    "근로기준법 연차휴가 미사용수당 계산 방법은?",
]

def render_conversation_starters(starters=STARTERS_DEFAULT, key_prefix="pre"):
    if not starters:
        return
    st.markdown('<div class="starter-title">💡 자주 묻는 질문</div>', unsafe_allow_html=True)
    cols = st.columns(min(5, max(1, len(starters))))
    for i, txt in enumerate(starters):
        col = cols[i % len(cols)]
        if col.button(txt, key=f"{key_prefix}_starter_{i}", use_container_width=True):
            st.session_state["_pending_user_q"] = txt.strip()
            st.session_state["_pending_user_files"] = []
            st.session_state["_pending_user_nonce"] = time.time_ns()
            st.rerun()

# --------------- Helper: push pending to chat ---------------
def push_user_from_pending():
    """Move the pending question into the chat and create a demo assistant reply.
    Replace the assistant generation with your real back-end call.
    """
    q = st.session_state.get("_pending_user_q")
    if not q:
        return
    st.session_state["messages"].append({"role": "user", "content": q})
    # --- Demo assistant reply (replace with your LLM / 법제처 API call) ---
    reply = (
        "요청하신 주제에 대해 확인했습니다. 이 데모 빌드에서는 예시 답변만 제공합니다.\\n\\n"
        f"**질문:** {q}\\n\\n"
        "- 실제 서비스에서는 국가법령정보 API 조회·요약이 여기에 표시됩니다.\\n"
        "- 파일을 첨부하셨다면 해당 파일도 함께 분석합니다."
    )
    st.session_state["messages"].append({"role": "assistant", "content": reply})
    # clear pending
    st.session_state["_pending_user_q"] = None
    st.session_state["_pending_user_files"] = []

# --------------- Styles ---------------
st.markdown(
    """
    <style>
      .center-hero {max-width: 820px; margin: 0 auto;}
      .starter-title{font-size:13px; color:#9aa0a6; margin:6px 2px 8px;}
      .post-chat-ui{max-width: 820px; margin: 16px auto 0;}
      .stChatMessage {max-width: 820px; margin-left:auto; margin-right:auto;}
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------- UI blocks ---------------
def render_pre_chat_center():
    st.markdown('<section class="center-hero">', unsafe_allow_html=True)
    st.markdown(
        '<h1 style="font-size:38px;font-weight:800;letter-spacing:-.5px;margin-bottom:20px;">무엇을 도와드릴까요?</h1>',
        unsafe_allow_html=True,
    )
    st.caption("Drag and drop files here")
    st.file_uploader(
        "Drag and drop files here",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="first_files",
        label_visibility="collapsed",
    )
    with st.form("first_ask", clear_on_submit=True):
        q = st.text_input("질문을 입력해 주세요...", key="first_input")
        sent = st.form_submit_button("전송", use_container_width=True)
    # conversation starters below input
    render_conversation_starters(key_prefix="pre")
    st.markdown("</section>", unsafe_allow_html=True)

    if sent and (q or "").strip():
        st.session_state["_pending_user_q"] = q.strip()
        st.session_state["_pending_user_nonce"] = time.time_ns()
        st.rerun()

def render_post_chat_simple_ui():
    st.markdown('<section class="post-chat-ui">', unsafe_allow_html=True)
    st.file_uploader(
        "Drag and drop files here",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="post_files",
    )
    with st.form("next_ask", clear_on_submit=True):
        q = st.text_input("질문을 입력해 주세요...", key="next_input")
        sent = st.form_submit_button("전송", use_container_width=True)
    # conversation starters below input
    render_conversation_starters(key_prefix="post")
    st.markdown("</section>", unsafe_allow_html=True)

    if sent and (q or "").strip():
        st.session_state["_pending_user_q"] = (q or "").strip()
        st.session_state["_pending_user_nonce"] = time.time_ns()
        st.rerun()

# --------------- Main flow ---------------
# If a starter/submit set a pending question, push it into chat
if st.session_state.get("_pending_user_q"):
    push_user_from_pending()

# Show either pre-chat or conversation + post-chat input
if not st.session_state["messages"]:
    render_pre_chat_center()
else:
    # history
    for m in st.session_state["messages"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    # post-chat input & starters under it
    render_post_chat_simple_ui()
