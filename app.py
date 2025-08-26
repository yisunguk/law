
from __future__ import annotations

import time
import streamlit as st

# ---------------- Page setup ----------------
st.set_page_config(
    page_title="법무 상담사",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",   # ✅ 사이드바 항상 보이도록
)

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

def trigger_question(text: str):
    """공통: 질문을 펜딩 상태로 넣고 즉시 재실행"""
    if not (text or "").strip():
        return
    st.session_state["_pending_user_q"] = text.strip()
    st.session_state["_pending_user_nonce"] = time.time_ns()
    st.session_state["_pending_user_files"] = []
    st.rerun()

def render_conversation_starters(starters=STARTERS_DEFAULT, key_prefix="pre"):
    if not starters:
        return
    st.markdown('<div class="starter-title">💡 자주 묻는 질문</div>', unsafe_allow_html=True)
    cols = st.columns(min(5, max(1, len(starters))))
    for i, txt in enumerate(starters):
        col = cols[i % len(cols)]
        if col.button(txt, key=f"{key_prefix}_starter_{i}", use_container_width=True):
            trigger_question(txt)

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
        "요청하신 주제에 대해 확인했습니다. 이 데모 빌드에서는 예시 답변만 제공합니다.\n\n"
        f"**질문:** {q}\n\n"
        "- 실제 서비스에서는 국가법령정보 API 조회·요약이 여기에 표시됩니다.\n"
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
      .sidebar-caption {font-size:12px;color:#9aa0a6;margin-top:6px;}
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------- Sidebar ---------------
def recent_user_questions(n=8):
    return [m["content"] for m in st.session_state["messages"] if m.get("role") == "user"][-n:][::-1]

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ 옵션")
        mode = st.radio("질의 유형", ["검색요청", "간단한 질의", "전문 법무 상담"], index=1, horizontal=False, key="mode_radio")
        st.caption("선택은 현재 데모에 표시만 됩니다.")

        st.divider()
        st.subheader("📌 빠른 시작")
        for i, txt in enumerate(STARTERS_DEFAULT):
            if st.button(txt, key=f"sb_starter_{i}"):
                trigger_question(txt)

        recents = recent_user_questions()
        if recents:
            st.divider()
            st.subheader("🕘 최근 질문")
            for i, q in enumerate(recents):
                if st.button(q, key=f"sb_recent_{i}"):
                    trigger_question(q)

        st.divider()
        st.markdown("**도움말**")
        st.markdown(
            "- 좌측 버튼을 눌러 빠르게 질문할 수 있어요.\n"
            "- 본 버전은 UI 데모이며, 실제 답변 로직은 백엔드와 연동하세요.",
        )
        st.markdown('<div class="sidebar-caption">국가법령정보 API 기반 데모</div>', unsafe_allow_html=True)

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
        trigger_question(q)

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
        trigger_question(q)

# --------------- Main flow ---------------
render_sidebar()  # ✅ 사이드바 렌더링

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
