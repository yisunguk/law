# app.py — Chat-bubble + Copy (button below, no overlay) FINAL
import time, json, html, re, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI

# =============================
# Page & Global Styles
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

  /* 폭 살짝 확대 */
  .block-container{max-width:1020px;margin:0 auto;}
  .stChatInput{max-width:1020px;margin-left:auto;margin-right:auto;}

  .header{
    text-align:center;padding:1rem;border-radius:12px;
    background:linear-gradient(135deg,#8b5cf6,#a78bfa);color:#fff;margin:0 0 1rem 0
  }

  /* 말풍선(가독성 압축) */
  .chat-bubble{
    background:var(--bubble-bg,#1f1f1f);
    color:var(--bubble-fg,#f5f5f5);
    border-radius:14px;
    padding:14px 16px;
    font-size:16px!important;
    line-height:1.6!important;
    white-space:pre-wrap;
    word-break:break-word;
    box-shadow:0 1px 8px rgba(0,0,0,.12);
  }
  /* 문단/목록/인용 마진 축소 */
  .chat-bubble p,
  .chat-bubble li,
  .chat-bubble blockquote{ margin:0 0 8px 0; }
  .chat-bubble blockquote{
    padding-left:12px;border-left:3px solid rgba(255,255,255,.2);
  }

  [data-theme="light"] .chat-bubble{
    --bubble-bg:#ffffff; --bubble-fg:#222222;
    box-shadow:0 1px 8px rgba(0,0,0,.06);
  }

  /* 말풍선 아래 줄의 복사 버튼 */
  .copy-row{ display:flex;justify-content:flex-end;margin:6px 4px 0 0; }
  .copy-btn{
    display:inline-flex;align-items:center;gap:6px;
    padding:6px 10px;border:1px solid rgba(255,255,255,.15);
    border-radius:10px;background:rgba(0,0,0,.25);
    backdrop-filter:blur(4px);cursor:pointer;font-size:12px;color:inherit;
  }
  [data-theme="light"] .copy-btn{background:rgba(255,255,255,.9);border-color:#ddd;}
  .copy-btn svg{pointer-events:none}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="header"><h2>⚖️ 법제처 인공지능 법률 상담 플랫폼</h2>'
    '<div>법제처 공식 데이터를 AI가 분석해 답변을 제공합니다</div>'
    '<div>당신의 문제를 입력하면 법률 자문서를 출력해 줍니다. 당신의 문제를 입력해 보세요</div></div>',
    unsafe_allow_html=True,
)

# =============================
# Text Normalization
# =============================
def _normalize_text(s: str) -> str:
    """
    - 개행 표준화
    - 앞/뒤 빈 줄 제거
    - 연속 빈 줄 최대 1개 허용
    - '번호만 있는 줄'을 다음 줄 제목과 합치기
      (1. / 1) / I. / iii) 등 폭넓게 처리)
    """
    # 개행 표준화
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # 라인 끝 공백 제거 + 앞/뒤 빈 줄 제거
    lines = [ln.rstrip() for ln in s.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    # 번호줄 + 제목 병합
    merged = []
    i = 0
    num_pat = re.compile(r'^\s*((\d+)|([IVXLC]+)|([ivxlc]+))\s*[\.\)]\s*$')  # 1. / 1) / III. / iii)
    while i < len(lines):
        cur = lines[i]
        m = num_pat.match(cur)
        if m:
            j = i + 1
            # 번호 뒤의 연속 빈 줄 건너뛰고 실제 텍스트 줄 찾기
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                number = (m.group(2) or m.group(3) or m.group(4)).upper()
                title = lines[j].lstrip()
                merged.append(f"{number}. {title}")
                i = j + 1
                continue
        merged.append(cur)
        i += 1

    # 연속 빈 줄 최대 1개 허용
    out, prev_blank = [], False
    for ln in merged:
        if ln.strip() == "":
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            prev_blank = False
            out.append(ln)

    return "\n".join(out)

# =============================
# Bubble Renderer (button below)
# =============================
def render_bubble_with_copy(message: str, key: str):
    """본문은 escape하여 안전하게 렌더, 복사 버튼은 '아래 줄'에 항상 보이게."""
    message = _normalize_text(message)
    safe_html = html.escape(message)     # 화면용
    safe_raw_json = json.dumps(message)  # 클립보드용

    st.markdown(f'<div class="chat-bubble" id="bubble-{key}">{safe_html}</div>',
                unsafe_allow_html=True)

    components.html(f"""
    <div class="copy-row">
      <button id="copy-{key}" class="copy-btn">
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
        if (!btn) return;
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
    """, height=40)

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
# Session (Hardcoded Options)
# =============================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "settings" not in st.session_state:
    st.session_state.settings = {}
st.session_state.settings["num_rows"] = 5
st.session_state.settings["include_search"] = True   # 항상 켬
st.session_state.settings["safe_mode"] = False       # 스트리밍 사용

# =============================
# MOLEG API (Law Search)
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
# Model Helpers
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
# Render History (bubble + copy)
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
# Input & Answer
# =============================
user_q = st.chat_input("법령에 대한 질문을 입력하세요… (Enter로 전송)")

if user_q:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 사용자 메시지
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": ts})
    with st.chat_message("user"):
        st.markdown(user_q)

    # 법제처 검색(항상 실행)
    with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
        law_data, used_endpoint, err = search_law_data(user_q, num_rows=st.session_state.settings["num_rows"])
    if used_endpoint: st.caption(f"법제처 API endpoint: `{used_endpoint}`")
    if err: st.warning(err)
    law_ctx = format_law_context(law_data)

    # 프롬프트
    model_messages = build_history_messages(max_turns=10)
    model_messages.append({
        "role": "user",
        "content": f"""사용자 질문: {user_q}

관련 법령 정보(요약):
{law_ctx}

아래 형식으로 답변하세요.
당신은 “대한민국 법령정보 챗봇”입니다.
당신이 제공하는 모든 법률·규칙·판례·조약 등 정보는
법제처 국가법령정보센터(www.law.go.kr)의
“국가법령정보 공유서비스 Open API”를 통해 조회됩니다.

[제공 범위]
1. 국가 법령(현행) - 법률, 시행령, 시행규칙 등 (target=law)
2. 행정규칙 - 예규, 고시, 훈령·지침 등 (target=admrul)
3. 자치법규 - 전국 지자체의 조례·규칙·훈령 (target=ordin)
4. 조약 - 양자·다자 조약 (target=trty)
5. 법령 해석례 - 법제처 유권해석 사례 (target=expc)
6. 헌법재판소 결정례 - 위헌·합헌·각하 등 (target=detc)
7. 별표·서식 - 각 법령에 첨부된 별표, 서식 (target=licbyl)
8. 법령 용어 사전 - 법령에 사용되는 용어와 정의 (target=lstrm)

[운영 지침]
- 반드시 사용자의 질의 의도에 따라 적절한 target을 선택하여 조회하세요.
- 답변에는 항상 법령명, 공포일자, 시행일자, 소관부처 등 주요 메타데이터를 포함하세요.
- 링크 제공 시 “www.law.go.kr” 공식 도메인 주소를 사용하세요.
- 데이터는 매일 1회 갱신되므로 최신 법령 개정 사항 반영에 시차가 있을 수 있음을 고지하세요.
- 모든 답변 하단에 “출처: 법제처 국가법령정보센터” 문구를 포함하세요.
- 법률 해석이 필요한 경우, 원문과 함께 관련 법제처 해석례나 헌재 결정례를 우선 안내하세요.
- 법적 효력에 대해 “참고용”임을 명시하고, 최종 해석·판단은 관보 및 법제처 고시·공포문을 따름을 고지하세요.

[금지 사항]
- 법령 범위를 벗어난 임의 해석 제공 금지.
- 데이터 출처를 숨기거나 변형하여 표기 금지.
- 최신성 확인 없이 확정적 표현 사용 금지.

한국어로 쉽게 설명하세요."""
    })

    # 스트리밍
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
                        preview = html.escape(_normalize_text(full_text[-1500:]))
                        placeholder.markdown(f'<div class="chat-bubble">{preview}</div>',
                                             unsafe_allow_html=True)
                        time.sleep(0.05)
                if buffer:
                    full_text += buffer
                    preview = html.escape(_normalize_text(full_text))
                    placeholder.markdown(f'<div class="chat-bubble">{preview}</div>',
                                         unsafe_allow_html=True)
            except Exception as e:
                full_text = f"답변 생성 중 오류가 발생했습니다: {e}\n\n{law_ctx}"
                placeholder.markdown(f'<div class="chat-bubble">{html.escape(_normalize_text(full_text))}</div>',
                                     unsafe_allow_html=True)

        # 미리보기 지우고 최종 말풍선 1번만 출력
        placeholder.empty()
        final_text = _normalize_text(full_text)
        render_bubble_with_copy(final_text, key=f"ans-{ts}")

    # 히스토리에 저장
    st.session_state.messages.append({
        "role": "assistant", "content": final_text, "law": law_data, "ts": ts
    })
