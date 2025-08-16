
# chatbar.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List
import streamlit as st

DEFAULT_ACCEPT = ["pdf", "docx", "txt", "png", "jpg", "jpeg"]

def chatbar(
    placeholder: str = "무엇이든 물어보세요...",
    button_label: str = "보내기",
    accept: List[str] = None,
    key_prefix: str = "chatbar",
):
    if accept is None:
        accept = DEFAULT_ACCEPT

    st.markdown(
        """
        <style>
        .cb-wrap {position: sticky; bottom: 0; background: transparent; padding: 8px 0 0 0; z-index: 99;}
        .cb {display:flex; align-items: center; gap:10px; background:#ffffff10; border:1px solid #7a7a7a44; border-radius:28px; padding:6px 8px;}
        .cb:hover {border-color:#99999966;}
        .cb .left {width:40px; min-width:40px;}
        .cb .mid {flex:1;}
        .cb .mid textarea {border:none !important; outline:none !important;}
        .cb .right {min-width:90px;}
        div[data-testid="stFileUploader"] {background: transparent; border: none; padding: 0; margin: 0;}
        div[data-testid="stFileUploader"] section {padding: 0; border:none; background: transparent;}
        div[data-testid="stFileUploader"] section > div {padding:0; margin:0;}
        div[data-testid="stFileUploader"] label {display:none;}
        div[data-testid="stFileUploaderDropzone"] {background: transparent; border:none; padding:0; margin:0;}
        .clip-btn { display:flex; align-items:center; justify-content:center; width:36px; height:36px;
                    border-radius:999px; cursor:pointer; border:1px solid #8b8b8b44; }
        .clip-btn:hover { background:#ffffff18; border-color:#8b8b8b88; }
        .chip {display:inline-block; padding:2px 8px; margin:4px 4px 0 0; border-radius:999px; border:1px solid #9993; font-size:12px;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    submitted = False
    text_val = ""
    files = []

    with st.container():
        st.markdown('<div class="cb-wrap">', unsafe_allow_html=True)
        with st.form(key=f"{key_prefix}-form", clear_on_submit=True):
            col_left, col_mid, col_right = st.columns([0.12, 0.72, 0.16])
            with col_left:
                st.markdown('<div class="cb"><div class="left">', unsafe_allow_html=True)
                files = st.file_uploader(
                    "첨부",
                    type=accept,
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    key=f"{key_prefix}-uploader",
                )
                st.markdown("<div class='clip-btn'>📎</div>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            with col_mid:
                st.markdown('<div class="mid">', unsafe_allow_html=True)
                text_val = st.text_area(
                    label="메시지",
                    label_visibility="collapsed",
                    placeholder=placeholder,
                    height=60,
                    key=f"{key_prefix}-text",
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with col_right:
                st.markdown('<div class="right">', unsafe_allow_html=True)
                submitted = st.form_submit_button(button_label, use_container_width=True, type="primary")
                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    if files:
        st.write("첨부:", " ".join([f"<span class='chip'>{f.name}</span>" for f in files]), unsafe_allow_html=True)

    return submitted, text_val.strip(), files
