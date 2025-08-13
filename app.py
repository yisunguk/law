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
# (NEW) ChatGPT 스타일 복사 버튼 렌더러
# =============================
def render_ai_with_copy(message: str, key: str = "ai"):
    """AI 답변을 예쁘게 렌더링하고 '복사' 버튼을 제공합니다."""
    safe_for_js = json.dumps(message)  # XSS/따옴표 이슈 방지
    components.html(
        f"""
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
        """,
        height=0,
    )

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
        # 필수 키 검증
        _ = azure["api_key"]
        _ = azure["endpoint"]
        _ = azure["deployment"]
        _ = azure["api_version"]
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
    st.session_state.messages = []  # [{timestamp, user_question, ai_response, law_data}]
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
        "serviceKey": urllib.parse.quote_plus(LAW_API_KEY),  # 요청 시점 인코딩
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
# 프롬프트 구성 유틸
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
    """Azure 미설정/오류 시 기본 답변"""
    return (
        f"**질문 요약:** {user_question}\n\n"
        f"**관련 법령(요약):**\n{format_law_context(law_data)}\n\n"
        f"*Azure OpenAI 설정이 없거나 호출 중 오류가 발생해 기본 답변을 제공합니다.*"
    )

# =============================
# Azure OpenAI 스트리밍 (안전 처리)
# =============================
def stream_chat_completion(messages, temperature=0.7, max_tokens=1000):
    """
    Azure OpenAI 스트리밍을 안전하게 순회하며 텍스트 덩어리를 yield 합니다.
    - choices가 없거나 빈 청크는 건너뜀
    - finish_reason 도착 시 종료
    """
    stream = client.chat.completions.create(
        model=AZURE["deployment"],  # deployment 이름 사용
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
# 과거 대화 렌더
# =============================
for m in st.session_state.messages:
    st.markdown(f'<div class="user-message"><strong>사용자:</strong><br>{m["user_question"]}</div>', unsafe_allow_html=True)
    # 과거 대화는 복사 버튼 버전으로 출력
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
    full_text = ""

    # 프롬프트 구성
    law_ctx = format_law_context(law_data)
    prompt = f"""
당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다.

사용자 질문: {user_q}

관련 법령 정보(요약):
{law_ctx}

위의 정보를 바탕으로 아래 형식으로 답변하세요.
### 법률자문서(전문형 예시)

제목: 납품 지연에 따른 계약 해제 가능 여부에 관한 법률 검토
수신: ○○ 주식회사 대표이사 귀하
작성: 법무법인 ○○ / 변호사 홍길동
작성일: 2025. 8. 14.

Ⅰ. 자문 의뢰의 범위
본 자문은 귀사가 체결한 납품계약에 관한 채무불이행 사유 발생 시 계약 해제 가능 여부 및 그에 따른 법적 효과를 검토하는 것을 목적으로 합니다.

Ⅱ. 사실관계
(사실관계 요약은 동일하되, 문장을 완전하게 작성하고 시간 순서 및 법률적 평가 가능하도록 기술)

Ⅲ. 관련 법령 및 판례

1. 민법 제544조(채무불이행에 의한 해제)
   > 당사자 일방이 채무를 이행하지 아니한 때에는 상대방은 상당한 기간을 정하여 이행을 최고하고, 그 기간 내에 이행이 없는 때에는 계약을 해제할 수 있다.
2. 대법원 2005다14285 판결
   > 매매계약에 따른 목적물 인도 또는 납품이 기한 내 이루어지지 않은 경우, 상당한 기간을 정하여 최고하였음에도 불구하고 이행이 없는 때에는 계약 해제가 가능함을 판시.

Ⅳ. 법률적 분석

1. 채무불이행 여부
   계약상 납품 기일(2025. 7. 15.)을 도과한 이후 30일 이상 지연된 사실은 채무불이행에 해당함.
   지연 사유인 ‘원자재 수급 불가’가 불가항력에 해당하는지 여부가 쟁점이나, 일반적인 원자재 수급 곤란은 불가항력으로 인정되지 않는 판례 경향 존재.

2. 계약 해제 요건 충족 여부
   상당한 기간(예: 7일)을 정한 최고 후에도 이행이 없을 경우, 민법 제544조에 따라 계약 해제가 가능함.
   해제 시 계약금 반환 및 손해배상 청구 가능성이 있음.

3. 손해배상 범위
   계약 해제와 별도로, 귀사가 입은 손해(대체 구매 비용, 지연으로 인한 생산 차질 등)가 입증되면 채무불이행에 따른 손해배상 청구 가능.

Ⅴ. 결론
귀사는 서면 최고를 거친 후 계약 해제 권리를 행사할 수 있으며, 계약금 반환과 별도로 손해배상을 청구할 수 있습니다.
다만, 손해액 산정 및 입증을 위해 납품 지연으로 인한 비용 자료를 사전에 확보하는 것이 필요합니다.

답변은 한국어로 쉽게 설명하세요.
"""

    with st.spinner("🤖 AI가 답변을 생성하는 중..."):
        if client is None:
            # Azure 미설정 → 기본 답변
            full_text = fallback_answer(user_q, law_data)
            # 복사 버튼 버전으로 출력
            render_ai_with_copy(full_text, key=str(int(time.time())))
        else:
            # 스트리밍 출력 (타자 효과)
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
                    full_text += piece
                    ai_placeholder.markdown(
                        f'<div class="ai-message"><strong>AI 어시스턴트:</strong><br>{full_text}</div>',
                        unsafe_allow_html=True,
                    )
                    time.sleep(0.02)
                # 스트리밍 끝: 복사 버튼 UI로 교체
                ai_placeholder.empty()
                render_ai_with_copy(full_text, key=str(int(time.time())))
            except Exception as e:
                # 스트리밍 중 에러가 나면 비-스트리밍 폴백
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

    # 3) 대화 저장 & 리렌더
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
    st.rerun()

# =============================
# 푸터
# =============================
st.markdown(
    '<div class="footer">제공되는 정보는 참고용이며, 정확한 법률 상담은 전문가에게 문의하시기 바랍니다.</div>',
    unsafe_allow_html=True,
)
