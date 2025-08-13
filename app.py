# app.py
# -*- coding: utf-8 -*-

import os
import time
import json
import traceback
from typing import Optional, Dict, Any, List

import streamlit as st

# =========================
# 페이지 기본 설정
# =========================
st.set_page_config(
    page_title="법제처 AI 챗봇",
    page_icon="⚖️",
    layout="wide",
)

# =========================
# UI 헤더
# =========================
st.markdown(
    """
    <style>
    .banner {
        background: linear-gradient(90deg, #6a85f1, #b98df5);
        color: white;
        padding: 28px 28px;
        border-radius: 18px;
        text-align: center;
        font-size: 28px;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin-bottom: 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="banner">⚖️ 법제처 AI 챗봇</div>', unsafe_allow_html=True)
st.caption("이 챗봇은 법제처 Open API와 OpenAI(Azure 포함)를 활용하여 지능형 법령 상담을 제공합니다. 제공되는 정보는 참고용이며, 정확한 법률 상담은 전문가에게 문의하세요.")

# =========================
# 시크릿 로딩
# =========================
def load_secrets():
    """
    Streamlit Secrets에서 키와 Azure 설정을 읽고 기본 검증 메시지를 표출합니다.
    - LAW_API_KEY: 법제처 Open API용 (선택)
    - OPENAI_API_KEY: 일반 OpenAI 키 (선택)
    - [azure_openai] 섹션: Azure OpenAI 설정 (선택)
    두 중 하나(OpenAI or Azure)가 존재하면 AI 응답이 활성화됩니다.
    """
    law_key = st.secrets.get("LAW_API_KEY")
    openai_key = st.secrets.get("OPENAI_API_KEY")
    azure_conf = st.secrets.get("azure_openai")

    if not law_key:
        st.info("ℹ️ `LAW_API_KEY`가 없습니다. 법제처 Open API 연동 기능은 제한될 수 있습니다.")

    if not openai_key and not azure_conf:
        st.warning("⚠️ OpenAI/Azure OpenAI 키가 없어 AI 답변 기능이 제한됩니다. `.streamlit/secrets.toml`을 확인하세요.")

    return law_key, openai_key, azure_conf

LAW_API_KEY, OPENAI_API_KEY, AZURE_CONF = load_secrets()

# =========================
# OpenAI / Azure OpenAI 클라이언트 초기화
# =========================
client = None
MODEL_NAME = None
is_azure = False

def init_client():
    global client, MODEL_NAME, is_azure
    try:
        if OPENAI_API_KEY:
            # 일반 OpenAI
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            # 필요시 다른 공개 모델로 교체 가능
            MODEL_NAME = "gpt-4o-mini"
            is_azure = False
        elif AZURE_CONF:
            # Azure OpenAI
            from openai import AzureOpenAI
            client = AzureOpenAI(
                api_key=AZURE_CONF.get("api_key"),
                azure_endpoint=AZURE_CONF.get("endpoint"),
                api_version=AZURE_CONF.get("api_version"),
            )
            # Azure에서는 model 인자에 "배포 이름(deployment name)"을 넣는다.
            MODEL_NAME = AZURE_CONF.get("deployment")
            is_azure = True
        else:
            client = None
            MODEL_NAME = None
            is_azure = False
    except Exception as e:
        client = None
        MODEL_NAME = None
        is_azure = False
        st.error(f"OpenAI 클라이언트 초기화 오류: {e}")
        st.exception(e)

init_client()

# =========================
# 법제처 Open API 헬퍼 (선택)
# =========================
def search_law_articles(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    예시용: 실제 법제처 Open API 스펙에 맞춰 수정해서 사용하세요.
    여기선 데모 목적으로, 키가 없거나 호출 실패 시 빈 리스트를 반환합니다.
    """
    if not LAW_API_KEY:
        return []

    try:
        # 실제 연동 시 아래에 requests 사용 예시를 참고해 구현하세요.
        # import requests
        # url = "https://api.law.go.kr/xxx"  # 실제 엔드포인트
        # params = {"query": query, "serviceKey": LAW_API_KEY, ...}
        # r = requests.get(url, params=params, timeout=10)
        # r.raise_for_status()
        # data = r.json()
        # return parse_to_briefs(data)  # 적절히 파싱

        # 데모 응답(가짜)
        return [
            {"title": "근로기준법 제50조(근로시간)", "snippet": "1주간의 근로시간은 휴게시간을 제외하고 40시간을 초과할 수 없다.", "ref": "법제처-데모"},
            {"title": "근로기준법 제55조(휴일)", "snippet": "사용자는 근로자에게 1주에 평균 1회 이상의 유급휴일을 주어야 한다.", "ref": "법제처-데모"},
        ][:limit]
    except Exception:
        return []

# =========================
# AI 응답 함수
# =========================
def generate_ai_answer(user_query: str, context_snippets: Optional[List[Dict[str, str]]] = None) -> str:
    """
    OpenAI/Azure OpenAI를 사용해 답변을 생성합니다.
    스트리밍 UI를 위해 토큰 단위로 출력합니다.
    """
    if client is None or MODEL_NAME is None:
        return "AI 엔진이 설정되어 있지 않아 답변을 생성할 수 없습니다. 관리자에게 키 설정을 요청하세요."

    system_prompt = (
        "너는 한국어 법률 비서야. 질문이 오면, 관련 법령 조항과 맥락을 근거로 명확하고 신중하게 답해."
        " 확실치 않은 내용은 추측하지 말고, 최신성/정확성 한계를 알려줘."
        " 마지막에 2~3줄로 핵심 요약을 덧붙여줘."
    )

    ctx_text = ""
    if context_snippets:
        bulleted = [f"- {c.get('title','')}: {c.get('snippet','')}" for c in context_snippets if c]
        ctx_text = "다음은 참고 맥락 자료야:\n" + "\n".join(bulleted)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{ctx_text}\n\n사용자 질문: {user_query}".strip()},
    ]

    # 스트리밍 생성
    answer_holder = st.empty()
    full_text = ""

    try:
        stream = client.chat.completions.create(
            model=MODEL_NAME,                 # ⚠️ Azure는 배포 이름, OpenAI는 모델명
            messages=messages,
            temperature=0.3,
            max_tokens=1200,
            stream=True,
        )

        for chunk in stream:
            delta = getattr(chunk.choices[0], "delta", None)
            if delta and getattr(delta, "content", None):
                piece = delta.content
                full_text += piece
                answer_holder.markdown(full_text)
        return full_text or "응답이 비어 있습니다."
    except Exception as e:
        st.error("모델 호출 중 오류가 발생했습니다.")
        st.code(traceback.format_exc())
        return f"오류: {e}"

# =========================
# 사이드바: 상태 및 설정 표시
# =========================
with st.sidebar:
    st.subheader("상태")
    st.write("엔진:", "Azure OpenAI(배포명)" if is_azure else ("OpenAI(공용 모델)" if client else "미설정"))
    st.write("모델/배포:", MODEL_NAME or "—")

    st.divider()
    st.subheader("도움말")
    st.markdown(
        """
        - `.streamlit/secrets.toml` 예시:
        ```toml
        LAW_API_KEY = "YOUR_LAW_KEY"

        [azure_openai]
        api_key = "YOUR_AZURE_KEY"
        endpoint = "https://YOUR-RESOURCE.openai.azure.com/"
        deployment = "YOUR_DEPLOYMENT_NAME"
        api_version = "2025-01-01-preview"
        ```
        - 일반 OpenAI 키가 있다면 `OPENAI_API_KEY="..."`를 추가하면 됩니다.
        """
    )

# =========================
# 메인 입력 영역
# =========================
st.markdown("#### 법령에 대한 질문을 입력하세요")
default_placeholder = "예: 근로기준법에서 정하는 최대 근로시간은 얼마인가요?"
user_text = st.text_input(" ", placeholder=default_placeholder, label_visibility="collapsed")

col1, col2 = st.columns([1, 4])
with col1:
    topk = st.number_input("참고 검색 개수(법제처)", min_value=0, max_value=10, value=2, step=1)
with col2:
    add_context = st.checkbox("법제처 Open API(예시)로 관련 조항 검색해 맥락에 포함", value=True, help="실제 연동 시 search_law_articles() 구현을 교체하세요.")

btn = st.button("전송", use_container_width=True, type="primary")

# =========================
# 동작
# =========================
if btn:
    if not user_text.strip():
        st.warning("질문을 입력하세요.")
        st.stop()

    # (선택) 법제처 맥락 수집
    snippets = search_law_articles(user_text, limit=int(topk)) if add_context else []

    with st.spinner("생성 중..."):
        answer = generate_ai_answer(user_text, context_snippets=snippets)

    if snippets:
        with st.expander("참고한 법제처 검색 요약(예시)"):
            for i, snip in enumerate(snippets, 1):
                st.markdown(f"**{i}. {snip.get('title','제목 없음')}**")
                st.write(snip.get("snippet", ""))
                if snip.get("ref"):
                    st.caption(f"출처: {snip['ref']}")

# 푸터
st.markdown("---")
st.caption("© 2025 POSCO E&C • 데모 앱")
