# app.py — POSCO E&C Law Chat (stable, secrets-based)

import os
import time
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests
import xml.etree.ElementTree as ET
import streamlit as st
from openai import AzureOpenAI

# =========================
# Page Configuration
# =========================
st.set_page_config(
    page_title="법제처 AI 챗봇", 
    page_icon="⚖️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================
# Secrets Management
# =========================
def _get_secret(path: list, default=None):
    """Secrets에서 값을 안전하게 가져오는 함수"""
    try:
        base = st.secrets
        for p in path:
            base = base[p]
        return base
    except Exception:
        return default

# 공공데이터포털 ServiceKey
DATA_PORTAL_SERVICE_KEY = _get_secret(["DATA_PORTAL_SERVICE_KEY"], "")

# Azure OpenAI
AZURE_OPENAI_API_KEY = _get_secret(["azure_openai", "api_key"], "")
AZURE_OPENAI_API_BASE = _get_secret(["azure_openai", "endpoint"], "")
AZURE_OPENAI_DEPLOYMENT = _get_secret(["azure_openai", "deployment"], "")
AZURE_OPENAI_API_VERSION = _get_secret(["azure_openai", "api_version"], "2024-06-01")

# Firebase
FIREBASE_CONFIG = _get_secret(["firebase"], None)

# =========================
# Firebase Integration (Optional)
# =========================
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    firebase_admin = None
    firestore = None

def init_firebase():
    """Firebase 초기화"""
    if firebase_admin is None or FIREBASE_CONFIG is None:
        return None
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(dict(FIREBASE_CONFIG))
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_CONFIG["project_id"]})
        return firestore.client()
    except Exception:
        return None

db = init_firebase()

def _threads_col():
    """Firestore threads 컬렉션 참조"""
    return None if db is None else db.collection("threads")

def load_thread(thread_id: str) -> List[Dict[str, Any]]:
    """특정 스레드의 메시지들을 로드"""
    if db is None:
        return []
    try:
        docs = (
            _threads_col()
            .document(thread_id)
            .collection("messages")
            .order_by("ts")
            .stream()
        )
        return [d.to_dict() for d in docs]
    except Exception:
        return []

def save_message(thread_id: str, msg: Dict[str, Any]):
    """메시지를 Firestore에 저장"""
    if db is None:
        return
    try:
        _threads_col().document(thread_id).set(
            {"updated_at": datetime.utcnow().isoformat()}, merge=True
        )
        _threads_col().document(thread_id).collection("messages").add(
            {**msg, "ts": msg.get("ts", time.time())}
        )
    except Exception:
        pass

# =========================
# Enhanced ChatGPT Style CSS
# =========================
st.markdown(
    """
<style>
/* 전체 폰트 설정 */
* {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
}

/* 헤더 스타일 */
.chat-header {
    text-align: center;
    padding: 2rem 0;
    margin-bottom: 1.5rem;
    color: white;
    border-radius: 16px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
}

.chat-header h1 {
    margin: 0;
    font-size: 2.5rem;
    font-weight: 700;
    text-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.chat-header p {
    margin: 0.5rem 0 0 0;
    font-size: 1.1rem;
    opacity: 0.9;
}

/* 사이드바 스타일 */
.sidebar .sidebar-content {
    background: #f8f9fa;
    border-right: 1px solid #e9ecef;
}

/* 사이드바 버튼 스타일 */
.sidebar-button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    border-radius: 12px;
    padding: 12px 20px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}

.sidebar-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}

/* 대화 히스토리 아이템 */
.chat-history-item {
    background: #ffffff;
    color: #495057;
    padding: 1rem;
    margin: 0.5rem 0;
    border-radius: 12px;
    border-left: 4px solid #667eea;
    font-size: 0.9rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    transition: all 0.3s ease;
    cursor: pointer;
}

.chat-history-item:hover {
    background: #f8f9fa;
    transform: translateX(4px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* 채팅 컨테이너 */
.chat-container {
    max-width: 900px;
    margin: 0 auto;
    padding: 0 1rem;
    padding-bottom: 120px; /* 하단 채팅창 공간 확보 */
}

/* 채팅 메시지 */
.chat-message {
    display: flex;
    margin: 2rem 0;
    align-items: flex-start;
    animation: fadeInUp 0.5s ease-out;
}

.chat-message.user {
    flex-direction: row-reverse;
}

.chat-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    margin: 0 16px;
    flex-shrink: 0;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.chat-avatar.user {
    background: linear-gradient(135deg, #10a37f 0%, #0d8a6f 100%);
    color: white;
}

.chat-avatar.assistant {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
}

.chat-content {
    background: #ffffff;
    padding: 1.25rem;
    border-radius: 20px;
    max-width: 75%;
    word-wrap: break-word;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    border: 1px solid #e9ecef;
    line-height: 1.6;
}

.chat-message.user .chat-content {
    background: linear-gradient(135deg, #10a37f 0%, #0d8a6f 100%);
    color: white;
    box-shadow: 0 4px 20px rgba(16, 163, 127, 0.3);
}

/* 하단 고정 채팅창 스타일 */
.fixed-chat-input {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    border-top: 1px solid #e9ecef;
    padding: 1rem;
    z-index: 1000;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.1);
}

.fixed-chat-input .stForm {
    max-width: 900px;
    margin: 0 auto;
}

.fixed-chat-input .stTextArea textarea {
    border-radius: 20px;
    border: 2px solid #e9ecef;
    padding: 12px 16px;
    font-size: 16px;
    resize: none;
    transition: all 0.3s ease;
}

.fixed-chat-input .stTextArea textarea:focus {
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.fixed-chat-input .stButton > button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    border-radius: 20px;
    padding: 12px 24px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}

.fixed-chat-input .stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}

/* 로딩 애니메이션 */
.typing-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 16px 20px;
    background: #f8f9fa;
    border-radius: 20px;
    margin: 1rem 0;
}

.typing-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #667eea;
    animation: typing 1.4s infinite ease-in-out;
}

.typing-dot:nth-child(1) { animation-delay: -0.32s; }
.typing-dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
    0%, 80%, 100% { 
        transform: scale(0); 
        opacity: 0.5; 
    }
    40% { 
        transform: scale(1); 
        opacity: 1; 
    }
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* 반응형 디자인 */
@media (max-width: 768px) {
    .chat-container {
        max-width: 100%;
        padding: 0 0.5rem;
        padding-bottom: 120px;
    }
    
    .chat-content {
        max-width: 85%;
    }
    
    .chat-header h1 {
        font-size: 2rem;
    }
    
    .fixed-chat-input {
        padding: 0.5rem;
    }
}

/* 스크롤바 스타일 */
::-webkit-scrollbar {
    width: 8px;
}

::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 4px;
}

::-webkit-scrollbar-thumb {
    background: #667eea;
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: #5a6fd8;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# Enhanced Header
# =========================
st.markdown(
    """
<div class="chat-header">
    <h1>⚖️ 법제처 AI 챗봇</h1>
    <p>공공데이터포털 + Azure OpenAI + ChatGPT 스타일 인터페이스</p>
</div>
""",
    unsafe_allow_html=True,
)

# =========================
# Session State Management
# =========================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())[:12]

def _get_thread_id_from_query() -> str:
    """URL 쿼리 파라미터에서 스레드 ID를 가져오는 함수"""
    try:
        q = st.query_params or {}
        t = q.get("t", "")
        return t if isinstance(t, str) else (t[0] if t else "")
    except Exception:
        try:
            qp = st.experimental_get_query_params() or {}
            t = qp.get("t", [""])
            return t[0] if isinstance(t, list) else t
        except Exception:
            return ""

# 과거 대화 복원
restored = load_thread(st.session_state.thread_id)
if restored:
    st.session_state.messages = restored

# =========================
# Enhanced Sidebar
# =========================
with st.sidebar:
    st.markdown("## 💬 대화 관리")
    
    # 새 대화 시작
    if st.button("🆕 새 대화 시작", use_container_width=True, key="new_chat"):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())[:12]
        st.rerun()
    
    # 대화 저장
    if st.button("💾 대화 저장", use_container_width=True, key="save_chat"):
        st.success("✅ 대화가 저장되었습니다!")
    
    st.markdown("---")
    
    # 법제처 조회 기능
    st.markdown("## 🔍 법제처 조회")
    
    # 검색어 입력
    search_keyword = st.text_input(
        "검색어 입력",
        placeholder="예: 민법, 형법, 상법...",
        key="sidebar_search",
        help="검색하고 싶은 법령명을 입력하세요"
    )
    
    # 검색 결과 수 선택
    search_rows = st.selectbox(
        "검색 결과 수",
        options=[5, 10, 15, 20],
        index=0,
        key="sidebar_rows"
    )
    
    # 검색 버튼
    if st.button("🔍 검색하기", use_container_width=True, key="sidebar_search_btn"):
        if search_keyword.strip():
            with st.spinner("법령 검색 중..."):
                search_results = law_search(search_keyword.strip(), search_rows)
                if search_results:
                    st.success(f"✅ {len(search_results)}개의 법령을 찾았습니다!")
                    
                    # 검색 결과를 세션에 저장하여 메인 채팅에 표시
                    st.session_state.last_search_results = search_results
                    st.session_state.last_search_query = search_keyword.strip()
                    
                    # 검색 결과를 채팅에 추가
                    search_summary = f"🔍 **'{search_keyword.strip()}' 검색 결과**\n\n" + "\n".join(search_results)
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": search_summary, 
                        "ts": time.time()
                    })
                    save_message(st.session_state.thread_id, {
                        "role": "assistant", 
                        "content": search_summary, 
                        "ts": time.time()
                    })
                    st.rerun()
                else:
                    st.warning("검색 결과가 없습니다.")
        else:
            st.warning("검색어를 입력해주세요.")
    
    # 최근 검색 결과 표시
    if hasattr(st.session_state, 'last_search_results') and st.session_state.last_search_results:
        st.markdown("### 📋 최근 검색 결과")
        st.info(f"**'{st.session_state.last_search_query}'** 검색 결과")
        for i, result in enumerate(st.session_state.last_search_results[:5]):  # 최근 5개만 표시
            st.markdown(f"• {result}")
        
        # 검색 결과 지우기
        if st.button("🗑️ 검색 결과 지우기", use_container_width=True, key="clear_search"):
            if 'last_search_results' in st.session_state:
                del st.session_state.last_search_results
            if 'last_search_query' in st.session_state:
                del st.session_state.last_search_query
            st.rerun()
    
    st.markdown("---")
    
    # 대화 히스토리
    st.markdown("### 📚 대화 히스토리")
    
    if st.session_state.messages:
        # 최근 10개 메시지만 표시
        recent_messages = st.session_state.messages[-10:]
        for i, m in enumerate(recent_messages):
            role = "👤 사용자" if m.get("role") == "user" else "⚖️ AI"
            preview = (m.get("content", "") or "").replace("\n", " ")[:50]
            
            # 클릭 가능한 히스토리 아이템
            if st.button(
                f"{role}: {preview}...",
                key=f"history_{i}",
                help="클릭하여 이 대화로 이동",
                use_container_width=True
            ):
                # 해당 메시지로 스크롤 (실제로는 새로고침)
                st.rerun()
    else:
        st.info("아직 대화 기록이 없습니다.")
    
    st.markdown("---")
    
    # 설정 정보
    st.markdown("### ⚙️ 설정 정보")
    if client:
        st.success("✅ Azure OpenAI 연결됨")
    else:
        st.error("❌ Azure OpenAI 연결 안됨")
    
    if DATA_PORTAL_SERVICE_KEY:
        st.success("✅ 공공데이터포털 API 키 설정됨")
    else:
        st.warning("⚠️ 공공데이터포털 API 키 필요")

# =========================
# Main Chat Container
# =========================
st.markdown('<div class="chat-container">', unsafe_allow_html=True)

# 메시지 히스토리 렌더링
for m in st.session_state.messages:
    role = m.get("role", "assistant")
    is_user = role == "user"
    
    st.markdown(
        f"""
        <div class="chat-message {'user' if is_user else 'assistant'}">
            <div class="chat-avatar {'user' if is_user else 'assistant'}">
                {'👤' if is_user else '⚖️'}
            </div>
            <div class="chat-content">
                {m.get("content", "")}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# 환경 경고 배너
if not client:
    st.info("💡 Azure OpenAI 설정이 없으면 기본 안내만 표시됩니다. (Secrets에 api_key/endpoint/deployment/api_version 확인)")

st.markdown('</div>', unsafe_allow_html=True)

# =========================
# Enhanced Chat Input with Fixed Bottom
# =========================
st.markdown('<div class="fixed-chat-input">', unsafe_allow_html=True)

with st.form("chat_form", clear_on_submit=True):
    col1, col2 = st.columns([4, 1])
    
    with col1:
        user_text = st.text_area(
            label="",
            key="draft_input",
            placeholder="법령에 대한 질문을 입력하세요... (Shift+Enter: 줄바꿈, Enter: 전송)",
            height=50,
            max_chars=2000,
        )
    
    with col2:
        submitted = st.form_submit_button("🚀 보내기", use_container_width=True, use_container_height=True)

st.markdown('</div>', unsafe_allow_html=True)

# =========================
# Message Processing
# =========================
if submitted:
    user_q = (user_text or "").strip()
    if user_q:
        ts = time.time()

        # 사용자 메시지 추가
        st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
        save_message(st.session_state.thread_id, {"role": "user", "content": user_q, "ts": ts})

        # 컨텍스트 초기화
        ctx: str = ""
        assistant_full: str = ""

        # 법령 검색
        with st.spinner("🔍 법령 검색 중..."):
            hits = law_search(user_q)
            ctx = law_context_str(hits)

        # 모델용 히스토리 준비
        history_for_model = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[-12:]
        ]
        history_for_model.append(
            {
                "role": "user",
                "content": f"""사용자 질문: {user_q}

관련 법령 정보(요약):
{ctx}

요청: 위 법령 검색 결과를 참고해 질문에 답하세요.
필요하면 관련 조문도 함께 제시하세요.
한국어로 쉽게 설명하세요.""",
            }
        )

        # AI 답변 생성
        with st.spinner("🤖 AI 답변 생성 중..."):
            if client is None:
                assistant_full = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + ctx
            else:
                try:
                    stream = client.chat.completions.create(
                        model=AZURE_OPENAI_DEPLOYMENT,
                        messages=history_for_model,
                        temperature=0.3,
                        top_p=1.0,
                        stream=True,
                        timeout=60,
                    )
                    buf = []
                    for ch in stream:
                        piece = ""
                        try:
                            piece = ch.choices[0].delta.get("content", "")
                        except Exception:
                            pass
                        if piece:
                            buf.append(piece)
                            assistant_full = "".join(buf)
                    assistant_full = "".join(buf)
                except Exception as e:
                    error_msg = f"답변 생성 중 오류가 발생했습니다: {str(e)}"
                    if "timeout" in str(e).lower():
                        error_msg = "⏰ 응답 시간이 초과되었습니다. 다시 시도해주세요."
                    elif "rate limit" in str(e).lower():
                        error_msg = "🚫 API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
                    elif "authentication" in str(e).lower():
                        error_msg = "🔑 인증 오류가 발생했습니다. API 키를 확인해주세요."
                    
                    assistant_full = f"{error_msg}\n\n{ctx}"
                    st.error(f"상세 오류: {str(e)}")

        # AI 답변 저장
        st.session_state.messages.append({"role": "assistant", "content": assistant_full, "ts": time.time()})
        save_message(st.session_state.thread_id, {"role": "assistant", "content": assistant_full, "ts": time.time()})
        
        # 페이지 새로고침
        st.rerun()

# =========================
# Utility Functions
# =========================
def law_search(keyword: str, rows: int = 5) -> List[str]:
    """국가법령 검색 - 공공데이터포털 사용"""
    rows = max(1, min(int(rows or 5), 20))

    def _warn(msg: str, sample: str = ""):
        from textwrap import shorten
        st.warning(msg + (f" : {shorten(sample.strip(), width=160)}" if sample else ""))

    def _is_html(t: str) -> bool:
        t = (t or "").lstrip().lower()
        return t.startswith("<!doctype html") or t.startswith("<html")

    def _parse_xml(xml_text: str) -> List[str]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as pe:
            _warn(f"XML 파싱 오류: {pe}")
            return []
        
        rc = (root.findtext('.//resultCode') or '').strip()
        if rc and rc != '00':
            msg = (root.findtext('.//resultMsg') or '').strip()
            code_map = {'01':'잘못된 요청 파라미터','02':'인증키 오류','03':'필수 파라미터 누락','09':'일시적 시스템 오류','99':'정의되지 않은 오류'}
            _warn(f"API 오류(resultCode={rc}): {code_map.get(rc, msg or '오류')}")
            return []
        
        hits = []
        for node in root.findall('.//law'):
            title = (node.findtext('법령명한글') or node.findtext('법령명') or '').strip()
            date  = (node.findtext('시행일자') or node.findtext('공포일자') or '').strip()
            if title:
                hits.append(f"- {title} (시행일자: {date})")
        return hits[:rows]

    # 공공데이터포털 API 호출
    if not DATA_PORTAL_SERVICE_KEY:
        st.warning("⚠️ 공공데이터포털 ServiceKey가 설정되지 않았습니다.")
        return []
    
    # 여러 API 엔드포인트 시도
    api_endpoints = [
        {
            'url': 'https://apis.data.go.kr/1170000/law/lawSearchList.do',
            'params': {
                'serviceKey': DATA_PORTAL_SERVICE_KEY,
                'target': 'law',
                'query': keyword or '*',
                'numOfRows': rows,
                'pageNo': 1,
            }
        },
        {
            'url': 'https://apis.data.go.kr/1170000/law/lawSearch.do',
            'params': {
                'serviceKey': DATA_PORTAL_SERVICE_KEY,
                'target': 'law',
                'query': keyword or '*',
                'numOfRows': rows,
                'pageNo': 1,
            }
        },
        {
            'url': 'https://apis.data.go.kr/1170000/law/lawList.do',
            'params': {
                'serviceKey': DATA_PORTAL_SERVICE_KEY,
                'target': 'law',
                'query': keyword or '*',
                'numOfRows': rows,
                'pageNo': 1,
            }
        }
    ]
    
    for endpoint in api_endpoints:
        try:
            # HTTP 연결 시도
            if endpoint['url'].startswith('https://'):
                http_url = endpoint['url'].replace('https://', 'http://')
            else:
                http_url = endpoint['url']
            
            # 세션 설정
            session = requests.Session()
            
            # User-Agent 추가로 호환성 향상
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/xml, text/xml, */*',
                'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                'Connection': 'keep-alive'
            }
            
            # HTTP로 시도
            res = session.get(http_url, params=endpoint['params'], headers=headers, timeout=30)
            ctype = (res.headers.get('Content-Type') or '').lower()
            txt = res.text or ''
            
            if res.status_code == 200 and txt.strip():
                if 'xml' in ctype or txt.strip().startswith('<'):
                    if _is_html(txt):
                        continue  # HTML 응답이면 다음 API 시도
                    else:
                        hits = _parse_xml(txt)
                        if hits:
                            return hits
                else:
                    # XML이 아닌 응답이지만 내용이 있으면 텍스트 기반으로 처리
                    if '법' in txt or '규정' in txt or '조례' in txt:
                        lines = txt.split('\n')
                        hits = []
                        for line in lines:
                            line = line.strip()
                            if line and len(line) > 5 and ('법' in line or '규정' in line or '조례' in line):
                                hits.append(f"- {line}")
                        if hits:
                            return hits[:rows]
            
        except Exception as e:
            continue  # 오류 발생 시 다음 API 시도
    
    # 모든 API 시도 실패 시 사용자에게 안내
    st.error("""
    ❌ 공공데이터포털 API 연결에 실패했습니다. 다음을 확인해주세요:
    
    1. **ServiceKey 확인**: [공공데이터포털](https://www.data.go.kr/iim/api/selectAPIAcountView.do)에서 발급받은 키가 정확한지 확인
    2. **키 타입**: Decoding된 값을 사용해야 합니다
    3. **일일 호출 한도**: 무료 계정의 경우 일일 1,000건 제한이 있을 수 있습니다
    4. **네트워크 환경**: 회사/기관 네트워크에서 외부 API 접근이 차단될 수 있습니다
    
    임시로 기본 법령 정보를 제공합니다.
    """)
    
    # 기본 법령 정보 제공
    default_laws = [
        "- 민법 (시행일자: 1960-01-01)",
        "- 형법 (시행일자: 1953-09-18)",
        "- 상법 (시행일자: 1962-01-20)",
        "- 민사소송법 (시행일자: 1960-04-01)",
        "- 형사소송법 (시행일자: 1954-09-23)"
    ]
    return default_laws[:rows]

def law_context_str(hits: List[str]) -> str:
    """법령 검색 결과를 문자열로 변환"""
    return "\n".join(hits) if hits else "관련 검색 결과가 없습니다."

def get_client() -> Optional[AzureOpenAI]:
    """Azure OpenAI 클라이언트 생성 및 검증"""
    if not all([AZURE_OPENAI_API_BASE, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT]):
        missing = []
        if not AZURE_OPENAI_API_BASE: missing.append("endpoint")
        if not AZURE_OPENAI_API_KEY: missing.append("api_key")
        if not AZURE_OPENAI_DEPLOYMENT: missing.append("deployment")
        st.error(f"❌ Azure OpenAI 설정 누락: {', '.join(missing)}")
        return None
    
    try:
        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_API_BASE,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
        return client
    except Exception as e:
        st.error(f"❌ Azure OpenAI 연결 실패: {str(e)}")
        return None

# Azure OpenAI 클라이언트 초기화
client = get_client()