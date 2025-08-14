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

# Firebase
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:
    firebase_admin = None

# =============================
# 페이지 설정 & ChatGPT 스타일 UI
# =============================
st.set_page_config(
    page_title="법제처 AI 챗봇", 
    page_icon="⚖️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ChatGPT 스타일 CSS
st.markdown("""
<style>
    /* ChatGPT 스타일 컨테이너 */
    .main-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 0 1rem;
    }
    
    /* 헤더 스타일 */
    .chat-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 15px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    
    /* 채팅 메시지 스타일 */
    .chat-message {
        margin: 1.5rem 0;
        padding: 1rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .user-message {
        background: #007bff;
        color: white;
        margin-left: 20%;
        border-radius: 18px 18px 4px 18px;
    }
    
    .assistant-message {
        background: #f8f9fa;
        color: #333;
        margin-right: 20%;
        border-radius: 18px 18px 18px 4px;
        border: 1px solid #e9ecef;
    }
    
    /* 입력창 스타일 */
    .stChatInput {
        position: fixed;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 800px;
        max-width: 90vw;
        background: white;
        padding: 1rem;
        border-top: 1px solid #e9ecef;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
        z-index: 1000;
    }
    
    /* 타이핑 인디케이터 */
    .typing-indicator {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 3px solid #f3f3f3;
        border-top: 3px solid #667eea;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-right: 10px;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    /* 법령 정보 카드 */
    .law-card {
        background: #e3f2fd;
        border-left: 4px solid #2196f3;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 8px;
        font-size: 0.9rem;
    }
    
    /* 사이드바 스타일 */
    .sidebar-content {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    
    /* 메트릭 카드 */
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
        text-align: center;
    }
    
    /* 복사 버튼 */
    .copy-btn {
        background: #6c757d;
        color: white;
        border: none;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.8rem;
        cursor: pointer;
        float: right;
        margin-top: -0.5rem;
    }
    
    .copy-btn:hover {
        background: #5a6268;
    }
    
    /* 스크롤바 숨기기 */
    .stChatInput textarea {
        border-radius: 20px;
        border: 2px solid #e9ecef;
        padding: 0.75rem 1rem;
        font-size: 16px;
        resize: none;
    }
    
    /* 하단 여백 */
    .bottom-spacer {
        height: 100px;
    }
</style>
""", unsafe_allow_html=True)

# =============================
# 헤더
# =============================
st.markdown("""
<div class="chat-header">
    <h1>⚖️ 법제처 AI 챗봇</h1>
    <p>법제처 공식 데이터 + Azure OpenAI + Firebase 대화 메모리</p>
</div>
""", unsafe_allow_html=True)

# =============================
# Secrets 로딩
# =============================
def load_secrets():
    law_key = None
    azure = None
    fb = None
    
    try:
        law_key = st.secrets["LAW_API_KEY"]
    except Exception:
        st.warning("⚠️ `LAW_API_KEY`가 없습니다. 법제처 검색 기능 없이 동작합니다.")
    
    try:
        azure = st.secrets["azure_openai"]
        _ = azure["api_key"]
        _ = azure["endpoint"]
        _ = azure["deployment"]
        _ = azure["api_version"]
    except Exception:
        st.error("❌ [azure_openai] 섹션(api_key, endpoint, deployment, api_version) 누락")
        azure = None
    
    try:
        fb = st.secrets["firebase"]
        # Firebase 설정 유효성 검사
        required_keys = ["type", "project_id", "private_key_id", "private_key", 
                        "client_email", "client_id", "auth_uri", "token_uri", 
                        "auth_provider_x509_cert_url", "client_x509_cert_url"]
        missing_keys = [key for key in required_keys if key not in fb]
        if missing_keys:
            st.error(f"❌ Firebase 설정 누락: {missing_keys}")
            fb = None
        else:
            st.success("✅ Firebase 설정 확인됨")
    except Exception:
        st.error("❌ [firebase] 시크릿이 없습니다. Firebase 기반 대화 유지가 비활성화됩니다.")
        fb = None
    
    return law_key, azure, fb

LAW_API_KEY, AZURE, FIREBASE_SECRET = load_secrets()

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
        st.success("✅ Azure OpenAI 연결 성공")
    except Exception as e:
        st.error(f"❌ Azure OpenAI 초기화 실패: {e}")

# =============================
# Firebase 초기화 & Firestore 핸들러
# =============================
_db = None

def init_firebase():
    global _db
    if _db is not None:
        return _db
    
    if not FIREBASE_SECRET or firebase_admin is None:
        return None
    
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate({
                "type": FIREBASE_SECRET.get("type"),
                "project_id": FIREBASE_SECRET.get("project_id"),
                "private_key_id": FIREBASE_SECRET.get("private_key_id"),
                "private_key": FIREBASE_SECRET.get("private_key"),
                "client_email": FIREBASE_SECRET.get("client_email"),
                "client_id": FIREBASE_SECRET.get("client_id"),
                "auth_uri": FIREBASE_SECRET.get("auth_uri"),
                "token_uri": FIREBASE_SECRET.get("token_uri"),
                "auth_provider_x509_cert_url": FIREBASE_SECRET.get("auth_provider_x509_cert_url"),
                "client_x509_cert_url": FIREBASE_SECRET.get("client_x509_cert_url"),
                "universe_domain": FIREBASE_SECRET.get("universe_domain"),
            })
            firebase_admin.initialize_app(cred)
        
        _db = firestore.client()
        
        # 연결 테스트
        test_doc = _db.collection("_test").document("connection_test")
        test_doc.set({"test": True, "timestamp": firestore.SERVER_TIMESTAMP})
        test_doc.delete()
        
        st.success("✅ Firebase 연결 성공")
        return _db
        
    except Exception as e:
        st.error(f"❌ Firebase 초기화 실패: {e}")
        return None

DB = init_firebase()

# =============================
# 세션 상태
# =============================
if "thread_id" not in st.session_state:
    query_params = st.query_params
    t_from_url = query_params.get("t") if hasattr(query_params, "get") else None
    st.session_state.thread_id = t_from_url or uuid.uuid4().hex[:12]

if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []

if "settings" not in st.session_state:
    st.session_state.settings = {"num_rows": 5, "include_search": True}

# =============================
# Firestore I/O
# =============================
def _threads_col():
    if DB is None:
        return None
    return DB.collection("threads")

def load_thread(thread_id: str) -> List[Dict[str, Any]]:
    if DB is None:
        return []
    
    try:
        msgs_ref = _threads_col().document(thread_id).collection("messages").order_by("ts")
        docs = msgs_ref.stream()
        loaded = [d.to_dict() for d in docs]
        
        # 최신 스키마 정규화
        for m in loaded:
            if "role" not in m and m.get("type") in ("user", "assistant"):
                m["role"] = m.pop("type")
        
        return loaded
        
    except Exception as e:
        st.warning(f"⚠️ 대화 로드 실패: {e}")
        return []

def save_message(thread_id: str, msg: Dict[str, Any]):
    if DB is None:
        return
    
    try:
        _threads_col().document(thread_id).set({
            "updated_at": firestore.SERVER_TIMESTAMP,
            "created_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        
        _threads_col().document(thread_id).collection("messages").add({
            **msg,
            "ts": msg.get("ts") or datetime.utcnow().isoformat(),
        })
        
    except Exception as e:
        st.warning(f"⚠️ 메시지 저장 실패: {e}")

def save_summary(thread_id: str, summary: str):
    if DB is None:
        return
    
    try:
        _threads_col().document(thread_id).set({
            "summary": summary, 
            "summary_updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
    except Exception as e:
        st.warning(f"⚠️ 요약 저장 실패: {e}")

def get_summary(thread_id: str) -> str:
    if DB is None:
        return ""
    
    try:
        doc = _threads_col().document(thread_id).get()
        if doc.exists:
            return (doc.to_dict() or {}).get("summary", "")
        return ""
        
    except Exception:
        return ""

# 첫 로드 시 Firestore에서 메시지 복원
if DB and not st.session_state.messages:
    restored = load_thread(st.session_state.thread_id)
    if restored:
        st.session_state.messages = restored
        st.success(f"✅ 이전 대화 {len(restored)}개 메시지 복원됨")

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
            last_err = e
            continue
    
    return [], None, f"법제처 API 연결 실패: {last_err}"

def format_law_context(law_data):
    if not law_data:
        return "관련 법령 검색 결과가 없습니다."
    
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
# 모델 메시지 구성/스트리밍
# =============================
def build_history_messages(max_turns=12):
    """최근 N턴 + Firestore 요약을 함께 모델에 전달"""
    sys = {"role": "system", "content": "당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다."}
    msgs: List[Dict[str, str]] = [sys]
    
    # Firestore에 저장된 장기 요약을 선행 컨텍스트로 사용
    long_summary = get_summary(st.session_state.thread_id)
    if long_summary:
        msgs.append({"role": "system", "content": f"이전 대화의 압축 요약:\n{long_summary}"})
    
    # 세션 내 최근 발화들
    history = st.session_state.messages[-max_turns*2:]
    for m in history:
        if m.get("role") in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": m["content"]})
    
    return msgs

def stream_chat_completion(messages, temperature=0.7, max_tokens=1000):
    if not client:
        return None
    
    try:
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
                c = chunk.choices[0]
                if getattr(c, "finish_reason", None):
                    break
                d = getattr(c, "delta", None)
                txt = getattr(d, "content", None) if d else None
                if txt:
                    yield txt
            except Exception:
                continue
                
    except Exception as e:
        st.error(f"❌ OpenAI API 호출 실패: {e}")
        return None

def update_long_summary_if_needed():
    """메시지가 충분히 쌓이면 장기 요약을 생성해 Firestore에 저장"""
    if client is None or DB is None:
        return
    
    msgs = st.session_state.messages
    if len(msgs) < 24:  # user/assistant 합 24개(=12턴) 쌓이면 수행
        return
    
    try:
        # 최근 8개는 그대로 두고, 그 이전을 요약
        head = msgs[:-8]
        text_blob = []
        for m in head:
            role = m.get("role", "user")
            content = m.get("content", "")
            text_blob.append(f"[{role}] {content}")
        
        joined = "\n".join(text_blob)[-12000:]  # 안전하게 제한
        
        prompt = [
            {"role": "system", "content": "너는 대화 요약가다. 핵심 사실, 결론, 요구사항, 약속/액션아이템을 한국어로 간결히 정리하라."},
            {"role": "user", "content": f"다음 대화를 10~15문장으로 요약:\n{joined}"},
        ]
        
        res = client.chat.completions.create(
            model=AZURE["deployment"],
            messages=prompt,
            temperature=0.2,
            max_tokens=512,
        )
        
        summary = res.choices[0].message.content.strip()
        if summary:
            save_summary(st.session_state.thread_id, summary)
            
    except Exception as e:
        st.warning(f"⚠️ 요약 생성 실패: {e}")

# =============================
# 사이드바
# =============================
with st.sidebar:
    st.markdown("### ⚙️ 설정")
    
    with st.container():
        st.session_state.settings["num_rows"] = st.slider(
            "참고 검색 개수(법제처)", 
            1, 10, 
            st.session_state.settings["num_rows"]
        )
        st.session_state.settings["include_search"] = st.checkbox(
            "법제처 검색 맥락 포함", 
            value=st.session_state.settings["include_search"]
        )
    
    st.divider()
    
    # 새로운 대화 시작
    if st.button("🆕 새로운 대화 시작", use_container_width=True, type="primary"):
        st.session_state.thread_id = uuid.uuid4().hex[:12]
        st.session_state.messages.clear()
        st.rerun()
    
    # 현재 스레드 정보
    st.markdown("### 📋 현재 대화")
    st.caption(f"Thread ID: `{st.session_state.thread_id}`")
    st.caption("URL에 `?t={thread_id}` 를 붙여 공유 가능")
    
    st.divider()
    
    # 통계
    st.markdown("### 📊 통계")
    st.metric("총 메시지 수", len(st.session_state.messages))
    
    if st.session_state.messages:
        latest_msg = st.session_state.messages[-1]
        st.caption(f"마지막: {latest_msg.get('ts', 'N/A')[:19]}")

# =============================
# 메인 채팅 영역
# =============================
main_container = st.container()

with main_container:
    # 기존 대화 표시
    for i, m in enumerate(st.session_state.messages):
        if m.get("role") == "user":
            st.markdown(f"""
            <div class="chat-message user-message">
                <strong>사용자</strong><br>
                {m.get("content", "")}
            </div>
            """, unsafe_allow_html=True)
            
        elif m.get("role") == "assistant":
            st.markdown(f"""
            <div class="chat-message assistant-message">
                <strong>AI 어시스턴트</strong>
                <button class="copy-btn" onclick="navigator.clipboard.writeText('{m.get("content", "").replace("'", "\\'")}')">복사</button><br>
                {m.get("content", "")}
            </div>
            """, unsafe_allow_html=True)
            
            # 법령 정보 표시
            if m.get("law"):
                with st.expander("📋 이 턴에서 참고한 법령 요약", expanded=False):
                    for j, law in enumerate(m["law"], 1):
                        st.markdown(f"""
                        <div class="law-card">
                            <strong>{j}. {law['법령명']}</strong> ({law['법령구분명']})<br>
                            소관부처: {law['소관부처명']}<br>
                            시행: {law['시행일자']} | 공포: {law['공포일자']}<br>
                            {f'링크: {law["법령상세링크"]}' if law.get("법령상세링크") else '링크: 없음'}
                        </div>
                        """, unsafe_allow_html=True)

# =============================
# 하단 입력창
# =============================
user_q = st.chat_input("법령에 대한 질문을 입력하세요… (Enter로 전송)")

if user_q:
    ts = datetime.utcnow().isoformat()
    
    # 사용자 메시지 즉시 표기/저장
    user_msg = {"role": "user", "content": user_q, "ts": ts}
    st.session_state.messages.append(user_msg)
    save_message(st.session_state.thread_id, user_msg)
    
    # 사용자 메시지 표시
    st.markdown(f"""
    <div class="chat-message user-message">
        <strong>사용자</strong><br>
        {user_q}
    </div>
    """, unsafe_allow_html=True)
    
    # 법제처 검색 (옵션)
    law_data, used_endpoint, err = ([], None, None)
    if st.session_state.settings["include_search"]:
        with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
            law_data, used_endpoint, err = search_law_data(
                user_q, 
                num_rows=st.session_state.settings["num_rows"]
            )
        
        if used_endpoint:
            st.caption(f"법제처 API endpoint: `{used_endpoint}`")
        if err:
            st.warning(err)
    
    law_ctx = format_law_context(law_data)
    
    # 모델 히스토리 + 현재 질문 프롬프트
    model_messages = build_history_messages(max_turns=12)
    model_messages.append({
        "role": "user",
        "content": f"""사용자 질문: {user_q}

관련 법령 정보(요약):
{law_ctx}

아래 형식으로 답변하세요.
1) 질문에 대한 직접적인 답변
2) 관련 법령의 구체적인 내용
3) 참고/주의사항
한국어로 쉽게 설명하세요."""
    })
    
    # AI 어시스턴트 답변 (스트리밍)
    st.markdown(f"""
    <div class="chat-message assistant-message">
        <strong>AI 어시스턴트</strong>
        <button class="copy-btn" id="copy-{ts}">복사</button><br>
        <div id="content-{ts}">
            <span class="typing-indicator"></span> 답변 생성 중...
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 답변 생성
    full_text = ""
    if client is None:
        full_text = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + law_ctx
        st.markdown(f"""
        <script>
        document.getElementById('content-{ts}').innerHTML = `{full_text.replace("`", "\\`")}`;
        </script>
        """, unsafe_allow_html=True)
    else:
        try:
            for piece in stream_chat_completion(model_messages, temperature=0.7, max_tokens=1000):
                full_text += piece
                # 실시간 업데이트
                st.markdown(f"""
                <script>
                document.getElementById('content-{ts}').innerHTML = `{full_text.replace("`", "\\`")}`;
                </script>
                """, unsafe_allow_html=True)
                time.sleep(0.02)
                
        except Exception as e:
            full_text = f"답변 생성 중 오류가 발생했습니다: {e}\n\n{law_ctx}"
            st.markdown(f"""
            <script>
            document.getElementById('content-{ts}').innerHTML = `{full_text.replace("`", "\\`")}`;
            </script>
            """, unsafe_allow_html=True)
    
    # 복사 버튼 기능 활성화
    st.markdown(f"""
    <script>
    document.getElementById('copy-{ts}').addEventListener('click', async () => {{
        try {{
            await navigator.clipboard.writeText(`{full_text.replace("`", "\\`")}`);
            const btn = document.getElementById('copy-{ts}');
            btn.innerHTML = '복사됨!';
            setTimeout(() => btn.innerHTML = '복사', 1200);
        }} catch(e) {{
            alert('복사 실패: ' + e);
        }}
    }});
    </script>
    """, unsafe_allow_html=True)
    
    # 대화 저장(법령 요약 포함)
    asst_msg = {
        "role": "assistant", 
        "content": full_text,
        "law": law_data if st.session_state.settings["include_search"] else None,
        "ts": ts
    }
    st.session_state.messages.append(asst_msg)
    save_message(st.session_state.thread_id, asst_msg)
    
    # 장기 요약 업데이트
    update_long_summary_if_needed()
    
    # 페이지 새로고침으로 깔끔한 표시
    st.rerun()

# 하단 여백
st.markdown('<div class="bottom-spacer"></div>', unsafe_allow_html=True)
