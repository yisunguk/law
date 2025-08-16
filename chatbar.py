# chatbar.py
# -*- coding: utf-8 -*-
"""
A cleaner, intuitive chat input with an attach (+) button for Streamlit.
- Single row input (auto-expands to ~3 rows)
- Big rounded bar like ChatGPT, with a clear + icon area
- Drag & drop or click to attach
- Shows compact "chips" for selected files with size
- Basic validation (max files, max size, extensions)
- Returns (submitted: bool, text: str, files: list[UploadedFile])
"""
from __future__ import annotations
from typing import List, Optional
import streamlit as st

KB = 1024
MB = 1024 * 1024

def _fmt_size(n: int) -> str:
    if n >= MB: return f"{n/MB:.1f} MB"
    if n >= KB: return f"{n/KB:.0f} KB"
    return f"{n} B"

def chatbar(
    placeholder: str = "메시지를 입력하세요…",
    button_label: str = "보내기",
    accept: Optional[List[str]] = None,
    max_files: int = 5,
    max_size_mb: int = 15,
    key_prefix: str = "chatbar",
):
    """
    A minimal, chat bar with + attach, returns (submitted, text, files).
    """
    if accept is None:
        accept = ["pdf","docx","txt","png","jpg","jpeg"]

    st.markdown(
        """
        <style>
        .cb2-wrap { position: sticky; bottom: 0; z-index: 50; padding: 8px 0 0; }
        .cb2 { display:flex; align-items:center; gap:10px; background: var(--cb2-bg,#1f1f1f);
               border:1px solid var(--cb2-bd,#404040); border-radius: 999px; padding: 8px 10px; }
        [data-theme="light"] .cb2 { --cb2-bg: #fff; --cb2-bd:#e5e5e5; }
        .cb2 .left { width: 40px; min-width: 40px; display:flex; align-items:center; justify-content:center; }
        .cb2 .clip { width: 28px; height: 28px; display:flex; align-items:center; justify-content:center;
                     border-radius: 999px; border:1px solid var(--cb2-bd,#404040); cursor:pointer; }
        .cb2 .clip:hover { background: rgba(255,255,255,.06); }
        .cb2 .mid { flex:1; display:flex; align-items:center; }
        .cb2 .mid textarea { border:none !important; outline:none !important; background:transparent !important;
                             resize:none !important; height:38px; max-height: 90px; }
        .cb2 .right { min-width: 96px; }
        .chips { margin: 6px 4px 0; }
        .chip { display:inline-flex; align-items:center; gap:6px; padding: 2px 8px; margin: 4px 6px 0 0;
                border-radius:999px; border:1px solid var(--cb2-bd,#404040); font-size:12px; }
        .chip .size { opacity: .7; }
        div[data-testid="stFileUploader"] { border:none; background:transparent; padding:0; margin:0; }
        div[data-testid="stFileUploader"] section { padding:0; border:none; background:transparent; }
        div[data-testid="stFileUploader"] section > div { padding:0; margin:0; }
        div[data-testid="stFileUploader"] label { display:none; }
        div[data-testid="stFileUploaderDropzone"] { border:none; background:transparent; padding:0; margin:0; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    submitted = False
    text_val = ""
    files = []

    with st.container():
        with st.form(key=f"{key_prefix}-form", clear_on_submit=True):
            col_l, col_m, col_r = st.columns([0.1, 0.78, 0.12])
            with col_l:
                st.markdown('<div class="cb2"><div class="left">', unsafe_allow_html=True)
                files = st.file_uploader(
                    "첨부",
                    type=accept,
                    accept_multiple_files=True,
                    key=f"{key_prefix}-uploader",
                    label_visibility="collapsed",
                )
                st.markdown('<div class="clip">＋</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            with col_m:
                st.markdown('<div class="mid">', unsafe_allow_html=True)
                text_val = st.text_area(
                    "메시지",
                    placeholder=placeholder,
                    key=f"{key_prefix}-text",
                    label_visibility="collapsed",
                    height=38,
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with col_r:
                st.markdown('<div class="right">', unsafe_allow_html=True)
                submitted = st.form_submit_button(button_label, use_container_width=True, type="primary")
                st.markdown('</div>', unsafe_allow_html=True)

    # Validation and chips
    errs = []
    sel = files or []
    if len(sel) > max_files:
        errs.append(f"최대 {max_files}개 파일만 첨부할 수 있습니다.")
        sel = sel[:max_files]

    overs = [f for f in sel if getattr(f, 'size', 0) > max_size_mb*MB]
    if overs:
        names = ", ".join([f.name for f in overs])
        errs.append(f"파일 용량 초과({max_size_mb}MB): {names}")
        sel = [f for f in sel if f not in overs]

    if errs:
        st.error(" / ".join(errs))

    if sel:
        chips = []
        for f in sel:
            chips.append(f"<span class='chip'>{f.name} <span class='size'>{_fmt_size(getattr(f,'size',0))}</span></span>")
        st.markdown("<div class='chips'>"+"".join(chips)+"</div>", unsafe_allow_html=True)

    return submitted, (text_val or "").strip(), sel
