
# local_legal_analyzer.py
# -*- coding: utf-8 -*-
import os, io, re, time
from typing import List, Tuple
import streamlit as st
from utils_extract import extract_text_from_pdf, extract_text_from_docx, read_txt, sanitize
import requests
from bs4 import BeautifulSoup

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")

try:
    from openai import OpenAI, AzureOpenAI
except Exception:
    OpenAI = None
    AzureOpenAI = None

def get_llm_client():
    if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT and AzureOpenAI is not None:
        client = AzureOpenAI(api_key=AZURE_OPENAI_API_KEY, api_version="2024-02-01", azure_endpoint=AZURE_OPENAI_ENDPOINT)
        return ("azure", client)
    elif OPENAI_API_KEY and OpenAI is not None:
        client = OpenAI(api_key=OPENAI_API_KEY)
        return ("openai", client)
    else:
        return (None, None)

def fetch_url_text(url: str) -> str:
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if not (200 <= r.status_code < 400):
            return ""
    except Exception:
        return ""
    soup = BeautifulSoup(r.text, "html.parser")
    node = soup.select_one("main") or soup.select_one("article") or soup.select_one("body")
    text = node.get_text("\\n", strip=True) if node else soup.get_text("\\n", strip=True)
    return sanitize(text)

def combine_contexts(report_texts: List[Tuple[str, str]], law_texts: List[Tuple[str, str]]) -> str:
    blocks = []
    for name, txt in report_texts:
        blocks.append(f"# [사고보고서] {name}\\n{sanitize(txt)[:12000]}")
    for name, txt in law_texts:
        blocks.append(f"# [법령/자료] {name}\\n{sanitize(txt)[:12000]}")
    return "\\n\\n".join(blocks)

SYSTEM_PROMPT = "당신은 산업안전·건설 안전 분야 분석가입니다. 사고보고서와 법령/자료를 함께 검토해 요약, 의무/위반, 원인, 개선, 추가확인을 간결히 제시하세요."

USER_PROMPT_TEMPLATE = """아래 자료를 종합 분석해 주세요.

[분석 목표]
{goal}

[참조 자료]
{contexts}
"""

def run_llm(kind, client, model_or_deploy, prompt, temperature=0.2, max_tokens=1500):
    if kind == "azure":
        resp = client.chat.completions.create(
            model=model_or_deploy,
            messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    else:
        resp = client.chat.completions.create(
            model=model_or_deploy,
            messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

st.set_page_config(page_title="로컬 사고보고서 + 법령 GPT 분석기", page_icon="⚖️", layout="wide")
st.title("⚖️ 로컬 사고보고서 + 법령 GPT 분석기 (DB 없이 로컬)")

with st.sidebar:
    st.header("API 설정")
    mode = st.radio("LLM 선택", ["Azure OpenAI", "OpenAI", "오프라인(LLM 사용 안 함)"], index=0)

st.subheader("1) 사고보고서 업로드")
ups = st.file_uploader("PDF / DOCX / TXT (여러 개 가능)", type=["pdf","docx","txt"], accept_multiple_files=True)
reports: List[Tuple[str,str]] = []
if ups:
    for f in ups:
        name = f.name; data = f.read()
        ext = os.path.splitext(name)[1].lower()
        if ext == ".pdf":
            txt = extract_text_from_pdf(io.BytesIO(data))
        elif ext == ".docx":
            txt = extract_text_from_docx(io.BytesIO(data))
        else:
            txt = read_txt(io.BytesIO(data))
        reports.append((name, txt))
    st.success(f"{len(reports)}개 파일에서 텍스트 추출 완료")

st.subheader("2) 법령/기준 입력")
tab1, tab2 = st.tabs(["붙여넣기", "URL"])
law_texts: List[Tuple[str,str]] = []
with tab1:
    pasted = st.text_area("법령·기준 원문 (여러 건은 --- 로 구분)", height=200)
    if pasted.strip():
        for i, block in enumerate([p.strip() for p in pasted.split("\\n---\\n") if p.strip()], 1):
            law_texts.append((f"붙여넣기_{i}", block))
with tab2:
    urls = st.text_area("법령/판례/기준 URL (한 줄당 1개)", height=140)
    if st.button("URL에서 텍스트 가져오기"):
        ok = 0
        for line in urls.splitlines():
            u = line.strip()
            if not u: continue
            t = fetch_url_text(u)
            if t:
                ok += 1; law_texts.append((u, t))
        st.success(f"{ok}개 URL에서 텍스트 추출 완료") if ok else st.warning("가져온 텍스트 없음")

goal = st.text_area("3) 분석 목표(선택)", value="사고 원인, 관련 법령 위반 여부, 재발 방지 조치 제안", height=80)
temperature = st.slider("창의성(temperature)", 0.0, 1.0, 0.2, 0.1)
max_tokens = st.slider("응답 최대 토큰", 500, 4000, 1500, 100)
run = st.button("🔎 GPT로 분석하기", type="primary", use_container_width=True)

if run:
    if not reports:
        st.error("사고보고서를 한 개 이상 업로드하세요."); st.stop()
    contexts = combine_contexts(reports, law_texts)
    prompt = USER_PROMPT_TEMPLATE.format(goal=goal, contexts=contexts)

    if mode == "오프라인(LLM 사용 안 함)":
        st.warning("LLM API 미설정 – 프롬프트 미리보기만 표시합니다.")
        st.text_area("프롬프트", value=prompt[:10000], height=300); st.stop()

    kind, client = get_llm_client()
    model_or_deploy = os.environ.get("AZURE_OPENAI_DEPLOYMENT","gpt-4o-mini") if kind=="azure" else os.environ.get("OPENAI_MODEL","gpt-4o-mini")
    with st.spinner("분석 중..."):
        try:
            result = run_llm(kind, client, model_or_deploy, prompt, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:
            st.exception(e); st.stop()
    st.success("분석 완료"); st.markdown(result)
    ts = time.strftime("%Y%m%d_%H%M%S")
    st.download_button("결과 다운로드(.md)", data=result.encode("utf-8"), file_name=f"분석결과_{ts}.md", mime="text/markdown")
