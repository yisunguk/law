
import streamlit as st

st.set_page_config(page_title="법률상담 챗봇 - Hero Lift Demo", layout="wide")

# --- Session state ---
if "chat_started" not in st.session_state:
    st.session_state["chat_started"] = False

# --- Hero HTML ---
HERO_HTML = """
<div class="hero-inner">
  <h1>⚖️ 법률상담 챗봇</h1>
  <p>법제처 국가법령정보 DB를 기반으로 최신 법령과 행정규칙, 자치법규, 조약, 법령해석례, 판례/결정례, 법령용어를 신뢰성 있게 제공합니다.</p>
  <p>본 챗봇은 신속하고 정확한 법령 정보를 안내하여, 사용자가 법률적 쟁점을 이해하고 합리적인 판단을 내릴 수 있도록 돕습니다.</p>
</div>
"""

# --- Base CSS ---
st.markdown(
    """
    <style>
    .hero-inner h1 { margin: 0 0 8px 0; font-size: 36px; }
    .hero-inner p  { margin: 0 0 8px 0; font-size: 16px; }
    /* right rail id is optional; if not present nothing happens */
    </style>
    """, unsafe_allow_html=True
)

# --- Pre-chat: lift only the hero to the very top (sticky) ---
if not st.session_state["chat_started"]:
    st.markdown(
        """
        <style>
          #hero-lift { position: sticky; top: 6px; z-index: 100; margin: 0 0 12px 0; }
          /* hide any hero that might be rendered inside a centered container */
          .center-hero .global-hero { display: none !important; }
          /* keep right flyout hidden in pre-chat if it exists */
          body:not(.chat-started) #search-flyout { display: none !important; }
          /* keep content close to the top in pre-chat */
          body:not(.chat-started) .block-container { padding-top: 12px !important; }
        </style>
        """, unsafe_allow_html=True
    )
    st.markdown(f'<div id="hero-lift" class="global-hero">{HERO_HTML}</div>', unsafe_allow_html=True)

    # --- Pre-chat content (uploader + question) ---
    st.markdown('<section class="center-hero">', unsafe_allow_html=True)
    st.write("Drag and drop files here")
    st.file_uploader("Drag and drop files here", type=["pdf", "docx", "txt"], key="first_files", accept_multiple_files=True)
    question = st.text_input("질문을 입력해 주세요...")
    if st.button("전송"):
        st.session_state["chat_started"] = True
        st.session_state["first_question"] = question
        st.experimental_rerun()
    st.markdown('</section>', unsafe_allow_html=True)

# --- Post-chat: render sticky hero in the normal place ---
else:
    st.markdown(
        """
        <style>
          .global-hero { position: sticky; top: 6px; z-index: 10; margin: 0 0 12px 0; }
          .block-container { padding-top: 108px !important; }
        </style>
        """, unsafe_allow_html=True
    )
    st.markdown(f'<div class="global-hero">{HERO_HTML}</div>', unsafe_allow_html=True)

    st.write("👋 여기에 채팅 UI가 나타납니다. (데모)")
    st.write("첫 질문:", st.session_state.get("first_question", ""))
    # place-holders for bottom-fixed inputs could be implemented with custom CSS/js in your real app
