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

# ============ 초기 설정 & 스타일 ============
st.set_page_config(page_title="법제처 AI 챗봇", page_icon="⚖️", layout="wide")
st.markdown("""
<style>
  .header {text-align:center;padding:1.2rem;border-radius:12px;background:linear-gradient(135deg,#8b5cf6,#a78bfa);color:#fff;margin-bottom:1.2rem}
  .bubble {max-width:950px;margin:10px auto}
  .user-message {background:#2563eb;color:#fff;padding:1rem;border-radius:16px 16px 0 16px}
  .ai-message {background:#fff;color:#111;padding:1rem;border-radius:16px 16px 16px 0;box-shadow:0 2px 8px rgba(0,0,0,.08)}
  .typing-indicator {display:inline-block;width:18px;height:18px;border:3px solid #eee;border-top:3px solid #8b5cf6;border-radius:50%;animation:spin 1s linear infinite}
  @keyframes spin {0%{transform:rotate(0)}100%{transform:rotate(360deg)}}
  .copy-wrap {background:#fff;color:#333;padding:12px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
  .copy-head {display:flex;justify-content:space-between;align-items:center;gap:12px}
  .copy-btn {display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid #ddd;border-radius:8px;background:#f8f9fa;cursor:pointer;font-size:12px}
  .copy-body {margin-top:6px;line-height:1.6;white-space:pre-wrap}
</style>
""", unsafe_allow_html=True)

st.markdown(
  '<div class="header"><h2>⚖️ 법제처 인공지능 법률 상담 플랫폼</h2><div>법제처 공식 데이터와 인공지능 기술을 결합한 전문 법률 정보 제공 서비스</div></div>',
  unsafe_allow_html=True,
)

# ============ 복사 버튼 컴포넌트 ============
def render_ai_with_copy(message: str, key: str):
    safe_for_js = json.dumps(message)
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
              await navigator.clipboard.writeText({safe_for_js});
              const old = btn.textContent;
              btn.textContent = "복사됨!";
              setTimeout(()=>btn.textContent = old, 1200);
            }} catch (e) {{ alert("복사 실패: " + e); }}
          }});
        }}
      }})();
    </script>
    """
    components.html(html, height=200)

# ============ Secrets ============
def load_secrets():
    law_key = None; azure = None
    try: law_key = st.secrets["LAW_API_KEY"]
    except Exception: st.error("`LAW_API_KEY`가 없습니다. Streamlit Secrets를 확인하세요.")
    try:
        azure = st.secrets["azure_openai"]
        _ = azure["api_key"]; _ = azure["endpoint"]; _ = azure["deployment"]; _ = azure["api_version"]
    except Exception:
        st.error("[azure_openai] 섹션(api_key, endpoint, deployment, api_version) 누락")
        azure = None
    return law_key, azure

LAW_API_KEY, AZURE = load_secrets()

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

# ============ 세션 상태 ============
# messages: [{role: "user"|"assistant", content: str, ts: str, law: list|None}]
if "messages" not in st.session_state: st.session_state.messages = []
if "is_processing" not in st.session_state: st.session_state.is_processing = False

# ============ 법제처 API ============
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

def build_model_messages(user_q: str, law_ctx: str, max_turns: int = 10):
    sys = {"role": "system", "content": "당신은 대한민국의 법령 정보를 전문적으로 안내하는 AI 어시스턴트입니다."}
    msgs = [sys]
    # 최근 turn부터 최대 max_turns * 2개의 메시지(질문/답변) 포함
    history = st.session_state.messages[-max_turns*2:]
    for m in history:
        msgs.append({"role": m["role"], "content": m["content"]})
    current = f"""사용자 질문: {user_q}

관련 법령 정보(요약):
{law_ctx}

요청 형식:
법률자문서

제목: 납품 지연에 따른 계약 해제 가능 여부에 관한 법률 검토
수신: ○○ 주식회사 대표이사 귀하
작성: 법제처 인공지능 법률 상담사
작성일: 오늘일자

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
한국어로 이해하기 쉽게 설명."""
    msgs.append({"role": "user", "content": current})
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
            if not hasattr(chunk, "choices") or not chunk.choices: continue
            ch = chunk.choices[0]
            if getattr(ch, "finish_reason", None): break
            delta = getattr(ch, "delta", None)
            text = getattr(delta, "content", None) if delta else None
            if text: yield text
        except Exception:
            continue

# ============ 사이드바 ============
with st.sidebar:
    st.markdown("### ⚙️ 옵션")
    num_rows = st.number_input("참고 검색 개수(법제처)", min_value=1, max_value=10, value=5, step=1)
    include_search = st.checkbox("법제처 검색 맥락 포함", value=True)
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🆕 새로운 대화", use_container_width=True):
            st.session_state.messages.clear()
            st.success("새 대화를 시작합니다.")
            st.experimental_rerun()
    with col2:
        if st.button("🗑️ 기록 초기화", use_container_width=True):
            st.session_state.messages.clear()
            st.experimental_rerun()
    st.divider()
    st.metric("총 메시지 수", len(st.session_state.messages))

# ============ 대화 스레드 렌더 ============
for i, m in enumerate(st.session_state.messages):
    if m["role"] == "user":
        st.markdown(f'<div class="bubble user-message"><strong>사용자:</strong><br>{m["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="bubble">', unsafe_allow_html=True)
        render_ai_with_copy(m["content"], key=f"past-{i}")
        st.markdown('</div>', unsafe_allow_html=True)
        if m.get("law"):
            with st.expander("📋 이 턴에서 참고한 법령 요약"):
                for j, law in enumerate(m["law"], 1):
                    st.write(f"**{j}. {law['법령명']}** ({law['법령구분명']})  | 시행 {law['시행일자']}  | 공포 {law['공포일자']}")
                    if law["법령상세링크"]:
                        st.write(f"- 링크: {law['법령상세링크']}")

st.divider()

# ============ 입력 & 처리 ============
user_q = st.text_input("법령에 대한 질문을 입력하세요", placeholder="예) 정당방위 인정받으려면 어떻게 하나요?")
send = st.button("전송", type="primary", use_container_width=True)

if send and user_q.strip():
    st.session_state.is_processing = True
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 0) 사용자 메시지를 즉시 스레드에 추가
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})

    # 1) 법제처 검색(옵션)
    law_data, used_endpoint, err = ([], None, None)
    if include_search:
        with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
            law_data, used_endpoint, err = search_law_data(user_q, num_rows=num_rows)
        if used_endpoint: st.caption(f"법제처 API endpoint: `{used_endpoint}`")
        if err: st.warning(err)

    # 2) 모델 호출
    law_ctx = format_law_context(law_data)
    model_messages = build_model_messages(user_q, law_ctx, max_turns=10)
    ai_placeholder = st.empty()

    full_text, buffer = "", ""

    with st.spinner("🤖 AI가 답변을 생성하는 중..."):
        if client is None:
            full_text = "설정된 Azure OpenAI가 없어 기본 답변을 제공합니다.\n\n" + law_ctx
            st.markdown(f'<div class="bubble ai-message"><strong>AI 어시스턴트:</strong><br>{full_text}</div>', unsafe_allow_html=True)
        else:
            # 타이핑 시작
            ai_placeholder.markdown(
                '<div class="bubble ai-message"><strong>AI 어시스턴트:</strong><br><div class="typing-indicator"></div> 생성 중...</div>',
                unsafe_allow_html=True,
            )
            try:
                for piece in stream_chat_completion(model_messages, temperature=0.7, max_tokens=1000):
                    buffer += piece
                    if len(buffer) >= 80:
                        full_text += buffer; buffer = ""
                        ai_placeholder.markdown(
                            f'<div class="bubble ai-message"><strong>AI 어시스턴트:</strong><br>{full_text}</div>',
                            unsafe_allow_html=True,
                        )
                        time.sleep(0.02)
                if buffer:
                    full_text += buffer
                    ai_placeholder.markdown(
                        f'<div class="bubble ai-message"><strong>AI 어시스턴트:</strong><br>{full_text}</div>',
                        unsafe_allow_html=True,
                    )
            except Exception:
                # 비-스트리밍 폴백
                try:
                    resp = client.chat.completions.create(
                        model=AZURE["deployment"], messages=model_messages,
                        max_tokens=1000, temperature=0.7, stream=False
                    )
                    full_text = resp.choices[0].message.content
                    ai_placeholder.markdown(
                        f'<div class="bubble ai-message"><strong>AI 어시스턴트:</strong><br>{full_text}</div>',
                        unsafe_allow_html=True,
                    )
                except Exception as e2:
                    full_text = f"답변 생성 중 오류가 발생했습니다: {e2}\n\n{law_ctx}"
                    ai_placeholder.markdown(
                        f'<div class="bubble ai-message"><strong>AI 어시스턴트:</strong><br>{full_text}</div>',
                        unsafe_allow_html=True,
                    )

    # 3) 스트리밍 종료 후: 복사 가능 카드로 한 번 더 추가 렌더
    st.markdown('<div class="bubble">', unsafe_allow_html=True)
    render_ai_with_copy(full_text, key=f"now-{ts}")
    st.markdown('</div>', unsafe_allow_html=True)

    # 4) 스레드에 어시스턴트 메시지 저장(법령 요약 포함)
    st.session_state.messages.append({
        "role": "assistant", "content": full_text, "ts": ts, "law": law_data if include_search else None
    })

    st.session_state.is_processing = False
    st.success("✅ 답변이 완성되었습니다!")
