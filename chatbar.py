# chatbar.py — Bottom-fixed chat input with file upload (safe)
import streamlit as st

def chatbar(
    placeholder: str = "메시지를 입력하세요...",
    accept: list[str] | None = None,
    max_files: int = 3,
    max_size_mb: int = 10,
    key_prefix: str = "chatbar",
):
    """
    하단 고정 ChatBar: 입력창 + 파일 업로드
    Returns:
        (submitted: bool, typed_text: str, files: list[UploadedFile])
    """
    st.markdown(
        """
        <style>
        .stChatInput {
            position: fixed; bottom: 0; left: 0; right: 0;
            padding: 0.75rem 1rem; z-index: 9999;
            background-color: var(--background-color);
            box-shadow: 0 -2px 8px rgba(0,0,0,0.08);
        }
        .stChatInput textarea { min-height: 3rem !important; }
        </style>
        """, unsafe_allow_html=True
    )

    submitted = False
    typed_text = ""
    files = []

    with st.container():
        c1, c2 = st.columns([6, 1], vertical_alignment="center")

        with c1:
            typed_text = st.text_area(
                label="chat-input",
                placeholder=placeholder,
                key=f"{key_prefix}-input",
                label_visibility="collapsed",
            )

        with c2:
            submitted = st.button("전송", key=f"{key_prefix}-send", use_container_width=True)

        if accept:
            files = st.file_uploader(
                "파일 첨부",
                type=accept,
                accept_multiple_files=True,
                key=f"{key_prefix}-files",
                label_visibility="collapsed",
            ) or []

            # 용량/개수 제한
            max_bytes = max_size_mb * 1024 * 1024
            files = [f for f in files if f.size <= max_bytes]
            if len(files) > max_files:
                files = files[:max_files]

    # ⛔ 여기서 st.session_state[...] = "" 로 입력창을 비우지 않습니다.
    return submitted, (typed_text or "").strip(), files
