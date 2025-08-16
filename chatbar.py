# chatbar.py
# -*- coding: utf-8 -*-
"""
Streamlit ChatBar (clean, no "+"):
- Browse files 버튼 + Limit 안내만 표시
- Drag&Drop 문구/박스 삭제
- "+" 아이콘 삭제
"""
from __future__ import annotations
from typing import List, Optional
import streamlit as st

DEFAULT_ACCEPT = ["pdf", "docx", "txt"]

def chatbar(
    placeholder: str = "메시지를 입력하세요…",
    button_label: str = "보내기",
    accept: Optional[List[str]] = None,
    key_prefix: str = "chatbar",
    max_files: int = 5,
    max_size_mb: int = 15,
):
    if accept is None:
        accept = DEFAULT_ACCEPT

    st.markdown("""
<style>
/* 업로더 기본 영역 */
div[data-testid="stFileUploader"]{
  background:transparent !important;
  border:none !important;
  padding:0 !important;
  margin:0 !important;
}

/* 드롭존 영역 */
div[data-testid="stFileUploaderDropzone"]{
  border:none !important;
  background:transparent !important;
  padding:0 !important;
  margin:0 !important;
}

/* ✅ "Drag and drop files here"는 보이지만 클릭 차단 */
div[data-testid="stFileUploaderDropzone"] div:first-child{
  pointer-events:none !important;  /* 클릭 막기 */
}

/* 안내 문구(small)는 그대로 */
div[data-testid="stFileUploaderDropzone"] small{
  display:inline !important;
  font-size:12px !important;
  color:inherit !important;
}

/* Browse files 버튼은 정상 작동 */
div[data-testid="stFileUploaderDropzone"] button{
  display:inline-flex !important;
  font-size:14px !important;
  color:inherit !important;
}
</style>
""", unsafe_allow_html=True)

    submitted = False
    text_val = ""
    files = []

    with st.container():
        st.markdown('<div class="cb2-wrap">', unsafe_allow_html=True)
        with st.form(key=f"{key_prefix}-form", clear_on_submit=True):
            col_l, col_m, col_r = st.columns([0.2, 0.6, 0.2])
            with col_l:
                files = st.file_uploader(
                    "첨부",
                    type=accept,
                    accept_multiple_files=True,
                    key=f"{key_prefix}-uploader",
                    label_visibility="collapsed",
                )
            with col_m:
                text_val = st.text_area(
                    "메시지",
                    placeholder=placeholder,
                    key=f"{key_prefix}-text",
                    label_visibility="collapsed",
                    height=40,
                )
            with col_r:
                submitted = st.form_submit_button(button_label, use_container_width=True, type="primary")
        st.markdown('</div>', unsafe_allow_html=True)

    return submitted, (text_val or '').strip(), files
