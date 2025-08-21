# chatbar.py — Enter-to-send (ChatGPT-style) + optional file upload
# - Enter      → 전송
# - Shift+Enter→ 줄바꿈
# - IME(한글 조합) 중 Enter는 자동 처리 (st.chat_input 기본 동작)
import streamlit as st
from typing import List, Optional

def chatbar(
    placeholder: str = "메시지를 입력하세요...",
    accept: Optional[List[str]] = None,   # 예: ["pdf","docx","txt"]
    max_files: int = 3,
    max_size_mb: int = 10,
    key_prefix: str = "chatbar",
):
    """
    하단 고정 ChatBar: 파일 업로드(선택) + 채팅 입력
    Returns:
        (submitted: bool, typed_text: str, files: list[UploadedFile])
    """
    submitted = False
    typed_text = ""
    files: List = []

    # ---- (선택) 파일 업로더: 입력창 위에 배치 ----
    if accept:
        files = st.file_uploader(
            "파일 첨부",
            type=accept,
            accept_multiple_files=True,
            key=f"{key_prefix}-files",
            label_visibility="collapsed",
        ) or []
        # 용량/개수 제한 적용
        max_bytes = max_size_mb * 1024 * 1024
        files = [f for f in files if f.size <= max_bytes][:max_files]

    # ---- 채팅 입력: Enter 전송(Shift+Enter 줄바꿈) ----
    text = st.chat_input(placeholder, key=f"{key_prefix}-chat")
    if text is not None:                 # 제출되면 문자열, 아니면 None
        typed_text = text.strip()
        submitted = bool(typed_text)     # 공백만 입력 시 False

    # ⛔ 여기서 입력창을 강제로 비우지 않습니다 (st.chat_input가 알아서 처리)
    return submitted, typed_text, files
