# modules/advice_engine.py — 깨끗한 통합 버전 (툴콜 + 스트리밍 + 조문 직링크 후처리)
from __future__ import annotations

from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
import json
import re

# =========================
# 외부 유틸 안전 임포트 (resolve_article_url)
# =========================
try:
    from modules.linking import resolve_article_url  # type: ignore
except Exception:  # pragma: no cover
    try:
        from linking import resolve_article_url  # type: ignore
    except Exception:
        # 최후 폴백: 무해한 더미
        def resolve_article_url(law: str, art_label: str) -> str:
            law_q = law.strip().replace(" ", "+")
            art_q = art_label.strip().replace(" ", "+")
            return f"https://www.law.go.kr/{law_q}/{art_q}"

# =========================
# "참고 링크(조문)" 블록 생성기
# =========================
_LINK_PATTERN = re.compile(
    r"(?P<law>[가-힣A-Za-z0-9·\(\) ]{2,40})\s+(?P<art>제\s*\d+\s*조(?:의\s*\d+)?)(?![^\n]*\])"
)

def _render_article_links_block(citations: List[Tuple[str, str]]) -> str:
    if not citations:
        return ""
    lines = ["", "### 참고 링크(조문)"]
    # 중복 제거 + 정렬
    seen = set()
    for law, art in citations:
        key = (law.strip(), art.strip())
        if key in seen:
            continue
        seen.add(key)
    items = sorted(seen, key=lambda x: (x[0], x[1]))
    for law, art in items:
        try:
            url = resolve_article_url(law, art)
        except Exception:
            url = ""
        if url:
            lines.append(f"- [{law} {art}]({url})")
        else:
            lines.append(f"- {law} {art}")
    return "\n".join(lines)

def _collect_citations_from_text(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if not text:
        return out
    for m in _LINK_PATTERN.finditer(text):
        law = (m.group("law") or "").strip()
        art = (m.group("art") or "").strip()
        if law and art:
            # 표기 정리
            art = re.sub(r"\s+", "", art)  # "제 83 조" → "제83조"
            art = art.replace("의", "의")  # idempotent
            out.append((law, art))
    return out

def merge_article_links_block(body: str, seed_citations: Optional[List[Tuple[str, str]]] = None) -> str:
    """
    본문 내 '법령명 제N조(의M)' 패턴과 seed_citations를 합쳐
    문서 끝에 '### 참고 링크(조문)' 블록을 추가/갱신.
    """
    text = (body or "").rstrip()
    citations: List[Tuple[str, str]] = []
    if seed_citations:
        citations.extend(seed_citations)
    citations.extend(_collect_citations_from_text(text))

    block = _render_article_links_block(citations)
    if not block:
        return text
    # 기존 블록 제거 후 재부착 (중복 방지)
    text = re.sub(r"\n+### 참고 링크\(조문\)[\s\S]*$", "", text, flags=re.MULTILINE)
    return text + "\n" + block + "\n"

# =========================
# 타입 별칭
# =========================
ToolFn = Callable[..., Dict[str, Any]]
PrefetchFn = Callable[..., Any]
SummarizeFn = Callable[..., str]

# =========================
# 내부 헬퍼
# =========================
def _msg_dict(role: str, content: str) -> Dict[str, Any]:
    return {"role": role, "content": content}

def _first_choice(resp: Any) -> Any:
    # dict/obj 호환
    if resp is None:
        return None
    choices = getattr(resp, "choices", None)
    if choices is None and isinstance(resp, dict):
        choices = resp.get("choices")
    if not choices:
        return None
    return choices[0]

def _message_of(choice: Any) -> Any:
    msg = getattr(choice, "message", None)
    if msg is None and isinstance(choice, dict):
        msg = choice.get("message")
    return msg

def _content_of_message(msg: Any) -> str:
    c = getattr(msg, "content", None)
    if c is None and isinstance(msg, dict):
        c = msg.get("content")
    return c or ""

def _tool_calls_of_message(msg: Any) -> List[Any]:
    tc = getattr(msg, "tool_calls", None)
    if tc is None and isinstance(msg, dict):
        tc = msg.get("tool_calls")
    return tc or []

def _json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"

def _try_int(x, default=5):
    try:
        return int(x)
    except Exception:
        return default

# =========================
# 본 엔진
# =========================
class AdviceEngine:
    """
    LLM 호출 + (선택)툴콜 + 스트리밍 처리 + '조문 직링크' 후처리 엔진.

    generate()는 제너레이터로 동작하며,
      - stream=True  -> ("delta", 텍스트조각, law_links) ... 여러 번 + ("final", 전체, law_links)
      - stream=False -> ("final", 전체, law_links) 한 번만
    """

    def __init__(
        self,
        client: Any,
        model: str,
        tools: List[Dict[str, Any]],
        safe_chat_completion: Callable[..., Dict[str, Any]],
        tool_search_one: ToolFn,
        tool_search_multi: ToolFn,
        tool_get_article: Optional[ToolFn] = None,
        prefetch_law_context: Optional[PrefetchFn] = None,
        summarize_laws_for_primer: Optional[SummarizeFn] = None,
        temperature: float = 0.2,
    ):
        self.client = client
        self.model = model
        self.tools = tools
        self.scc = safe_chat_completion
        self.tool_search_one = tool_search_one
        self.tool_search_multi = tool_search_multi
        self.tool_get_article = tool_get_article
        self.prefetch_law_context = prefetch_law_context
        self.summarize_laws_for_primer = summarize_laws_for_primer
        self.temperature = temperature

    # ---- 핵심 제너레이터 ----
    def generate(
        self,
        user_q: str,
        *,
        system_prompt: str,
        allow_tools: bool,
        num_rows: int = 5,
        stream: bool = True,
        primer_enable: bool = True,
    ) -> Generator[Tuple[str, str, List[Dict[str, Any]]], None, None]:

        if not self.client or not self.model:
            yield ("final", "엔진이 설정되지 않았습니다.", [])
            return

        # 1) 메시지 조립
        sys_prompt = system_prompt or ""
        if allow_tools and primer_enable and self.prefetch_law_context and self.summarize_laws_for_primer:
            # 사전 법령 프라이머 (간단 요약) - 시스템에 병합
            try:
                pre = self.prefetch_law_context(user_q, num_rows_per_law=3)
                primer = self.summarize_laws_for_primer(pre, max_items=6)
                if primer:
                    sys_prompt = f"{sys_prompt}\n\n[사전 요약]\n{primer}"
            except Exception:
                pass

        messages: List[Dict[str, Any]] = [
            _msg_dict("system", sys_prompt),
            _msg_dict("user", user_q),
        ]

        law_citations: List[Tuple[str, str]] = []  # (law, art) 모음

        # 2) 1차 호출: 툴콜 유도 (stream=False)
        if allow_tools:
            try:
                resp = self.scc(
                    self.client,
                    messages=messages,
                    model=self.model,
                    tools=self.tools,
                    stream=False,
                    allow_retry=True,
                    temperature=self.temperature,
                    max_tokens=800,
                )
            except TypeError:
                # 일부 scc는 tools 파라미터 미지원일 수 있음
                resp = self.scc(
                    self.client,
                    messages=messages,
                    model=self.model,
                    stream=False,
                    allow_retry=True,
                    temperature=self.temperature,
                    max_tokens=800,
                )

            ch = _first_choice(resp)
            msg1 = _message_of(ch) if ch else None
            tool_calls = _tool_calls_of_message(msg1) if msg1 else []

            # 모델이 어떤 보조 텍스트를 냈다면 그대로 대화 이력에 추가
            if msg1 is not None:
                messages.append({
                    "role": "assistant",
                    "content": _content_of_message(msg1),
                    "tool_calls": tool_calls if tool_calls else None,
                })

            # 2-1) 툴 실행 및 결과 주입
            for call in tool_calls:
                try:
                    fn_name = getattr(call.function, "name", None) if hasattr(call, "function") else None
                except Exception:
                    fn = getattr(call, "function", None) if hasattr(call, "function") else None
                    fn_name = getattr(fn, "name", None) if fn else None
                if fn_name is None and isinstance(call, dict):
                    fn_name = ((call.get("function") or {}).get("name"))

                # 인자 파싱
                try:
                    raw_args = getattr(call.function, "arguments", None) if hasattr(call, "function") else None
                    if raw_args is None and isinstance(call, dict):
                        raw_args = ((call.get("function") or {}).get("arguments"))
                    args = json.loads(raw_args or "{}")
                except Exception:
                    args = {}

                result: Dict[str, Any] = {"error": f"unknown tool: {fn_name}"}

                if fn_name == "search_one" and self.tool_search_one:
                    # num_rows 보정
                    if "num_rows" not in args:
                        args["num_rows"] = _try_int(num_rows, 5)
                    result = self.tool_search_one(**args)

                elif fn_name == "search_multi" and self.tool_search_multi:
                    if "num_rows" not in args:
                        args["num_rows"] = _try_int(num_rows, 5)
                    result = self.tool_search_multi(**args)

                elif fn_name == "get_article" and self.tool_get_article:
                    result = self.tool_get_article(**args)
                    # 링크 시드 수집 (법령명/조문)
                    law = (result or {}).get("law")
                    art = (result or {}).get("article_label")
                    if law and art:
                        law_citations.append((str(law), str(art)))

                # 툴 결과를 메시지에 추가
                tool_call_id = getattr(call, "id", None) if hasattr(call, "id") else None
                if tool_call_id is None and isinstance(call, dict):
                    tool_call_id = call.get("id")
                messages.append({
                    "role": "system",
                    "content": "위 도구 결과를 이미 반영했다. 이제는 도구를 다시 호출하지 말고, 한국어 최종 답변만 작성하라."
        })

        # 3) 2차 호출: 답변 생성 (stream 또는 단발)
        if stream:
            resp2 = self.scc(
                self.client,
                messages=messages,
                model=self.model,
                tools=None,
                stream=True,
                allow_retry=True,
                temperature=self.temperature,
                max_tokens=1400,
            )
            # 스트리밍: delta를 중계하고, 종료 시 링크 블록 병합
            out = ""
            stream_iter = None
            # scc 결과가 dict/객체 어느 쪽이든 'stream' 속성/키를 제공한다고 가정
            stream_iter = getattr(resp2, "stream", None)
            if stream_iter is None and isinstance(resp2, dict):
                stream_iter = resp2.get("stream")
            if stream_iter is None:
                # 스트리밍이 불가하면 논-스트리밍과 동일 처리
                stream = False
            else:
                for ev in stream_iter:
                    try:
                        choice = _first_choice(ev)
                        delta = getattr(choice, "delta", None)
                        txt = getattr(delta, "content", None) if delta else None
                        if not txt and isinstance(choice, dict):
                            d = choice.get("delta") or {}
                            txt = (d or {}).get("content")
                        if txt:
                            out += txt
                            # 실시간 delta
                            law_links = [
                                {"law": l, "article_label": a, "url": resolve_article_url(l, a)}
                                for (l, a) in law_citations
                            ]
                            yield ("delta", txt, law_links)
                        # finish_reason 체크
                        fr = getattr(choice, "finish_reason", None)
                        if fr is None and isinstance(choice, dict):
                            fr = choice.get("finish_reason")
                        if fr:
                            break
                    except Exception:
                        # 유연하게 무시
                        pass

                # 스트림 종료: 꼬리로 링크 블록 합성
                out2 = merge_article_links_block(out, seed_citations=law_citations)
                addon = out2[len(out):]
                if addon.strip():
                    law_links = [
                        {"law": l, "article_label": a, "url": resolve_article_url(l, a)}
                        for (l, a) in law_citations
                    ]
                    yield ("delta", addon, law_links)
                law_links = [
                    {"law": l, "article_label": a, "url": resolve_article_url(l, a)}
                    for (l, a) in law_citations
                ]
                yield ("final", out2, law_links)
                return

        # --- 논-스트리밍 경로 ---
        resp3 = self.scc(
            self.client,
            messages=messages,
            model=self.model,
            tools=self.tools if allow_tools else None,
            stream=False,
            allow_retry=True,
            temperature=self.temperature,
            max_tokens=1400,
        )
        ch3 = _first_choice(resp3)
        msg3 = _message_of(ch3) if ch3 else None
        content = _content_of_message(msg3) if msg3 else ""
        final = merge_article_links_block(content, seed_citations=law_citations)
        law_links = [
            {"law": l, "article_label": a, "url": resolve_article_url(l, a)}
            for (l, a) in law_citations
        ]
        yield ("final", final, law_links)

# ================
# (선택) 모드 관련 폴백
# ================
try:
    from .legal_modes import Intent  # type: ignore
except Exception:  # pragma: no cover
    class Intent:  # 최소 폴백(타입힌트용)
        QUICK = "quick"
        LAWFINDER = "lawfinder"
        MEMO = "memo"
        DRAFT = "draft"

def pick_mode(det_intent: "Intent", conf: float) -> "Intent":
    """단순 통과(필요시 규칙 추가)."""
    return det_intent
