# app.py
import time
import json
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI

# =============================
# 스트림릿 페이지 설정 & 간단 스타일
# =============================
st.set_page_config(page_title="법제처 AI 챗봇", page_icon="⚖️", layout="wide")
st.markdown(
    """
    <style>
      .header {text-align:center;padding:1.2rem;border-radius:12px;background:linear-gradient(135deg,#8b5cf6,#a78bfa);color:#fff;margin-bottom:1.2rem}
      .user-message {background:#2563eb;color:#fff;padding:1rem;border-radius:16px 16px 0 16px;margin:0.6rem 0;max-width:80%;margin-left:auto}
      .ai-message {background:#fff;color:#111;padding:1rem;border-radius:16px 16px 16px 0;margin:0.6rem 0;max-width:80%;box-shadow:0 2px 8px rgba(0,0,0,.08)}
      .typing-indicator {display:inline-block;width:18px;height:18px;border:3px solid #eee;border-top:3px solid #8b5cf6;border-radius:50%;animation:spin 1s linear infinite}
      @keyframes spin {0%{transform:rotate(0)}100%{transform:rotate(360deg)}}
      .footer {text-align:center;color:#777;margin-top:2rem}
      .copy-wrap {background:#fff;color:#333;padding:16px;border-radius:16px 16px 16px 0;
                  box-shadow:0 2px 8px rgba(0,0,0,.08);margin:12px 0;max-width:900px;}
      .copy-head {display:flex;justify-content:space-between;align-items:center;gap:12px}
      .copy-btn {display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid #ddd;border-radius:8px;
                 background:#f8f9fa;cursor:pointer;font-size:12px}
      .copy-body {margin-top:10px;line-height:1.6;white-space:pre-wrap}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="header"><h2>⚖️ 법제처 인공지능 법률 상담 플랫폼</h2><div>법제처 공식 데이터와 인공지능 기술을 결합한 전문 법률 정보 제공 서비스</div></div>',
    unsafe_allow_html=True,
)

# =============================
# ChatGPT 스타일 복사 버튼 렌더러
# =============================
def render_ai_with_copy(message: str, key: str = "ai"):
    """AI 답변을 예쁘게 렌더링하고 '복사' 버튼을 제공합니다."""
    safe_for_js = json.dumps(message)  # XSS/따옴표 이슈 방지
    html_string = f"""
        <div class="copy-wrap">
          <div class="copy-head">
            <strong>AI 어시스턴트</strong>
            <button id="copy-{key}" class="copy-btn" title="클립보드로 복사">복사</button>
          </div>
          <div class="copy-body">{message}</div>
        </div>
        <script>
          const btn = document.getElementById("copy-{key}");
          if (btn) {{
            btn.addEventListener("click", async () => {{
              try {{
                await navigator.clipboard.writeText({safe_for_js});
                const old = btn.textContent;
                btn.textContent = "복사됨!";
                setTimeout(()=>btn.textContent = old, 1200);
              }} catch (e) {{
                alert("복사에 실패했습니다: " + e);
              }}
            }});
          }}
        </script>
    """
    # ⚠️ height=0 대신 고정 높이로 레이아웃 안정화
    components.html(html_string, height=220)

# =============================
# Secrets 로딩
# =============================
def load_secrets():
    law_key = None
    azure = None
    try:
        law_key = st.secrets["LAW_API_KEY"]
    except Exception:
        st.error("`LAW_API_KEY`가 없습니다. Streamlit Cloud → App settings → Secrets 에 추가하세요.")

    try:
        azure = st.secrets["azure_openai"]
        _ = azure["api_key"]; _ = azure["endpoint"]; _ = azure["deployment"]; _ = azure["api_version"]
    except Exception:
        st.error("[azure_openai] 섹션(api_key, endpoint, deployment, api_version)이 없거나 누락되었습니다.")
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
        st.error(f"Azure OpenAI 클라이언트 초기화 실패: {e}")

# =============================
# 세션 상태
# =============================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False

# =============================
# 법제처 API 호출 (HTTPS 우선, HTTP 폴백)
# =============================
@st.cache_data(show_spinner=False, ttl=300)
def search_law_data(query: str, num_rows: int = 5):
    """법제처 API에서 법령 목록을 조회합니다."""
    if not LAW_API_KEY:
        return [], None, "LAW_API_KEY 미설정"

    params = {
        "serviceKey": urllib.parse.quote_plus(LAW_API_KEY),
        "target": "law",
        "query": query,
        "numOfRows": max(1, int(num_rows)),
        "pageNo": 1,
    }

    endpoints = [
        "https://apis.data.go.kr/1170000/law/lawSearchList.do",
        "http://apis.data.go.kr/1170000/law/lawSearchList.do",
    ]

    last_err = None
    for url in endpoints:
        try:
            res = requests.get(url, params=params, timeout=15)
            res.raise_for_status()
            root = ET.fromstring(res.text)

            laws = []
            for law in root.findall(".//law"):
                laws.append(
                    {
                        "법령명": law.findtext("법령명한글", default=""),
                        "법령약칭명": law.findtext("법령약칭명", default=""),
                        "소관부처명": law.findtext("소관부처명", default=""),
                        "법령구분명": law.findtext("법령구분명", default=""),
                        "시행일자": law.findtext("시행일자", default=""),
                        "공포일자": law.findtext("공포일자", default=""),
                        "법령상세링크": law.findtext("법령상세링크", default=""),
                    }
                )
            return laws, url, None
        except Exception as e:
            last_err = e
            continue

    return [], None, f"법제처 API 연결 실패: {last_err}"

# =============================
# 프롬프트/폴백 유틸
# =============================
def format_law_context(law_data):
    if not law_data:
        return "관련 법령 검색 결과가 없습니다."
    ctx = []
    for i, law in enumerate(law_data, 1):
        ctx.append(
            f"{i}. {law['법령명']} ({law['법령구분명']})\n"
            f"   - 소관부처: {law['소관부처명']}\n"
            f"   - 시행일자: {law['시행일자']} / 공포일자: {law['공포일자']}\n"
            f"   - 링크: {law['법령상세링크'] or '없음'}"
        )
    return "\n\n".join(ctx)

def fallback_answer(user_question, law_data):
    return (
        f"**질문 요약:** {user_question}\n\n"
        f"**관련 법령(요약):**\n{format_law_context(law_data)}\n\n"
        f"*Azure OpenAI 설정이 없거나 호출 중 오류가 발생해 기본 답변을 제공합니다.*"
    )

# =============================
# Azure OpenAI 스트리밍 (안전 처리)
# =============================
def stream_chat_completion(messages, temperature=0.7, max_tokens=1000):
    stream = client.chat.completions.create(
        model=AZURE["deployment"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        try:
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue
            choice = chunk.choices[0]
            if getattr(choice, "finish_reason", None):
                break
            delta = getattr(choice, "delta", None)
            text = getattr(delta, "content", None) if delta else None
            if text:
                yield text
        except Exception:
            continue

# =============================
# 사이드바
# =============================
with st.sidebar:
    st.markdown("### ⚙️ 옵션")
    num_rows = st.number_input("참고 검색 개수(법제처)", min_value=1, max_value=10, value=2, step=1)
    include_search = st.checkbox("법제처 Open API로 관련 조항 검색해 맥락에 포함", value=True)
    st.divider()
    st.metric("총 질문 수", len(st.session_state.messages))
    if st.session_state.messages:
        st.metric("마지막 질문", st.session_state.messages[-1]["timestamp"])
    if st.button("🗑️ 대화 기록 초기화"):
        st.session_state.messages.clear()
        st.rerun()

# =============================
# 과거 대화 렌더 (복사 버튼 포함)
# =============================
for m in st.session_state.messages:
    st.markdown(f'<div class="user-message"><strong>사용자:</strong><br>{m["user_question"]}</div>', unsafe_allow_html=True)
    render_ai_with_copy(m["ai_response"], key=f"hist-{m['timestamp']}")
    if m.get("law_data"):
        with st.expander("📋 관련 법령 정보 보기"):
            for i, law in enumerate(m["law_data"], 1):
                st.write(f"**{i}. {law['법령명']}** ({law['법령구분명']})")
                st.write(f"- 소관부처: {law['소관부처명']}")
                st.write(f"- 시행일자: {law['시행일자']} / 공포일자: {law['공포일자']}")
                if law["법령상세링크"]:
                    st.write(f"- 링크: {law['법령상세링크']}")
    st.divider()

# =============================
# 입력 & 처리
# =============================
user_q = st.text_input("법령에 대한 질문을 입력하세요", placeholder="예) 근로기준법에서 정하는 최대 근로시간은 얼마인가요?")
send = st.button("전송", type="primary", use_container_width=True)

if send and user_q.strip():
    st.session_state.is_processing = True

    # 1) 법제처 검색
    law_data, used_endpoint, err = ([], None, None)
    if include_search:
        with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
            law_data, used_endpoint, err = search_law_data(user_q, num_rows=num_rows)
        if used_endpoint:
            st.caption(f"법제처 API endpoint: `{used_endpoint}`")
        if err:
            st.warning(err)

    # 2) AI 응답
    ai_placeholder = st.empty()
    full_text, buffer = "", ""

    # 프롬프트
    law_ctx = format_law_context(law_data)
    prompt = f"""
당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다.

사용자 질문: {user_q}

관련 법령 정보(요약):
{law_ctx}

위의 정보를 바탕으로 아래 형식으로 답변하세요.
1) 질문에 대한 직접적인 답변
2) 관련 법령의 구체적인 내용 설명
3) 참고/주의사항
답변은 한국어로 쉽게 설명하세요.
"""

    with st.spinner("🤖 AI가 답변을 생성하는 중..."):
        if client is None:
            full_text = fallback_answer(user_q, law_data)
            render_ai_with_copy(full_text, key=str(int(time.time())))
        else:
            # 타자 효과 진행
            ai_placeholder.markdown(
                """
                <div class="ai-message">
                  <strong>AI 어시스턴트:</strong><br>
                  <div class="typing-indicator"></div> 답변을 생성하고 있습니다...
                </div>
                """,
                unsafe_allow_html=True,
            )
            try:
                messages = [
                    {"role": "system", "content": "당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다."},
                    {"role": "user", "content": prompt},
                ]
                for piece in stream_chat_completion(messages, temperature=0.7, max_tokens=1000):
                    buffer += piece
                    # 🔧 너무 잦은 리렌더링 방지: 80자마다 갱신
                    if len(buffer) >= 80:
                        full_text += buffer
                        buffer = ""
                        ai_placeholder.markdown(
                            f'<div class="ai-message"><strong>AI 어시스턴트:</strong><br>{full_text}</div>',
                            unsafe_allow_html=True,
                        )
                        time.sleep(0.02)
                # 남은 버퍼 반영
                if buffer:
                    full_text += buffer
                    ai_placeholder.markdown(
                        f'<div class="ai-message"><strong>AI 어시스턴트:</strong><br>{full_text}</div>',
                        unsafe_allow_html=True,
                    )
                # ✅ 더 이상 placeholder를 비우지 않고, 아래에 복사 카드 "추가" 렌더
                render_ai_with_copy(full_text, key=str(int(time.time())))
            except Exception:
                try:
                    resp = client.chat.completions.create(
                        model=AZURE["deployment"],
                        messages=messages,
                        max_tokens=1000,
                        temperature=0.7,
                        stream=False,
                    )
                    full_text = resp.choices[0].message.content
                    render_ai_with_copy(full_text, key=str(int(time.time())))
                except Exception as e2:
                    full_text = fallback_answer(user_q, law_data) + f"\n\n(추가 정보: {e2})"
                    render_ai_with_copy(full_text, key=str(int(time.time())))

    # 3) 대화 저장 (페이지 재실행 없이 유지)
    st.session_state.messages.append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_question": user_q,
            "ai_response": full_text,
            "law_data": law_data,
        }
    )
    st.session_state.is_processing = False
    st.success("✅ 답변이 완성되었습니다!")
    # ❌ st.rerun() 제거 — 답변창이 갑자기 사라지는 현상 방지

# =============================
# 푸터
# =============================
st.markdown(
    '<div class="footer">제공되는 정보는 참고용이며, 정확한 법률 상담은 전문가에게 문의하시기 바랍니다.</div>',
    unsafe_allow_html=True,
)
