
import time
import streamlit as st

# ======================
# Page & Global CSS
# ======================
st.set_page_config(page_title="법무 상담사", page_icon="⚖️", layout="wide")

def inject_compact_css():
    st.markdown("""
    <style>
    /* 전체 상하 패딩 축소 */
    .block-container { padding-top: 16px !important; padding-bottom: 16px !important; }
    /* 가로 스크롤 완전 차단 */
    .block-container, .main, .element-container { overflow-x: hidden !important; }
    /* 히어로 섹션 상단 끌어올림 */
    .center-hero { margin-top: -8px !important; }
    /* 업로더/폼/입력창 간격 축소 */
    section.center-hero .stFileUploader { margin-top: 2px !important; margin-bottom: 8px !important; }
    section.center-hero [data-testid="stForm"] { margin-top: 4px !important; margin-bottom: 8px !important; }
    section.center-hero .stTextInput input { min-height: 38px !important; }
    /* 대화 스타터 */
    .starter-wrap { margin-top: 8px !important; overflow-x: hidden !important; }
    .starter-note { opacity:.75; font-size:12.5px; margin: 6px 0 4px !important; }
    .stButton > button {
      padding: 8px 12px !important;
      line-height: 1.25 !important;
      white-space: normal !important;
      word-break: break-word !important;
      border-radius: 12px !important;
      font-size: 14px !important;
    }
    </style>
    """, unsafe_allow_html=True)

inject_compact_css()

# ======================
# Starters
# ======================
CHAT_STARTERS = [
    "주택임대차보호법 보증금 우선변제권 요건은?",
    "개인정보 보호법 유출 통지의무와 과징금은?",
    "교통사고처리 특례법 적용 대상과 처벌 수위는?",
    "근로기준법 연차휴가 미사용수당 계산 방법은?"
]

# ======================
# State
# ======================
def init_state():
    ss = st.session_state
    ss.setdefault("messages", [])
    ss.setdefault("chat_started", False)
    # pending user question for pre-chat handoff
    ss.setdefault("_pending_user_q", None)
    ss.setdefault("_pending_user_nonce", None)
init_state()

def push_user_from_pending():
    ss = st.session_state
    q = ss.get("_pending_user_q")
    if not q:
        return False
    # append to chat history
    ss["messages"].append({"role": "user", "content": q})
    # clear pending
    ss["_pending_user_q"] = None
    ss["_pending_user_nonce"] = None
    ss["chat_started"] = True
    return True

# ======================
# Views
# ======================
def render_pre_chat_center():
    st.markdown('<section class="center-hero">', unsafe_allow_html=True)
    st.markdown(
        '<h1 style="font-size:34px;font-weight:800;letter-spacing:-.5px;margin-bottom:14px;">무엇을 도와드릴까요?</h1>',
        unsafe_allow_html=True,
    )

    # 파일 업로더 (중복 키 방지)
    st.file_uploader(
        "Drag and drop files here",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="pre_files",
    )

    # 입력 폼 (전송 버튼 포함)
    with st.form("first_ask_pre", clear_on_submit=True):
        q = st.text_input("질문을 입력해 주세요...", key="pre_input")
        sent = st.form_submit_button("전송", use_container_width=True)

    if sent and (q or "").strip():
        st.session_state["_pending_user_q"] = q.strip()
        st.session_state["_pending_user_nonce"] = time.time_ns()
        st.rerun()

    # 대화 스타터: 입력창 아래, 세로 5줄
    if CHAT_STARTERS:
        st.markdown('<div class="starter-wrap">', unsafe_allow_html=True)
        st.markdown('<div class="starter-note">추천 질문</div>', unsafe_allow_html=True)
        for i, txt in enumerate(CHAT_STARTERS):
            if st.button(txt, key=f"starter_pre_{i}", use_container_width=True, help="클릭하면 바로 전송됩니다."):
                st.session_state["_pending_user_q"] = txt.strip()
                st.session_state["_pending_user_nonce"] = time.time_ns()
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("</section>", unsafe_allow_html=True)

def render_chat_view():
    st.markdown("### 대화")
    # 대화 기록 표시
    for m in st.session_state["messages"]:
        if m["role"] == "user":
            with st.chat_message("user"):
                st.write(m["content"])
        else:
            with st.chat_message("assistant"):
                st.write(m["content"])

    # 하단 채팅 입력창
    user_q = st.chat_input("메시지를 입력하세요…")
    if user_q:
        st.session_state["messages"].append({"role": "user", "content": user_q})
        # === 여기에 실제 답변 생성 로직을 연결하세요 ===
        # 현재는 데모로 간단한 에코/가짜 응답
        with st.chat_message("assistant"):
            st.write("요청하신 내용을 확인 중입니다…")
        # 가짜 답변 추가
        st.session_state["messages"].append({
            "role": "assistant",
            "content": f"질문 요약: {user_q}\n\n※ 실제 서비스에선 국가법령정보/검색 API와 LLM 응답을 연결하세요."
        })
        st.rerun()

# ======================
# App Router
# ======================
# pending이 있으면 푸시
if push_user_from_pending():
    st.experimental_rerun()

if not st.session_state["chat_started"]:
    render_pre_chat_center()
else:
    render_chat_view()
