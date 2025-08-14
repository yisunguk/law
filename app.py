import os
import time
import json
import math
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import uuid
from typing import List, Dict, Any

import requests
import streamlit as st
from openai import AzureOpenAI

# =============================
# 기본 설정 & 스타일 (ChatGPT와 동일한 채팅 UI)
# =============================
st.set_page_config(page_title="법제처 AI 챗봇", page_icon="⚖️", layout="wide")

st.markdown("""
<style>
  .block-container {max-width: 900px; margin: 0 auto; padding-bottom: .5rem !important;}
  .stChatInput {max-width: 900px; margin-left: auto; margin-right: auto;}
  .stChatInput textarea {font-size:15px; margin-top: 0 !important;}
  .header {text-align:center;padding:1rem;border-radius:12px;background:linear-gradient(135deg,#8b5cf6,#a78bfa);color:#fff;margin:0 0 .75rem 0}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="header"><h2>⚖️ 법제처 인공지능 법률 상담 플랫폼</h2><div>법제처 공식 데이터 + Azure OpenAI</div></div>', unsafe_allow_html=True)

# =============================
# Secrets 로딩
# =============================
def load_secrets():
    law_key = None; azure = None
    try:
        law_key = st.secrets["LAW_API_KEY"]
    except Exception:
        st.warning("`LAW_API_KEY`가 없습니다. 법제처 검색 기능 없이 동작합니다.")
    try:
        azure = st.secrets["azure_openai"]
    except Exception:
        st.error("[azure_openai] 설정 누락")
        azure = None
    return law_key, azure

LAW_API_KEY, AZURE = load_secrets()

# =============================
# Azure OpenAI 클라이언트
# =============================
client = None
if AZURE:
    try:
        client = AzureOpenAI(
            api_key=AZURE["api_key"],
            api_version=AZURE["api_version"],
            azure_endpoint=AZURE["endpoint"],
        )
    except Exception as e:
        st.error(f"Azure OpenAI 초기화 실패: {e}")

# =============================
# 세션 상태 초기화
# =============================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []

# =============================
# 법제처 API
# =============================
@st.cache_data(show_spinner=False, ttl=300)
def search_law_data(query: str, num_rows: int = 5):
    if not LAW_API_KEY:
        return [], None, "LAW_API_KEY 미설정"
    params = {
        "serviceKey": urllib.parse.quote_plus(LAW_API_KEY),
        "target": "law",
        "query": query,
        "numOfRows": max(1, min(10, int(num_rows))),
        "pageNo": 1,
    }
    url = "https://apis.data.go.kr/1170000/law/lawSearchList.do"
    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        root = ET.fromstring(res.text)
        laws = []
        for law in root.findall(".//law"):
            laws.append({
                "법령명": law.findtext("법령명한글", default=""),
                "법령약칭명": law.findtext("법령약칭명", default=""),
                "소관부처명": law.findtext("소관부처명", default=""),
                "법령구분명": law.findtext("법령구분명", default=""),
                "시행일자": law.findtext("시행일자", default=""),
                "공포일자": law.findtext("공포일자", default=""),
                "법령상세링크": law.findtext("법령상세링크", default=""),
            })
        return laws, url, None
    except Exception as e:
        return [], None, str(e)

def format_law_context(law_data):
    if not law_data: return "관련 법령 검색 결과가 없습니다."
    rows = []
    for i, law in enumerate(law_data, 1):
        rows.append(
            f"{i}. {law['법령명']} ({law['법령구분명']})\n"
            f"   - 소관부처: {law['소관부처명']}\n"
            f"   - 시행일자: {law['시행일자']} / 공포일자: {law['공포일자']}\n"
            f"   - 링크: {law['법령상세링크'] or '없음'}"
        )
    return "\n\n".join(rows)

# =============================
# 모델 메시지 구성
# =============================

def build_history_messages(max_turns=10):
    sys = {"role": "system", "content": "당신은 대한민국 법령 전문 AI 어시스턴트입니다."}
    msgs = [sys]
    history = st.session_state.messages[-max_turns*2:]
    for m in history:
        msgs.append({"role": m["role"], "content": m["content"]})
    return msgs

# =============================
# 기존 대화 출력 (GPT처럼 위에서부터 쌓이는 형식)
# =============================
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# =============================
# 입력창
# =============================
user_q = st.chat_input("법령에 대한 질문을 입력하세요…")
if user_q:
    ts = datetime.utcnow().isoformat()
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
    with st.chat_message("user"):
        st.markdown(user_q)

    # 법제처 검색
    law_data, _, _ = ([], None, None)
    if True:
        law_data, _, _ = search_law_data(user_q, 5)
    law_ctx = format_law_context(law_data)

    # 모델 호출
    model_messages = build_history_messages()
    model_messages.append({"role": "user", "content": f"{user_q}\n\n참고 법령:\n{law_ctx}"})

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_text = ""
        if client:
            for piece in client.chat.completions.create(model=AZURE["deployment"], messages=model_messages, stream=True):
                try:
                    if piece.choices and piece.choices[0].delta and piece.choices[0].delta.content:
                        full_text += piece.choices[0].delta.content
                        placeholder.markdown(full_text)
                except Exception:
                    pass
        else:
            full_text = law_ctx
            placeholder.markdown(full_text)
    st.session_state.messages.append({"role": "assistant", "content": full_text, "ts": ts})
