# app.py — Chat-bubble + Copy, no sidebar, hardcoded options (final)
import time, json, html, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI

# =============================
# 페이지 & 전역 스타일
# =============================
st.set_page_config(
    page_title="법제처 AI 챗봇",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  /* 사이드바/토글 숨김 */
  [data-testid="stSidebar"]{display:none!important;}
  [data-testid="collapsedControl"]{display:none!important;}

  .block-container{max-width:900px;margin:0 auto;}
  .stChatInput{max-width:900px;margin-left:auto;margin-right:auto;}

  .header{ text-align:center;padding:1rem;border-radius:12px;
           background:linear-gradient(135deg,#8b5cf6,#a78bfa);color:#fff;margin:0 0 1rem 0 }

  /* ChatGPT 스타일 말풍선 */
  .chat-bubble{
    position:relative;
    background:var(--bubble-bg,#1f1f1f);
    color:var(--bubble-fg,#f5f5f5);
    border-radius:14px;
    padding:16px 48px 16px 16px;  /* 오른쪽 복사버튼 공간 */
    font-size:17px!important;
    line-height:1.8!important;
    white-space:pre-wrap;
    word-break:break-word;
    box-shadow:0 1px 8px rgba(0,0,0,.12);
  }
  [data-theme="light"] .chat-bubble{
    --bubble-bg:#ffffff; --bubble-fg:#222222;
    box-shadow:0 1px 8px rgba(0,0,0,.06);
  }
  /* 복사 버튼 (상단 오른쪽) */
  .copy-fab{
    position:absolute;top:10px;right:10px;
    display:inline-flex;align-items:center;gap:6px;
    padding:6px 10px;border:1px solid rgba(255,255,255,.15);
    border-radius:10px;background:rgba(0,0,0,.25);
    backdrop-filter:blur(4px);cursor:pointer;font-size:12px;
  }
  [data-theme="light"] .copy-fab{background:rgba(255,255,255,.9);border-color:#ddd;}
  .copy-fab svg{pointer-events:none}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="header"><h2>⚖️ 법제처 인공지능 법률 상담 플랫폼</h2>'
    '<div>법제처 공식 데이터를 AI가 분석해 답변을 제공합니다</div>'
    '<div>당신의 문제를 입력하면 법률 자문서를 출력해 줍니다. 당신의 문제를 입력해 보세요</div></div>',
    unsafe_allow_html=True,
)

# =============================
# 유틸: 말풍선 + 복사 버튼, 텍스트 정규화
# =============================
def _normalize_text(s: str) -> str:
    """앞/뒤 공백 줄 제거 + 3줄 이상 연속 빈 줄은 2줄로 축약."""
    s = s.replace("\r\n", "\n")
    lines = s.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    out, blanks = [], 0
    for ln in lines:
        if ln.strip() == "":
            blanks += 1
            if blanks <= 2:
                out.append("")
        else:
            blanks = 0
            out.append(ln)
    return "\n".join(out)

def render_bubble_with_copy(message: str, key: str):
    """본문은 escape해서 안전하게 렌더, 복사 버튼은 경량 components로 오버레이."""
    message = _normalize_text(message)
    safe_html = html.escape(message)     # 화면용
    safe_raw_json = json.dumps(message)  # 클립보드용

    st.markdown(f'<div class="chat-bubble" id="bubble-{key}">{safe_html}</div>',
                unsafe_allow_html=True)

    components.html(f"""
    <div style="position:relative;height:0">
      <button class="copy-fab" id="copy-{key}"
              style="position:absolute; top:-58px; right:18px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <path d="M9 9h9v12H9z" stroke="currentColor"/>
          <path d="M6 3h9v3" stroke="currentColor"/>
          <path d="M6 6h3v3" stroke="currentColor"/>
        </svg>
        복사
      </button>
    </div>
    <script>
      (function(){{
        const btn = document.getElementById("copy-{key}");
        if(!btn) return;
        btn.addEventListener("click", async () => {{
          try {{
            await navigator.clipboard.writeText({safe_raw_json});
            const old = btn.innerHTML;
            btn.innerHTML = "복사됨!";
            setTimeout(()=>btn.innerHTML = old, 1200);
          }} catch(e) {{
            alert("복사 실패: " + e);
          }}
        }});
      }})();
    </script>
    """, height=0)

# =============================
# Secrets
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
# Azure OpenAI
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
# 세션 상태 (하드코딩 옵션)
# =============================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "settings" not in st.session_state:
    st.session_state.settings = {}
st.session_state.settings["num_rows"] = 5
st.session_state.settings["include_search"] = True   # 항상 켬
st.session_state.settings["safe_mode"] = False       # 스트리밍 사용

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
# 모델 호출 유틸
# =============================
def build_history_messages(max_turns=10):
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

def chat_completion(messages, temperature=0.7, max_tokens=1000):
    resp = client.chat.completions.create(
        model=AZURE["deployment"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    try:
        return resp.choices[0].message.content
    except Exception:
        return ""

# =============================
# 과거 대화 렌더 (말풍선 + 복사)
# =============================
for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        if m["role"] == "assistant":
            render_bubble_with_copy(m["content"], key=f"past-{i}")
            if m.get("law"):
                with st.expander("📋 이 턴에서 참고한 법령 요약"):
                    for j, law in enumerate(m["law"], 1):
                        st.write(f"**{j}. {law['법령명']}** ({law['법령구분명']})  | 시행 {law['시행일자']}  | 공포 {law['공포일자']}")
                        if law.get("법령상세링크"):
                            st.write(f"- 링크: {law['법령상세링크']}")
        else:
            st.markdown(m["content"])

# =============================
# 입력 & 답변
# =============================
user_q = st.chat_input("법령에 대한 질문을 입력하세요… (Enter로 전송)")

if user_q:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 사용자 메시지 표기/저장
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
    with st.chat_message("user"):
        st.markdown(user_q)

    # 법제처 맥락 검색(항상 실행)
    with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
        law_data, used_endpoint, err = search_law_data(user_q, num_rows=st.session_state.settings["num_rows"])
    if used_endpoint: st.caption(f"법제처 API endpoint: `{used_endpoint}`")
    if err: st.warning(err)
    law_ctx = format_law_context(law_data)

    # 모델 프롬프트
    model_messages = build_history_messages(max_turns=10)
    model_messages.append({
        "role": "user",
        "content": f"""사용자 질문: {user_q}

관련 법령 정보(요약):
{law_ctx}

아래 형식으로 답변하세요.
법률자문서

제목: 납품 지연에 따른 계약 해제 가능 여부에 관한 법률 검토
작성: 법제처 인공지능 법률 상담사
작성일: 오늘 일자를 출력

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

한국어로 쉽게 설명하세요."""
    })

    # ==== 스트리밍 표시 ====
    if client is None:
        final_text = "Azure OpenAI 설정이 없어 기본 안내를 제공합니다.\n\n" + law_ctx
        with st.chat_message("assistant"):
            render_bubble_with_copy(final_text, key=f"ans-{ts}")
    else:
        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_text, buffer = "", ""
            try:
                placeholder.markdown('<div class="chat-bubble"><span class="typing-indicator"></span> 답변 생성 중...</div>',
                                     unsafe_allow_html=True)
                for piece in stream_chat_completion(model_messages, temperature=0.7, max_tokens=1000):
                    buffer += piece
                    if len(buffer) >= 200:
                        full_text += buffer; buffer = ""
                        preview = html.escape(_normalize_text(full_text[-1500:]))  # 최근만
                        placeholder.markdown(f'<div class="chat-bubble">{preview}</div>', unsafe_allow_html=True)
                        time.sleep(0.05)
                if buffer:
                    full_text += buffer
                    preview = html.escape(_normalize_text(full_text))
                    placeholder.markdown(f'<div class="chat-bubble">{preview}</div>', unsafe_allow_html=True)
            except Exception as e:
                full_text = f"답변 생성 중 오류가 발생했습니다: {e}\n\n{law_ctx}"
                placeholder.markdown(f'<div class="chat-bubble">{html.escape(_normalize_text(full_text))}</div>',
                                     unsafe_allow_html=True)

        # 미리보기 제거 후 최종 말풍선 1번만 출력(중복 방지)
        placeholder.empty()
        final_text = _normalize_text(full_text)
        render_bubble_with_copy(final_text, key=f"ans-{ts}")

    # 대화 저장
    st.session_state.messages.append({
        "role": "assistant", "content": final_text,
        "law": law_data, "ts": ts
    })
