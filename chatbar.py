# chatbar.py — Bottom chat input (Enter=Send) + optional file upload
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
    하단 고정 입력창(st.chat_input) + 파일 업로드
    Returns:
        (submitted: bool, typed_text: str, files: list[UploadedFile])
    """
    # ⚠️ 여기서는 .stChatInput 위치/스타일을 건드리지 않습니다.
    # (app.py에서 이미 padding-bottom / max-width 등을 설정함)

    # 파일 업로드(선택, 본문 위에 표시됨)
    files = []
    if accept:
        files = st.file_uploader(
            "파일 첨부",
            type=accept,
            accept_multiple_files=True,
            key=f"{key_prefix}-files",
            label_visibility="visible",
        ) or []

        # 개수/용량 제한
        max_bytes = max_size_mb * 1024 * 1024
        files = [f for f in files if f.size <= max_bytes]
        if len(files) > max_files:
            files = files[:max_files]

    # 하단 고정 입력창: Enter = 전송
    msg = st.chat_input(placeholder, key=f"{key_prefix}-input")
    submitted = (msg is not None)
    return submitted, (msg or "").strip(), files
