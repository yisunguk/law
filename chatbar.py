# chatbar.py — Bottom-fixed chat input with file upload (Enter = Send)
from __future__ import annotations
import streamlit as st

def chatbar(
    placeholder: str = "메시지를 입력하세요...",
    accept: list[str] | None = None,
    max_files: int = 3,
    max_size_mb: int = 10,
    key_prefix: str = "chatbar",
):
    """
    하단 고정 ChatBar: 입력창(st.chat_input) + 파일 업로드
    Returns:
        (submitted: bool, typed_text: str, files: list[UploadedFile])
    """
    # 선택: 살짝 그림자만 (필수 아님)
    st.markdown(
        """
        <style>
          .stChatInput {
            position: fixed; bottom: 0; left: 0; right: 0;
            padding: 0.75rem 1rem; z-index: 9999;
            background-color: var(--background-color);
            box-shadow: 0 -2px 8px rgba(0,0,0,0.08);
          }
        </style>
        """,
        unsafe_allow_html=True
    )

    # 1) 입력: Enter = 전송
    msg = st.chat_input(placeholder, key=f"{key_prefix}-input")

    # 2) 파일 업로드(선택)
    files = st.file_uploader(
        "파일 첨부",
        type=(accept or None),
        accept_multiple_files=True,
        key=f"{key_prefix}-files",
        label_visibility="collapsed",
    ) or []

    # 개수/용량 제한
    max_bytes = max_size_mb * 1024 * 1024
    files = [f for f in files if f.size <= max_bytes]
    if len(files) > max_files:
        files = files[:max_files]

    submitted = (msg is not None)
    return submitted, (msg or "").strip(), files
