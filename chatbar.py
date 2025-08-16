# chatbar.py — Bottom chat input (Enter=Send) + compact file uploader
from __future__ import annotations
import streamlit as st

def chatbar(
    placeholder: str = "메시지를 입력하세요...",
    accept: list[str] | None = None,
    max_files: int = 3,
    max_size_mb: int = 10,
    key_prefix: str = "chatbar",
    max_width_px: int | None = None,   # 상단 컨텐츠와 동일한 최대폭
    compact: bool = True,              # 입력바 높이 축소
    show_upload_label: bool = False,   # 업로드 라벨 보이기 여부
):
    """
    하단 입력창(st.chat_input) + (선택) 파일 업로드
    Returns: (submitted: bool, typed_text: str, files: list[UploadedFile])
    """
    page_max = max_width_px or 1020

    # 폭 정렬 + 업로더 진행바 숨김 + 입력창 컴팩트
    st.markdown(
        f"""
        <style>
          :root {{ --page-max:{page_max}px; }}

          /* 업로더/입력창을 페이지 폭과 맞춤 */
          div[data-testid="stFileUploader"] {{
            max-width: var(--page-max) !important;
            margin: 0 auto 6px !important;
          }}
          .stChatInput {{
            max-width: var(--page-max) !important;
            margin: 0 auto !important;
          }}

          /* 업로더 아래 회색 진행바 숨김 */
          div[role="progressbar"] {{ display: none !important; }}

          /* 입력창을 컴팩트하게 */
          {".stChatInput textarea, .stChatInput input { padding: 6px 10px !important; min-height: 36px !important; font-size: 0.95rem !important; }" if compact else ""}
        </style>
        """,
        unsafe_allow_html=True
    )

    # (선택) 파일 업로드 – 입력바 바로 위에 배치
    files = []
    if accept:
        files = st.file_uploader(
            "파일 첨부",
            type=accept,
            accept_multiple_files=True,
            key=f"{key_prefix}-files",
            label_visibility=("visible" if show_upload_label else "collapsed"),
        ) or []

        # 개수/용량 제한
        max_bytes = max_size_mb * 1024 * 1024
        files = [f for f in files if f.size <= max_bytes]
        if len(files) > max_files:
            files = files[:max_files]

    # 하단 입력창: Enter=전송
    msg = st.chat_input(placeholder, key=f"{key_prefix}-input")
    submitted = (msg is not None)
    return submitted, (msg or "").strip(), files
