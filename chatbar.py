# chatbar.py — Optimized bottom-fixed chat input with file upload
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

    # --- CSS: ChatBar 고정 스타일 ---
    st.markdown(
        f"""
        <style>
        .stChatInput {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 0.75rem 1rem;
            background-color: var(--background-color);
            box-shadow: 0 -2px 8px rgba(0,0,0,0.08);
            z-index: 9999;
        }}
        .stChatInput textarea {{
            min-height: 3rem !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    submitted = False
    typed_text = ""
    files = []

    # --- 입력 영역 ---
    with st.container():
        c1, c2 = st.columns([6, 1])

        with c1:
            typed_text = st.text_area(
                label="chat-input",
                placeholder=placeholder,
                key=f"{key_prefix}-input",
                label_visibility="collapsed",
            )

        with c2:
            submitted = st.button("전송", key=f"{key_prefix}-send", use_container_width=True)

        # 파일 업로드 (선택)
        if accept:
            files = st.file_uploader(
                "파일 첨부",
                type=accept,
                accept_multiple_files=True,
                key=f"{key_prefix}-files",
                label_visibility="collapsed",
            ) or []

            # 용량 제한 확인
            max_bytes = max_size_mb * 1024 * 1024
            oversized = [f for f in files if f.size > max_bytes]
            if oversized:
                st.warning(f"⚠️ {len(oversized)}개 파일이 {max_size_mb}MB 제한을 초과하여 제외됩니다.")
                files = [f for f in files if f not in oversized]

            if len(files) > max_files:
                st.warning(f"⚠️ 파일은 최대 {max_files}개까지만 업로드 가능합니다.")
                files = files[:max_files]

    return submitted, (typed_text or "").strip(), files
