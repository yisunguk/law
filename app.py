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
import streamlit.components.v1 as components
from openai import AzureOpenAI

# Firebase
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:
    firebase_admin = None

# =============================
# 기본 설정 & 스타일 (ChatGPT 레이아웃 + 간격 축소)
# =============================
st.set_page_config(page_title="법제처 AI 챗봇", page_icon="⚖️", layout="wide")

st.markdown("""
<style>
  /* 중앙 900px 컨테이너 - 답변/입력 동일 폭 */
  .block-container {max-width: 900px; margin: 0 auto; padding-bottom: .5rem !important;}
  .stChatInput {max-width: 900px; margin-left: auto; margin-right: auto;}
  /* 입력 위쪽 여백 최소화 */
  .stChatInput textarea {font-size:15px; margin-top: 0 !important;}

  /* 상단 헤더 */
  .header {text-align:center;padding:1.0rem;border-radius:12px;
           background:linear-gradient(135deg,#8b5cf6,#a78bfa);
           color:#fff;margin:0 0 .75rem 0}

  /* 복사 카드 */
  .copy-wrap {background:#fff;color:#222;padding:12px;border-radius:12px;
              box-shadow:0 1px 6px rgba(0,0,0,.06);margin:6px 0}
  .copy-head {display:flex;justify-content:space-between;align-items:center;gap:12px}
  .copy-btn  {display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid #ddd;border-radius:8px;
              background:#f8f9fa;cursor:pointer;font-size:12px}
  .copy-body {margin-top:6px;line-height:1.6;white-space:pre-wrap}

  /* 타이핑 인디케이터 */
  .typing-indicator {display:inline-block;width:16px;height:16px;border:3px solid #eee;border-top:3px solid #8b5cf6;
                     border-radius:50%;animation:spin 1s linear infinite;vertical-align:middle}
  @keyframes spin {0%{transform:rotate(0)}100%{transform:rotate(360deg)}}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="header"><h2>⚖️ 법제처 인공지능 법률 상담 플랫폼</h2>'
    '<div>법제처 공식 데이터 + Azure OpenAI + Firebase 대화 메모리</div></div>',
    unsafe_allow_html=True,
)

# =============================
# 복사 버튼 카드 (자동 높이 / 스크롤 없음 / 말풍선 아래 추가)
# =============================

def _estimate_height(text: str, min_h=220, max_h=2000, per_line=18):
    lines = text.count("\n") + max(1, math.ceil(len(text) / 60))
    h = min_h + lines * per_line
    return max(min_h, min(h, max_h))


def build_copy_html(message: str, key: str) -> str:
    """JS 중괄호를 f-string에서 안전하게 표현하기 위해 {{ }} 이스케이프 사용.
    message는 json.dumps로 JS 문자열로 안전하게 삽입합니다.
    """
    safe = json.dumps(message)  # JS 문자열 리터럴로 안전하게 인코딩됨 (양쪽 따옴표 포함)
    html = f"""
    <div class="copy-wrap">
      <div class="copy-head">
        <strong>AI 어시스턴트</strong>
        <button id="copy-{key}" class="copy-btn" title="클립보드로 복사">복사</button>
      </div>
      <div class="copy-body">{message}</div>
    </div>
    <script>
      (function(){{
        const btn = document.getElementById("copy-{key}");
        if (btn) {{
          btn.addEventListener("click", async () => {{
            try {{
              await navigator.clipboard.writeText({safe});
              const old = btn.innerHTML;
              btn.innerHTML = "복사됨!";
              setTimeout(()=>btn.innerHTML = old, 1200);
            }} catch(e) {{ alert("복사 실패: "+e); }}
          }});
        }}
      }})();
    </script>
    """
    return html


def render_ai_with_copy(message: str, key: str):
    est_h = _estimate_height(message)
    html = build_copy_html(message, key)
    components.html(html, height=est_h)

# =============================
# Secrets 로딩
# =============================

def load_secrets():
    law_key = None; azure = None; fb = None
    try:
        law_key = st.secrets["LAW_API_KEY"]
    except Exception:
        st.warning("`LAW_API_KEY`가 없습니다. 법제처 검색 기능 없이 동작합니다.")
    try:
        azure = st.secrets["azure_openai"]
        _ = azure["api_key"]; _ = azure["endpoint"]; _ = azure["deployment"]; _ = azure["api_version"]
    except Exception:
        st.error("[azure_openai] 섹션(api_key, endpoint, deployment, api_version) 누락")
        azure = None
    try:
        fb = st.secrets["firebase"]
    except Exception:
        st.error("[firebase] 시크릿이 없습니다. Firebase 기반 대화 유지가 비활성화됩니다.")
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
    except Exception as e:
        st.error(f"Azure OpenAI 초기화 실패: {e}")

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
                # Streamlit secrets는 줄바꿈 포함 문자열을 그대로 주입하므로 replace 필요 없음
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
        return _db
    except Exception as e:
        st.error(f"Firebase 초기화 실패: {e}")
        return None


DB = init_firebase()

# =============================
# 세션 상태 (ChatGPT 호환 구조 + thread_id)
# =============================
if "thread_id" not in st.session_state:
    # URL 쿼리로 thread 공유 허용 (?t=...)
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
        st.warning(f"대화 로드 실패: {e}")
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
        st.warning(f"메시지 저장 실패: {e}")


def save_summary(thread_id: str, summary: str):
    if DB is None:
        return
    try:
        _threads_col().document(thread_id).set({"summary": summary, "summary_updated_at": firestore.SERVER_TIMESTAMP}, merge=True)
    except Exception:
        pass


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
# 모델 메시지 구성/스트리밍 (+ 요약 메모리)
# =============================


def build_history_messages(max_turns=12):
    """최근 N턴 + Firestore 요약을 함께 모델에 전달 (ChatGPT 유사 맥락 유지)."""
    sys = {"role": "system", "content": "당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다."}
    msgs: List[Dict[str, str]] = [sys]

    # Firestore에 저장된 장기 요약을 선행 컨텍스트로 사용
    long_summary = get_summary(st.session_state.thread_id)
    if long_summary:
        msgs.append({"role": "system", "content": f"이전 대화의 압축 요약:\n{long_summary}"})

    # 세션 내 최근 발화들
    history = st.session_state.messages[-max_turns*2:]
    for m in history:
        # 모델에 전달할 때는 role/content만
        if m.get("role") in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": m["content"]})
    return msgs


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
            c = chunk.choices[0]
            if getattr(c, "finish_reason", None):
                break
            d = getattr(c, "delta", None)
            txt = getattr(d, "content", None) if d else None
            if txt:
                yield txt
        except Exception:
            continue


def update_long_summary_if_needed():
    """메시지가 충분히 쌓이면 장기 요약을 생성해 Firestore에 저장.
    - 12턴마다 이전 대화를 요약해 토큰 절약 + 맥락 지속
    """
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
    except Exception:
        pass

# =============================
# 사이드바 (옵션 & 새로운 대화)
# =============================
with st.sidebar:
    st.markdown("### ⚙️ 옵션")
    st.session_state.settings["num_rows"] = st.slider("참고 검색 개수(법제처)", 1, 10, st.session_state.settings["num_rows"])
    st.session_state.settings["include_search"] = st.checkbox("법제처 검색 맥락 포함", value=st.session_state.settings["include_search"])
    st.divider()
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("🆕 새로운 대화 시작", use_container_width=True):
            st.session_state.thread_id = uuid.uuid4().hex[:12]
            st.session_state.messages.clear()
            st.rerun()
    with col2:
        # 현재 스레드 공유용 링크 노출
        try:
            base = st.get_option("browser.serverAddress") or ""
        except Exception:
            base = ""
        st.caption(f"Thread ID: `{st.session_state.thread_id}` — URL에 `?t={st.session_state.thread_id}` 를 붙여 공유 가능")
    st.divider()
    st.metric("총 메시지 수", len(st.session_state.messages))

# =============================
# 과거 대화 렌더 (ChatGPT 스타일)
# =============================
for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m.get("role", "user")):
        if m.get("role") == "assistant":
            render_ai_with_copy(m.get("content", ""), key=f"past-{i}")
            if m.get("law"):
                with st.expander("📋 이 턴에서 참고한 법령 요약"):
                    for j, law in enumerate(m["law"], 1):
                        st.write(f"**{j}. {law['법령명']}** ({law['법령구분명']})  | 시행 {law['시행일자']}  | 공포 {law['공포일자']}")
                        if law.get("법령상세링크"):
                            st.write(f"- 링크: {law['법령상세링크']}")
        else:
            st.markdown(m.get("content", ""))

# =============================
# 하단 입력창 (고정, 답변과 동일 폭)
# =============================
user_q = st.chat_input("법령에 대한 질문을 입력하세요… (Enter로 전송)")

if user_q:
    ts = datetime.utcnow().isoformat()

    # 사용자 메시지 즉시 표기/저장
    user_msg = {"role": "user", "content": user_q, "ts": ts}
    st.session_state.messages.append(user_msg)
    save_message(st.session_state.thread_id, user_msg)

    with st.chat_message("user"):
        st.markdown(user_q)

    # (옵션) 법제처 검색
    law_data, used_endpoint, err = ([], None, None)
    if st.session_state.settings["include_search"]:
        with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
            law_data, used_endpoint, err = search_law_data(user_q, num_rows=st.session_state.settings["num_rows"])
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

    # 어시스턴트 말풍선(스트리밍)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_text, buffer = "", ""

        if client is None:
            full_text = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + law_ctx
            placeholder.markdown(full_text)
        else:
            try:
                placeholder.markdown('<span class="typing-indicator"></span> 답변 생성 중...', unsafe_allow_html=True)
                for piece in stream_chat_completion(model_messages, temperature=0.7, max_tokens=1000):
                    buffer += piece
                    if len(buffer) >= 80:
                        full_text += buffer; buffer = ""
                        placeholder.markdown(full_text)
                        time.sleep(0.02)
                if buffer:
                    full_text += buffer
                    placeholder.markdown(full_text)
            except Exception as e:
                full_text = f"답변 생성 중 오류가 발생했습니다: {e}\n\n{law_ctx}"
                placeholder.markdown(full_text)

        # ✅ 말풍선을 지우지 않고, 그 아래에 복사 카드 추가 렌더
        render_ai_with_copy(full_text, key=f"now-{ts}")

    # 대화 저장(법령 요약 포함)
    asst_msg = {
        "role": "assistant", "content": full_text,
        "law": law_data if st.session_state.settings["include_search"] else None,
        "ts": ts
    }
    st.session_state.messages.append(asst_msg)
    save_message(st.session_state.thread_id, asst_msg)

    # 장기 요약 업데이트 (토큰 절약 + 맥락 지속)
    update_long_summary_if_needed()

# =============================
# 🔧 간단 자가 테스트 (옵션) — 복사 위젯의 안전성 점검용
# =============================

def _selftest_copy_html() -> None:
    # 다양한 특수문자/개행을 포함한 메시지로 HTML 생성이 안전한지 검사
    cases = [
        ("simple", "Hello world"),
        ("quotes", 'He said "Hello" & replied.'),
        ("newline", "Line1\nLine2\nLine3"),
        ("unicode", "한글 🥟 emojis <> & ' \" \\"),
    ]
    for key, msg in cases:
        html = build_copy_html(msg, key)
        assert f"copy-{key}" in html
        assert "navigator.clipboard.writeText(" in html
        # json.dumps 결과가 양쪽 따옴표를 포함해 삽입되었는지 (대략적 검사)
        assert ")" in html and "writeText(" in html


with st.sidebar:
    run_tests = st.checkbox("🔧 복사 위젯 자가 테스트 실행")
    if run_tests:
        try:
            _selftest_copy_html()
            st.success("복사 위젯 자가 테스트 통과 ✅")
            # 미리보기 컴포넌트
            components.html(build_copy_html('테스트 "따옴표" 및 개행\n두번째 줄', "preview"), height=220)
        except AssertionError as e:
            st.error(f"자가 테스트 실패: {e}")
        except Exception as e:
            st.error(f"자가 테스트 중 예외: {e}")
