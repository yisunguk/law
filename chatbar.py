# chatbar.py
# -*- coding: utf-8 -*-
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

    # ===== CSS + JS (엔터 제출, Shift+Enter 줄바꿈) =====
    st.markdown(f"""
<style>
.block-container{{ padding-bottom:120px !important; }}
.cb2-wrap{{ position:fixed;left:0;right:0;bottom:0;
  border-top:1px solid rgba(255,255,255,.12);
  background:rgba(20,20,20,.95);backdrop-filter:blur(6px);z-index:1000; }}
[data-theme="light"] .cb2-wrap{{ background:rgba(255,255,255,.95);border-top:1px solid #e5e5e5; }}
.cb2-wrap .stForm, .cb2-wrap .stForm>div{{ max-width:1020px;margin:0 auto;width:100%; }}
.cb2-row{{ display:grid;grid-template-columns:0.22fr 1fr 0.18fr;gap:8px;padding:8px 12px; }}
.cb2-text textarea{{ min-height:40px !important;height:40px !important; }}
</style>

<script>
document.addEventListener("DOMContentLoaded", function(){{
  const textarea = window.parent.document.querySelector(
    'textarea[id^="{key_prefix}-text"]'
  );
  if(textarea){{
    textarea.addEventListener("keydown", function(e){{
      if(e.key === "Enter" && !e.shiftKey){{
        e.preventDefault();
        const btn = window.parent.document.querySelector(
          'button[kind="primary"][id^="{key_prefix}-form"]'
        );
        if(btn) btn.click();
      }}
    }});
  }}
}});
</script>
""", unsafe_allow_html=True)

    submitted = False
    text_val = ""
    files = []

    st.markdown('<div class="cb2-wrap">', unsafe_allow_html=True)
    with st.form(key=f"{key_prefix}-form", clear_on_submit=True):
        st.markdown('<div class="cb2-row">', unsafe_allow_html=True)

        files = st.file_uploader(
            "첨부",
            type=accept,
            accept_multiple_files=True,
            key=f"{key_prefix}-uploader",
            label_visibility="collapsed",
            help=f"최대 {max_files}개, 파일당 {max_size_mb}MB",
        )

        text_val = st.text_area(
            "메시지",
            placeholder=placeholder,
            key=f"{key_prefix}-text",
            label_visibility="collapsed",
            height=40,
        )

        submitted = st.form_submit_button(button_label, use_container_width=True, type="primary")

        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    return submitted, (text_val or '').strip(), files
