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

/* 드롭존 상자 제거 */
div[data-testid="stFileUploaderDropzone"]{
  border:none !important; background:transparent !important;
  padding:0 !important; margin:0 !important;
}

/* ▼▼ 핵심: 드롭존의 모든 텍스트를 가리고, small/버튼만 복구 ▼▼ */
div[data-testid="stFileUploaderDropzone"] *{
  display:none !important;            /* 일단 전부 숨김 */
  font-size:0 !important;             /* 혹시 남는 텍스트 대비 */
  line-height:0 !important;
  color:transparent !important;
}

/* 안내(small)와 Browse files 버튼만 다시 보이게 */
div[data-testid="stFileUploaderDropzone"] small{
  display:inline !important;
  font-size:12px !important;
  line-height:1.2 !important;
  color:inherit !important;
}
div[data-testid="stFileUploaderDropzone"] button{
  display:inline-flex !important;
  font-size:14px !important;
  line-height:1.2 !important;
  color:inherit !important;
}

/* 업로드된 파일 기본 프리뷰 숨김(칩 형태 등 별도 UI 쓸 때) */
div[data-testid="stUploadedFile"]{display:none !important;}
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
