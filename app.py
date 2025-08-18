# app.py  — 안전 베이스라인 (초기 화면 복사 버튼 X, 답변 말풍선만 복사 버튼 O, 오프라인 안내 표시 안 함)

import re
from datetime import datetime
from typing import Generator, List, Tuple, Dict, Any

import streamlit as st
from streamlit.components.v1 import html

# =========================
# 전역 설정 (필요 시 여러분 환경에 맞게 교체)
# =========================
AZURE = None     # 예: {"deployment": "..."}  (없으면 오프라인 분기로 처리)
client = None    # 예: Azure/OpenAI 클라이언트 객체

# =========================
# Utilities
# =========================
def _normalize_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in s.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    merged, i = [], 0
    # 번호 단독행 + 다음 줄 제목을 "1. 제목" 형태로 병합
    num_pat = re.compile(r'^\s*((\d+)|([IVXLC]+)|([ivxlc]+))\s*[\.\)]\s*$')
    while i < len(lines):
        cur = lines[i]
        m = num_pat.match(cur)
        if m:
            j = i + 1
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


def _dedupe_blocks(text: str) -> str:
    # 같은 문단 반복, "법률 자문 메모 ..." 중복 등을 제거
    s = _normalize_text(text or "")

    # 1) 동일 문단 연속 중복 제거
    lines, out, prev = s.split("\n"), [], None
    for ln in lines:
        if ln.strip() and ln == prev:
            continue
        out.append(ln)
        prev = ln
    s = "\n".join(out)

    # 2) "법률 자문 메모"로 시작하는 동일 본문 2중 출력 방지
    pat = re.compile(r'(법률\s*자문\s*메모[\s\S]{50,}?)(?:\n+)\1', re.I)
    s = pat.sub(r'\1', s)

    # 3) 내부 절차 문구(의도분석/추가검색/재검색)가 남았으면 제거
    s = re.sub(
        r'^\s*\d+\.\s*\*\*?(사용자의 의도 분석|추가 검색|재검색)\*\*?.*?(?=\n\d+\.|\Z)',
        '',
        s,
        flags=re.M | re.S
    )

    # 여분 빈 줄 정리
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s


def fix_links_with_lawdata(text: str, laws: List[Dict[str, Any]]) -> str:
    """law.go.kr 상대경로 → 절대 URL 보정 등. 필요 시 고도화."""
    if not text:
        return ""
    s = text
    # 예: '/DRF/lawService.do?...' → 'https://www.law.go.kr/DRF/lawService.do?...'
    s = re.sub(r'\((/DRF/[^)]+)\)', r'(https://www.law.go.kr\1)', s)
    s = re.sub(r'\]\((/DRF/[^)]+)\)', r'](https://www.law.go.kr\1)', s)
    return s


def format_law_context(laws: List[Dict[str, Any]]) -> str:
    """법령 미리보기 텍스트. (필요시 사이드바 등에서만 사용)"""
    if not laws:
        return ""
    buf = []
    for i, law in enumerate(laws, 1):
        nm = law.get("법령명") or law.get("법령명한글") or "법령"
        kind = law.get("법령구분") or law.get("법령구분명") or "-"
        ef = law.get("시행일자", "-")
        pf = law.get("공포일자", "-")
        link = law.get("법령상세링크", "")
        line = f"**{i}. {nm}** ({kind}) | 시행 {ef} | 공포 {pf}"
        if link:
            if link.startswith("/"):
                link = "https://www.law.go.kr" + link
            line += f"\n- 링크: {link}"
        buf.append(line)
    return "\n\n".join(buf)


def choose_output_template(q: str) -> str:
    # 강제 템플릿 사용 안 함 (호출 호환만 유지)
    return ""


def render_bubble_with_copy(message: str, key: str, show_copy: bool = True):
    """말풍선 + 복사 버튼(옵션). 메인 답변/과거 assistant 메시지에만 show_copy=True."""
    msg = _normalize_text(message or "")
    st.markdown(msg)
    if not show_copy:
        return
    # 간단한 복사 버튼 (브라우저 클립보드)
    safe_text = (msg or "").replace("\\", "\\\\").replace("`", "\\`").replace("</", "<\/")
    html(f"""
    <div style="margin-top:6px">
      <button id="copy-{key}" style="padding:6px 10px;border:1px solid #ddd;border-radius:8px;cursor:pointer;"
        onclick="navigator.clipboard.writeText(`{safe_text}`); 
                 const b=this; const t=b.innerText; b.innerText='복사됨!'; 
                 setTimeout(()=>b.innerText=t, 1500);">
        복사
      </button>
    </div>
    """, height=40)


# =========================
# 도구/LLM 스트리밍 (프로젝트 함수와 인터페이스만 맞춤)
# =========================
def ask_llm_with_tools(user_q: str, num_rows: int = 5, stream: bool = True) -> Generator[Tuple[str, str, List[Dict[str, Any]]], None, None]:
    """
    yield ("delta", 토막문자열, None)  — 스트리밍 중간 토막
    yield ("final", 최종문자열, 법령리스트) — 스트리밍 완료

    ⚠️ 오프라인/미설정일 때는 메인에 아무 것도 표시하지 않기 위해 빈 본문을 final로 보낸다.
    """
    # --- 오프라인/미설정 분기: 본문 출력 없음 ---
    if client is None or AZURE is None:
        yield ("final", "", [])
        return

    # --- TODO: 여기서 실제 LLM + 함수콜(법제처 API 래퍼)을 붙이세요 ---
    # 예시(스트리밍 흉내): delta 2번 → final 1번
    # for chunk in your_streaming_call(...):
    #     yield ("delta", chunk, None)
    # 최종 결과/법령 리스트
    # laws = [...]
    # yield ("final", full_text, laws)

    # 안전 기본(빈 응답)
    yield ("final", "", [])


def find_law_with_fallback(user_q: str, num_rows: int = 10) -> Tuple[List[Dict[str, Any]], str, str, str]:
    """오프라인 폴백(선택적으로 사용). 메인 본문엔 표시하지 않음."""
    # TODO: 필요 시 구현. 여기선 빈 값 반환.
    return [], "", "", "offline"


# =========================
# Streamlit App
# =========================
st.set_page_config(page_title="법률 자문 챗봇", page_icon="⚖️", layout="wide")

# 대화 상태
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []

# 상단 헤더/입력
st.title("⚖️ 법률 자문 챗봇")
st.caption("법령·행정규칙·자치법규·조약 등을 검색해 답변합니다.")

# 초기 안내 (대화가 비어 있을 때만; 복사 버튼 없음)
if not st.session_state.messages:
    st.markdown(
        "- 질문을 입력하거나 관련 문서를 첨부해 주세요.\n"
        "- 답변엔 근거 조문/링크가 포함될 수 있습니다.\n"
        "- 대화가 시작되면 어시스턴트 답변에만 **복사 버튼**이 표시됩니다."
    )

# 과거 대화 렌더 (assistant만 복사 버튼 O)
with st.container():
    for i, m in enumerate(st.session_state.messages):
        with st.chat_message(m["role"]):
            if m["role"] == "assistant":
                render_bubble_with_copy(m.get("content", ""), key=f"past-{i}", show_copy=True)
                if m.get("law"):
                    with st.expander("📋 이 턴에서 참고한 법령 요약"):
                        st.markdown(format_law_context(m["law"]))
            else:
                st.markdown(m.get("content", ""))

# 입력창
user_q = st.chat_input("질문을 입력하세요")

# 입력 처리
if user_q:
    # 유저 메시지 저장/표시(복사 버튼 없음)
    st.session_state.messages.append({"role": "user", "content": user_q, "ts": datetime.now().isoformat()})
    with st.chat_message("user"):
        st.markdown(user_q)

    # 어시스턴트 답변 (복사 버튼 O)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_text, buffer = "", ""
        collected_laws: List[Dict[str, Any]] = []

        try:
            # 스트리밍 미리보기 (짧은 안내)
            placeholder.markdown("_질의를 해석하고, 관련 법령을 확인 중입니다..._")

            for kind, payload, law_list in ask_llm_with_tools(user_q, num_rows=5, stream=True):
                if kind == "delta":
                    buffer += payload or ""
                    if len(buffer) >= 200:
                        full_text += buffer
                        buffer = ""
                        placeholder.markdown(_normalize_text(full_text[-1500:]))
                elif kind == "final":
                    full_text += (payload or "")
                    collected_laws = law_list or []
                    break

            if buffer:
                full_text += buffer

        except Exception:
            # 폴백: 메인 말풍선엔 아무 것도 뿌리지 않음(빈 본문)
            full_text, collected_laws = "", []

        # 후처리 & 출력
        final_text = _normalize_text(full_text)
        final_text = fix_links_with_lawdata(final_text, collected_laws)
        final_text = _dedupe_blocks(final_text)

        placeholder.empty()
        with placeholder.container():
            render_bubble_with_copy(final_text, key=f"ans-{datetime.now().timestamp()}", show_copy=True)

        # 대화 기록 저장
        st.session_state.messages.append({
            "role": "assistant",
            "content": final_text,
            "law": collected_laws,
            "ts": datetime.now().isoformat(),
        })
