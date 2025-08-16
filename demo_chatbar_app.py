
# demo_chatbar_app.py
# -*- coding: utf-8 -*-
import io, os
import streamlit as st
from chatbar import chatbar
from utils_extract import extract_text_from_pdf, extract_text_from_docx, read_txt, sanitize

st.set_page_config(page_title="ChatBar 데모", page_icon="💬", layout="wide")
st.title("💬 ChatBar 데모 (채팅창에서 바로 첨부)")

if "history" not in st.session_state:
    st.session_state.history = []

for role, text, file_names in st.session_state.history:
    with st.chat_message(role):
        st.markdown(text or "")
        if file_names:
            st.caption("첨부: " + ", ".join(file_names))

submitted, text, files = chatbar(
    placeholder="메시지를 입력하고 📎로 파일을 첨부하세요...",
    accept=["pdf","docx","txt","png","jpg","jpeg"],
)

if submitted and (text or files):
    file_names = [f.name for f in (files or [])]
    previews = []
    for f in files or []:
        name = f.name
        ext = os.path.splitext(name)[1].lower()
        data = f.read()
        if ext == ".pdf":
            txt = extract_text_from_pdf(io.BytesIO(data))
        elif ext == ".docx":
            txt = extract_text_from_docx(io.BytesIO(data))
        elif ext == ".txt":
            txt = read_txt(io.BytesIO(data))
        else:
            txt = f"(미리보기 없음) {len(data)} bytes"
        previews.append(f"### {name}\\n```\n{sanitize(txt)[:1000]}\n```")

    user_blob = (text or "") + ("\\n\\n" + "\\n\\n".join(previews) if previews else "")
    st.session_state.history.append(("user", user_blob, file_names))

    reply = "파일을 받았어요. 본문 추출을 완료했습니다."
    st.session_state.history.append(("assistant", reply, []))

    st.experimental_rerun()
