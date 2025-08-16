# chatbar.py — Compact chat input (Enter=Send) with attach button (popover/expander)
from __future__ import annotations
import streamlit as st

def chatbar(
    placeholder: str = "메시지를 입력하세요...",
    accept: list[str] | None = None,
    max_files: int = 3,
    max_size_mb: int = 10,
    key_prefix: str = "chatbar",
    max_width_px: int | None = None,    # 상단 컨텐츠와 동일한 최대폭
    compact: bool = True,               # 입력바 높이 축소
    show_upload_label: bool = False,    # 업로드 라벨 표시 여부
    uploader_style: str = "button",     # "button"(권장) | "dropzone"
):
    """
    하단 입력창(st.chat_input) + (선택) 파일 업로드
    Returns: (submitted: bool, typed_text: str, files: list[UploadedFile])
    """
    page_max = max_width_px or 1020

    # 공통 스타일: 폭 정렬 + 입력창 컴팩트 + 업로더 진행바 숨김
    st.markdown(
        f"""
        <style>
          :root {{ --page-max:{page_max}px; }}

          /* 업로더/입력창을 페이지 폭과 맞춤 */
          div[data-testid="stFileUploader"],
          .stChatInput {{
            max-width: var(--page-max) !important;
            margin-left: auto !important;
            margin-right: auto !important;
          }}

          /* 업로더 하단 회색 진행바 숨김 */
          div[role="progressbar"] {{ display: none !important; }}

          /* 입력창을 컴팩트하게 */
          {".stChatInput textarea, .stChatInput input { padding: 6px 10px !important; min-height: 36px !important; font-size: 0.95rem !important; }" if compact else ""}

          /* 첨부 버튼 줄을 입력창과 가깝게 */
          .attach-row {{ max-width: var(--page-max); margin: 0 auto 6px; display:flex; gap:.5rem; align-items:center; }}
          .attach-btn {{
            border: 1px solid rgba(127,127,127,.25);
            background: transparent; color: inherit;
            padding: 6px 10px; border-radius: 10px; cursor: pointer;
          }}
          [data-theme="light"] .attach-btn {{ border-color:#ddd; }}
        </style>
        """,
        unsafe_allow_html=True
    )

    files = []

    if accept:
        if uploader_style == "dropzone":
            # 기존 드롭존 스타일(큰 박스) — 필요시 사용
            files = st.file_uploader(
                "파일 첨부",
                type=accept,
                accept_multiple_files=True,
                key=f"{key_prefix}-files",
                label_visibility=("visible" if show_upload_label else "collapsed"),
            ) or []
        else:
            # 컴팩트: 📎 버튼 → 팝오버(가능하면) 또는 익스팬더로 업로더 표시
            # Streamlit 버전에 따라 st.popover 유무가 다를 수 있어 try 사용
            st.markdown('<div class="attach-row">', unsafe_allow_html=True)
            used_pop = False
            try:
                # 1) popover가 있으면 더 깔끔함
                pop = st.popover("📎 파일 첨부", use_container_width=False)
                with pop:
                    files = st.file_uploader(
                        "파일 첨부",
                        type=accept,
                        accept_multiple_files=True,
                        key=f"{key_prefix}-files",
                        label_visibility=("visible" if show_upload_label else "collapsed"),
                    ) or []
                used_pop = True
            except Exception:
                pass

            if not used_pop:
                # 2) 대안: expander (최소 여백)
                with st.expander("📎 파일 첨부", expanded=False):
                    files = st.file_uploader(
                        "파일 첨부",
                        type=accept,
                        accept_multiple_files=True,
                        key=f"{key_prefix}-files",
                        label_visibility=("visible" if show_upload_label else "collapsed"),
                    ) or []
            st.markdown('</div>', unsafe_allow_html=True)

        # 개수/용량 제한
        max_bytes = max_size_mb * 1024 * 1024
        files = [f for f in files if f.size <= max_bytes]
        if len(files) > max_files:
            files = files[:max_files]

    # 하단 입력창: Enter = 전송
    msg = st.chat_input(placeholder, key=f"{key_prefix}-input")
    submitted = (msg is not None)
    return submitted, (msg or "").strip(), files
