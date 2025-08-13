import streamlit as st
import requests
import xml.etree.ElementTree as ET
import urllib.parse
from requests.exceptions import SSLError, ConnectionError, ReadTimeout
from datetime import datetime
from openai import OpenAI
import time

# =============================
# 페이지 설정
# =============================
st.set_page_config(
    page_title="법제처 AI 챗봇",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =============================
# CSS 스타일링
# =============================
st.markdown("""
<style>
    .main-header { text-align: center; padding: 2rem 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 15px; margin-bottom: 2rem; }
    .chat-container { background: #f8f9fa; border-radius: 15px; padding: 1rem; margin: 1rem 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    .user-message { background: #007bff; color: white; padding: 1rem; border-radius: 15px 15px 0 15px; margin: 1rem 0; max-width: 80%; margin-left: auto; }
    .ai-message { background: white; color: #333; padding: 1rem; border-radius: 15px 15px 15px 0; margin: 1rem 0; max-width: 80%; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    .input-container { position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 1rem; border-top: 1px solid #e0e0e0; z-index: 1000; }
    .stTextInput > div > div > input { border-radius: 25px; border: 2px solid #e0e0e0; padding: 0.75rem 1rem; font-size: 16px; }
    .stButton > button { border-radius: 25px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; color: white; padding: 0.75rem 1.5rem; font-weight: 600; }
    .sidebar-content { background: #f8f9fa; padding: 1rem; border-radius: 10px; margin: 1rem 0; }
    .metric-card { background: white; padding: 1rem; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin: 0.5rem 0; }
    .typing-indicator { display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #667eea; border-radius: 50%; animation: spin 1s linear infinite; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .law-info { background: #e3f2fd; border-left: 4px solid #2196f3; padding: 1rem; margin: 1rem 0; border-radius: 5px; }
    .footer { text-align: center; color: #666; padding: 2rem 0; margin-top: 4rem; }
</style>
""", unsafe_allow_html=True)

# =============================
# 시크릿 로딩 (하드코딩 제거)
# =============================
def load_secrets():
    """
    secrets.toml이 없거나 키가 없으면 사용자에게 경고만 띄우고 앱은 계속 동작하게 함.
    """
    openai_key = None
    law_key = None
    try:
        openai_key = st.secrets["OPENAI_API_KEY"]
        law_key = st.secrets["LAW_API_KEY"]
    except Exception:
        # secrets.toml이 없거나 키가 누락된 경우
        st.error("`secrets.toml`을 찾지 못했거나 키가 없습니다. `.streamlit/secrets.toml`에 OPENAI_API_KEY와 LAW_API_KEY를 설정하세요.")
    return openai_key, law_key

OPENAI_API_KEY, LAW_API_KEY = load_secrets()

# OpenAI 클라이언트 초기화
client = None
if OPENAI_API_KEY:
    # 최신 경량 모델 권장(원하시면 gpt-3.5-turbo로 바꿀 수 있습니다)
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    st.warning("⚠️ OpenAI API 키가 없어 AI 답변 기능이 제한됩니다.")

# =============================
# 세션 상태
# =============================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False

# =============================
# 법제처 API
# =============================
import requests
from requests.exceptions import SSLError, ConnectionError, ReadTimeout

def search_law_data(query, num_rows=5):
    """법제처 API를 호출하여 법령 데이터를 검색합니다. (HTTPS 우선, HTTP 폴백)"""
    if not LAW_API_KEY:
        st.error("LAW_API_KEY가 설정되지 않았습니다. secrets.toml을 확인하세요.")
        return []

    params = {
        "serviceKey": urllib.parse.quote_plus(LAW_API_KEY),  # 키는 원본 저장, 요청 시 인코딩
        "target": "law",
        "query": query,
        "numOfRows": num_rows,
        "pageNo": 1
    }

    endpoints = [
        "https://apis.data.go.kr/1170000/law/lawSearchList.do",  # 우선 시도
        "http://apis.data.go.kr/1170000/law/lawSearchList.do",   # 폴백
    ]

    last_err = None
    for url in endpoints:
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)

            # 간단한 유효성 체크 (빈 결과/오류 메시지 대비)
            if root.find(".//law") is None and root.find(".//Law") is None:
                # 응답이 XML 형식 오류이거나 결과 없음일 수 있음 → 그대로 처리
                pass

            # UI에 어떤 엔드포인트를 사용했는지 표시(디버깅/운영 확인용)
            st.caption(f"법제처 API endpoint: `{url}`")

            laws = []
            for law in root.findall('.//law'):
                laws.append({
                    "법령명": law.findtext('법령명한글', default=""),
                    "법령약칭명": law.findtext('법령약칭명', default=""),
                    "소관부처명": law.findtext('소관부처명', default=""),
                    "법령구분명": law.findtext('법령구분명', default=""),
                    "시행일자": law.findtext('시행일자', default=""),
                    "공포일자": law.findtext('공포일자', default=""),
                    "법령상세링크": law.findtext('법령상세링크', default="")
                })
            return laws

        except (SSLError, ConnectionError, ReadTimeout) as e:
            last_err = e
            continue  # 다음 엔드포인트(HTTP)로 폴백
        except Exception as e:
            st.error(f"❌ 법제처 API 호출 중 오류가 발생했습니다: {e}")
            return []

    # 모든 엔드포인트 실패
    st.error(f"법제처 API 연결 실패: {last_err}")
    return []


# =============================
# AI 응답 생성
# =============================
def format_law_context(law_data):
    context = ""
    for i, law in enumerate(law_data, 1):
        context += f"{i}. {law['법령명']} ({law['법령구분명']})\n"
        context += f"   - 소관부처: {law['소관부처명']}\n"
        context += f"   - 시행일자: {law['시행일자']}\n"
        context += f"   - 공포일자: {law['공포일자']}\n\n"
    return context

def generate_fallback_response(user_question, law_data):
    law_context = format_law_context(law_data)
    return f"""
**질문에 대한 답변:**

'{user_question}'에 대한 관련 법령 정보를 찾았습니다.

**관련 법령 목록:**
{law_context}

**참고사항:**
- 위 법령들은 귀하의 질문과 관련된 법령들입니다.
- 더 자세한 내용은 각 법령의 본문을 참조하시기 바랍니다.
- 정확한 법률 상담은 전문가에게 문의하시기 바랍니다.

*OpenAI API 키가 설정되지 않아 기본 답변을 제공합니다.*
"""

def generate_ai_response_stream(user_question, law_data):
    try:
        if not client:
            return generate_fallback_response(user_question, law_data)

        law_context = format_law_context(law_data)
        prompt = f"""
당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다.

사용자 질문: {user_question}

관련 법령 정보:
{law_context}

위의 법령 정보를 바탕으로 사용자의 질문에 대해 정확하고 도움이 되는 답변을 제공해주세요.
답변은 다음 형식으로 구성해주세요:

1. 질문에 대한 직접적인 답변
2. 관련 법령의 구체적인 내용 설명
3. 추가로 참고할 만한 정보나 주의사항

답변은 한국어로 작성하고, 법률 용어는 일반인이 이해하기 쉽게 설명해주세요.
"""

        # 최신 경량 모델 예시: gpt-4o-mini (원하면 기존 gpt-3.5-turbo로 변경 가능)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7,
            stream=True
        )
        return response

    except Exception as e:
        st.error(f"❌ AI 답변 생성 중 오류가 발생했습니다: {str(e)}")
        return None

# =============================
# 저장/표시 유틸
# =============================
def save_conversation(user_question, ai_response, law_data):
    conversation = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_question": user_question,
        "ai_response": ai_response,
        "law_data": law_data
    }
    st.session_state.messages.append(conversation)

def display_law_info(law_data):
    if not law_data:
        return
    st.markdown("### 📋 관련 법령 정보")
    for i, law in enumerate(law_data, 1):
        with st.expander(f"{i}. {law['법령명']} ({law['법령구분명']})"):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**소관부처:** {law['소관부처명']}")
                st.write(f"**시행일자:** {law['시행일자']}")
            with col2:
                st.write(f"**공포일자:** {law['공포일자']}")
                if law['법령상세링크']:
                    st.write(f"**상세링크:** [법령 상세보기]({law['법령상세링크']})")

# =============================
# UI
# =============================
st.markdown("""
<div class="main-header">
    <h1>⚖️ 법제처 AI 챗봇</h1>
    <p>법제처 Open API와 OpenAI를 활용한 지능형 법령 상담 서비스</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📋 사용 안내")
    st.markdown("""
    이 챗봇은 법제처 Open API와 OpenAI를 활용하여 
    대한민국의 법령 정보에 대한 질문에 답변합니다.
    
    **사용 방법:**
    1. 아래 입력창에 법령 관련 질문을 입력하세요
    2. Enter 키를 누르거나 전송 버튼을 클릭하세요
    3. AI가 관련 법령을 검색하고 답변을 제공합니다
    
    **예시 질문:**
    - "근로기준법에 대해 알려주세요"
    - "개인정보보호법 관련 규정은?"
    - "교통법규 위반 시 처벌은?"
    """)
    st.metric("총 질문 수", len(st.session_state.messages))
    if st.session_state.messages:
        latest_msg = st.session_state.messages[-1]
        st.metric("마지막 질문", latest_msg["timestamp"])
    if st.button("🗑️ 대화 기록 초기화", type="secondary"):
        st.session_state.messages = []
        st.success("대화 기록이 초기화되었습니다.")
        st.rerun()

chat_container = st.container()

with chat_container:
    for message in st.session_state.messages:
        st.markdown(f"""
        <div class="user-message">
            <strong>사용자:</strong><br>
            {message['user_question']}
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="ai-message">
            <strong>AI 어시스턴트:</strong><br>
            {message['ai_response']}
        </div>
        """, unsafe_allow_html=True)

        if message['law_data']:
            display_law_info(message['law_data'])

        st.markdown("---")

st.markdown("---")
input_container = st.container()

with input_container:
    col1, col2 = st.columns([4, 1])
    with col1:
        user_input = st.text_input(
            "💬 법령에 대한 질문을 입력하세요:",
            placeholder="예: 근로기준법에서 정하는 최대 근로시간은 얼마인가요?",
            key="user_input",
            on_change=None
        )
    with col2:
        send_button = st.button("🚀 전송", type="primary", use_container_width=True)

    if (user_input and send_button):
        if user_input.strip():
            st.session_state.is_processing = True

            st.markdown(f"""
            <div class="user-message">
                <strong>사용자:</strong><br>
                {user_input}
            </div>
            """, unsafe_allow_html=True)

            ai_response_placeholder = st.empty()

            with st.spinner("🔍 법령 정보를 검색하고 답변을 생성하는 중..."):
                law_data = search_law_data(user_input)

                if law_data:
                    if client:
                        stream_response = generate_ai_response_stream(user_input, law_data)
                        if stream_response:
                            full_response = ""
                            ai_response_placeholder.markdown("""
                            <div class="ai-message">
                                <strong>AI 어시스턴트:</strong><br>
                                <div class="typing-indicator"></div> 답변을 생성하고 있습니다...
                            </div>
                            """, unsafe_allow_html=True)

                            for chunk in stream_response:
                                if hasattr(chunk.choices[0].delta, "content") and chunk.choices[0].delta.content:
                                    full_response += chunk.choices[0].delta.content
                                    ai_response_placeholder.markdown(f"""
                                    <div class="ai-message">
                                        <strong>AI 어시스턴트:</strong><br>
                                        {full_response}
                                    </div>
                                    """, unsafe_allow_html=True)
                                    time.sleep(0.03)
                        else:
                            full_response = "죄송합니다. 답변을 생성하는 중에 오류가 발생했습니다."
                    else:
                        full_response = generate_fallback_response(user_input, law_data)

                    save_conversation(user_input, full_response, law_data)
                    display_law_info(law_data)
                    st.success("✅ 답변이 완성되었습니다!")
                else:
                    st.warning("⚠️ 관련 법령을 찾을 수 없습니다. 다른 키워드로 검색해보세요.")

            st.session_state.is_processing = False
            st.rerun()
        else:
            st.warning("⚠️ 질문을 입력해주세요.")

st.markdown("""
<div class="footer">
    <p>이 챗봇은 법제처 Open API와 OpenAI를 활용하여 개발되었습니다.</p>
    <p>제공되는 정보는 참고용이며, 정확한 법률 상담은 전문가에게 문의하시기 바랍니다.</p>
</div>
""", unsafe_allow_html=True)
