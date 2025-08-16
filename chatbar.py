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
/* 업로더 기본 정리 */
div[data-testid="stFileUploader"]{background:transparent;border:none;padding:0;margin:0;}
div[data-testid="stFileUploader"] section{padding:0;border:none;background:transparent;}
div[data-testid="stFileUploader"] section>div{padding:0;margin:0;}
div[data-testid="stFileUploader"] label{display:none;}  /* 라벨 숨김 */

/* 드롭존 커스터마이징 */
div[data-testid="stFileUploaderDropzone"]{
  border:2px dashed #888 !important;  /* ✅ 테두리 추가 */
  border-radius:8px !important;
  background:transparent !important;
  padding:10px !important;
  margin:0 !important;
  text-align:center;
}

/* 안의 모든 요소 숨기기 */
div[data-testid="stFileUploaderDropzone"] *{
  display:none !important;
}

/* 안내 문구(small)만 다시 보이게 */
div[data-testid="stFileUploaderDropzone"] small{
  display:block !important;
  font-size:0.9rem !important;
  color:#ccc !important;
  margin:5px 0;
}

/* Browse files 버튼 숨김 */
div[data-testid="stFileUploaderDropzone"] button{
  display:none !important;
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
