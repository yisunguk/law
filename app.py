# ============================================================
# app.py — Single-file Streamlit app (clean, non-duplicated)
# ============================================================
from __future__ import annotations

# -------------------- Path bootstrap (app only) --------------------
import os, sys, html, re
try:
    import streamlit as st  # type: ignore
except Exception:
    st = None  # for safety in non-UI contexts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOD_DIR  = os.path.join(BASE_DIR, "modules")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.isdir(MOD_DIR) and MOD_DIR not in sys.path:
    sys.path.insert(0, MOD_DIR)

# Optional: reduce inotify issues in hosted environments
try:
    if st:
        st.set_option("server.fileWatcherType", "none")
except Exception:
    pass

# -------------------- Project modules (lazy exports) --------------------
# Expectation: modules/__init__.py exposes lazy getters for AdviceEngine, etc.
try:
    from modules import AdviceEngine  # lazy export
except Exception:
    # Fallback to local (in case modules package not found)
    from advice_engine import AdviceEngine  # type: ignore

# Law deep-link helpers (canonical)
try:
    from modules.linking import make_pretty_article_url, resolve_article_url
except Exception:
    # Minimal fallback
    from urllib.parse import quote as _q
    def make_pretty_article_url(law: str, art: str) -> str:
        return f"https://law.go.kr/법령/{_q((law or '').strip())}/{_q((art or '').strip())}"
    resolve_article_url = make_pretty_article_url

# Optional helpers (safe wrapper / URL utils) — app runs without them too.
try:
    from llm_safety import safe_chat_completion  # type: ignore
except Exception:
    safe_chat_completion = None  # graceful fallback

try:
    from external_content import is_url, extract_first_url, extract_all_urls, fetch_article_text  # type: ignore
except Exception:
    def is_url(s: str) -> bool:
        return bool(re.match(r"^https?://", str(s or "")))
    def extract_first_url(s: str) -> str | None:
        m = re.search(r"(https?://\S+)", str(s or ""))
        return m.group(1) if m else None
    def extract_all_urls(s: str) -> list[str]:
        return re.findall(r"(https?://\S+)", str(s or ""))
    def fetch_article_text(url: str, timeout: float = 8.0) -> str:
        return ""

# -------------------- Secrets (Azure) --------------------
try:
    AZURE = st.secrets.get("azure_openai", {}) if st else {}
except Exception:
    AZURE = {}

# -------------------- Azure OpenAI client factory --------------------
try:
    from openai import AzureOpenAI
except Exception:
    AzureOpenAI = None  # runtime guard

def _make_azure_client():
    if AzureOpenAI is None:
        return None
    api_key  = (AZURE.get("api_key") or os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
    endpoint = (AZURE.get("endpoint") or os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    api_ver  = (AZURE.get("api_version") or os.getenv("AZURE_OPENAI_API_VERSION") or "2024-06-01").strip()
    if not (api_key and endpoint and api_ver):
        return None
    cli = AzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_ver)
    # router model hint (optional)
    cli.router_model = (
        AZURE.get("router_deployment")
        or AZURE.get("deployment")
        or os.getenv("AZURE_OPENAI_ROUTER_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or ""
    )
    return cli

client = _make_azure_client()

# -------------------- Session init --------------------
if st:
    if "messages" not in st.session_state:
        st.session_state.messages = []  # list[{"role":"user|assistant", "content": str}]

# -------------------- LLM ask function --------------------
def ask_llm(question: str) -> str:
    """
    Compose messages from session, add a concise system prompt, then call LLM.
    Uses AdviceEngine if Azure client is ready; otherwise tries safe_chat_completion;
    finally falls back to a static error message.
    """
    sys_prompt = (
        "너는 한국 법률 상담 도우미다. 가능한 경우 근거가 되는 법령/조문 링크를 함께 제공하고, "
        "사실에 근거하여 간결하게 설명하라."
    )
    # Keep the last 6 turns for brevity
    history = [{"role": m["role"], "content": m["content"]} for m in (st.session_state.messages[-6:] if st else [])]
    messages = [{"role": "system", "content": sys_prompt}, *history, {"role": "user", "content": question}]

    # If user included something like "건설산업기본법 제83조", attach a pretty deeplink hint.
    law_hint = ""
    try:
        m1 = re.search(r"([가-힣A-Za-z0-9]+법)\s*(제?\s*\d+\s*조(?:\s*의\s*\d+)?|\d+\s*조)", question)
        if m1:
            law = m1.group(1).strip()
            art = m1.group(2).replace(" ", "")
            if not art.startswith("제"):
                art = "제" + art
            link = resolve_article_url(law, art)
            law_hint = f"참고 법령 링크: {link}"
            messages.append({"role":"system","content":law_hint})
    except Exception:
        pass

    # (A) Preferred path: AdviceEngine with Azure client
    if client is not None:
        model = AZURE.get("deployment") or getattr(client, "router_model", "") or "gpt-4o-mini"
        try:
            engine = AdviceEngine(client=client, model=model, temperature=0.2)
            # use non-stream for simplicity in this single-file sample
            answer = engine.generate(messages, stream=False)
            if law_hint and (answer and "http" not in answer):
                answer += f"\n\n{law_hint}"
            return answer
        except Exception as e:
            return f"LLM 호출 중 오류가 발생했습니다: {e}"

    # (B) Fallback: safe_chat_completion if available
    if safe_chat_completion:
        try:
            model = AZURE.get("deployment") or "gpt-4o-mini"
            res = safe_chat_completion(client=None, messages=messages, model=model,
                                       stream=False, temperature=0.2, max_tokens=900)
            if isinstance(res, dict) and res.get("type") == "ok":
                return (res["resp"].choices[0].message.content or "").strip()
            return (res.get("message") or "일시적인 문제로 응답을 생성하지 못했습니다.").strip()
        except Exception as e:
            return f"LLM 호출 실패: {e}"

    # (C) Last fallback: no LLM available
    return "LLM 설정이 없어 답변을 생성할 수 없습니다. Streamlit secrets의 'azure_openai' 설정을 확인해 주세요."

# -------------------- UI --------------------
if st:
    st.title("⚖️ 인공지능 법률 상담가")
    st.caption("국가법령정보 한글주소(딥링크)와 함께 사실 기반으로 답변합니다. 대화 기록은 서버에 저장하지 않습니다.")

    # Sidebar: quick deeplink maker
    with st.sidebar:
        st.subheader("🔗 법령 딥링크 만들기")
        col1, col2 = st.columns(2)
        with col1:
            law_name = st.text_input("법령명", value="건설산업기본법")
        with col2:
            art_label = st.text_input("조문", value="제83조")
        if st.button("링크 생성"):
            url = resolve_article_url(law_name, art_label)
            st.success(f"[{law_name} {art_label}]({url})")

    # Display history
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Input
    user_q = st.chat_input("질문을 입력하세요 (예: 건설산업기본법 제83조 본문 알려줘)")
    if user_q:
        # add user message to session & render immediately
        st.session_state.messages.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)

        # get answer
        with st.chat_message("assistant"):
            ans = ask_llm(user_q)
            st.markdown(ans)
        st.session_state.messages.append({"role": "assistant", "content": ans})
else:
    # Non-Streamlit execution (for safety)
    print("This script is intended to run with Streamlit.")
