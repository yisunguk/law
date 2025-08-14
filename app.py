# app.py
import time
import json
import math
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI

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
    '<div>법제처 공식 데이터 + Azure OpenAI</div></div>',
    unsafe_allow_html=True,
)

# =============================
# 복사 버튼 카드 (자동 높이 / 스크롤 없음 / 말풍선 아래 추가)
# =============================
def _estimate_height(text: str, min_h=220, max_h=2000, per_line=18):
    # 대략 60자 = 한 줄로 가정하여 줄 수 추정
    lines = text.count("\n") + max(1, math.ceil(len(text) / 60))
    h = min_h + lines * per_line
    return max(min_h, min(h, max_h))

def render_ai_with_copy(message: str, key: str):
    safe = json.dumps(message)  # JS로 전달할 때 안전 처리
    est_h = _estimate_height(message)
    html = f"""
    <div class="copy-wrap">
      <div class="copy-head">
        <strong>AI 어시스턴트</strong>
        <button id="copy-{key}" class="copy-btn" title="클립보드로 복사">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
            <path d="M9 9h9v12H9z" stroke="#444"/>
            <path d="M6 3h9v3" stroke="#444"/>
            <path d="M6 6h3v3" stroke="#444"/>
          </svg>복사
        </button>
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
    components.html(html, height=est_h)

# =============================
# Secrets 로딩
# =============================
def load_secrets():
    law_key = None; azure = None
    try:
        law_key = st.secrets["LAW_API_KEY"]
    except Exception:
        st.error("`LAW_API_KEY`가 없습니다. Streamlit → App settings → Secrets에 추가하세요.")
    try:
        azure = st.secrets["azure_openai"]
        _ = azure["api_key"]; _ = azure["endpoint"]; _ = azure["deployment"]; _ = azure["api_version"]
    except Exception:
        st.error("[azure_openai] 섹션(api_key, endpoint, deployment, api_version) 누락")
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
# 세션 상태 (ChatGPT 호환 구조)
# =============================
# messages: [{role: "user"|"assistant", content: str, law: list|None, ts: str}]
if "messages" not in st.session_state:
    st.session_state.messages = []
if "settings" not in st.session_state:
    st.session_state.settings = {"num_rows": 5, "include_search": True}

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
# 모델 메시지 구성/스트리밍
# =============================
def build_history_messages(max_turns=10):
    """최근 N턴 히스토리를 모델에 전달 (ChatGPT와 동일 맥락 유지)."""
    sys = {"role": "system", "content": "당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다."}
    msgs = [sys]
    history = st.session_state.messages[-max_turns*2:]
    for m in history:
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

# =============================
# 사이드바 (옵션 & 새로운 대화)
# =============================
with st.sidebar:
    st.markdown("### ⚙️ 옵션")
    st.session_state.settings["num_rows"] = st.slider("참고 검색 개수(법제처)", 1, 10, st.session_state.settings["num_rows"])
    st.session_state.settings["include_search"] = st.checkbox("법제처 검색 맥락 포함", value=st.session_state.settings["include_search"])
    st.divider()
    if st.button("🆕 새로운 대화 시작", use_container_width=True):
        st.session_state.messages.clear()
        st.rerun()
    st.divider()
    st.metric("총 메시지 수", len(st.session_state.messages))

# =============================
# 과거 대화 렌더 (ChatGPT 스타일)
# =============================
for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        if m["role"] == "assistant":
            render_ai_with_copy(m["content"], key=f"past-{i}")
            if m.get("law"):
                with st.expander("📋 이 턴에서 참고한 법령 요약"):
                    for j, law in enumerate(m["law"], 1):
                        st.write(f"**{j}. {law['법령명']}** ({law['법령구분명']})  | 시행 {law['시행일자']}  | 공포 {law['공포일자']}")
                        if law.get("법령상세링크"):
                            st.write(f"- 링크: {law['법령상세링크']}")
        else:
            st.markdown(m["content"])

# =============================
# 하단 입력창 (고정, 답변과 동일 폭)
# =============================
user_q = st.chat_input("법령에 대한 질문을 입력하세요… (Enter로 전송)")

if user_q:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 사용자 메시지 즉시 표기/저장
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
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
    model_messages = build_history_messages(max_turns=10)
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
                # 타이핑 인디케이터
                placeholder.markdown('<span class="typing-indicator"></span> 답변 생성 중...', unsafe_allow_html=True)
                for piece in stream_chat_completion(model_messages, temperature=0.7, max_tokens=1000):
                    buffer += piece
                    if len(buffer) >= 80:  # 깜빡임 완화
                        full_text += buffer; buffer = ""
                        placeholder.markdown(full_text)
                        time.sleep(0.02)
                if buffer:
                    full_text += buffer
                    placeholder.markdown(full_text)
            except Exception as e:
                full_text = f"답변 생성 중 오류가 발생했습니다: {e}\n\n{law_ctx}"
                placeholder.markdown(full_text)

        # ✅ 말풍선을 지우지 않고, 그 아래에 복사 카드 '추가' 렌더 (사라짐 방지)
        render_ai_with_copy(full_text, key=f"now-{ts}")

    # 대화 저장(법령 요약 포함)
    st.session_state.messages.append({
        "role": "assistant", "content": full_text,
        "law": law_data if st.session_state.settings["include_search"] else None,
        "ts": ts
    })
