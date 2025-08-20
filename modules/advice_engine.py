# modules/advice_engine.py  (통합버전: 스트리밍 + 조문 직링크 후처리 포함)
from __future__ import annotations
from typing import Callable, Dict, List, Optional, Tuple, Generator, Any

# =========================
# 조문 직링크 생성 유틸 (내장)
# =========================
import re
from urllib.parse import quote

# 자주 쓰는 약칭 보정(필요 시 추가)
ALIAS_MAP: Dict[str, str] = {
    "형소법": "형사소송법",
    "민소법": "민사소송법",
    "민집법": "민사집행법",
    # "형법": "형법",
}

# "민법 제839조의2" / "민사소송법 제163조" 등 패턴
ARTICLE_PAT = re.compile(
    r'(?P<law>[가-힣A-Za-z0-9·()\s]{2,40})\s*제(?P<num>\d{1,4})조(?P<ui>(의\d{1,3}){0,2})'
)

def _normalize_law_name(name: str) -> str:
    name = (name or "").strip()
    return ALIAS_MAP.get(name, name)

def _make_deep_article_url(law_name: str, article_label: str) -> str:
    """
    law.go.kr 조문 슬러그:
      https://law.go.kr/법령/<법령명>/<제N조(의M)>
    예) 민법 제839조의2 -> .../법령/민법/제839조의2
        민사소송법 제163조 -> .../법령/민사소송법/제163조
    """
    return f"https://law.go.kr/법령/{quote(law_name)}/{quote(article_label)}"

def _extract_article_citations(text: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for m in ARTICLE_PAT.finditer(text or ""):
        law = _normalize_law_name(m.group("law"))
        art = f"제{m.group('num')}조{m.group('ui') or ''}"
        found.append((law, art))
    # 유니크 보장
    return list({(l, a) for (l, a) in found})

def _render_article_links_block(citations: List[Tuple[str, str]]) -> str:
    if not citations:
        return ""
    lines = ["", "### 참고 링크(조문)"]
    for law, art in sorted(citations):
        url = _make_deep_article_url(law, art)
        lines.append(f"- [{law} {art}]({url})")
    return "\n".join(lines)

def merge_article_links_block(text: str) -> str:
    """
    본문 내 '법령명 제N조(의M)' 패턴을 수집하여
    문서 끝에 '### 참고 링크(조문)' 블록을 추가/갱신.
    """
    citations = _extract_article_citations(text)
    block = _render_article_links_block(citations)
    if not block:
        return text

    # 기존 블록이 있으면 교체, 없으면 추가
    pat_block = re.compile(r'\n### 참고 링크\(조문\)[\s\S]*$', re.M)
    if pat_block.search(text or ""):
        return pat_block.sub(block, text or "")
    return (text or "").rstrip() + "\n" + block + "\n"


# =========================
# 본 엔진
# =========================
ToolFn = Callable[..., Dict[str, Any]]
PrefetchFn = Callable[..., Any]
SummarizeFn = Callable[..., str]

def _safe_json_dumps(obj: Any) -> str:
    try:
        import json
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"

class AdviceEngine:
    """
    LLM 호출 + (선택)툴콜 + 스트리밍 처리 + '조문 직링크' 후처리 엔진.

    generate() 반환:
      - stream=True  -> 제너레이터:
           ("delta", 텍스트조각, law_links) ... 여러 번
           ("final", 최종전체텍스트, law_links) ... 1번
      - stream=False -> 제너레이터:
           ("final", 최종전체텍스트, law_links) ... 1번
    """

    def __init__(
        self,
        client: Any,
        model: str,
        tools: List[Dict[str, Any]],
        safe_chat_completion: Callable[..., Dict[str, Any]],
        tool_search_one: ToolFn,
        tool_search_multi: ToolFn,
        prefetch_law_context: Optional[PrefetchFn] = None,
        summarize_laws_for_primer: Optional[SummarizeFn] = None,
        temperature: float = 0.2,
        # 라우팅/프롬프트는 외부(app.py 또는 다른 모듈)에서 처리해 messages로 넣어주는 설계도 가능하지만,
        # 여기서는 messages를 이 클래스에서 구성하는 형태(일반적 사용)를 가정합니다.
    ):
        self.client = client
        self.model = model
        self.tools = tools
        self.scc = safe_chat_completion
        self.tool_search_one = tool_search_one
        self.tool_search_multi = tool_search_multi
        self.prefetch_law_context = prefetch_law_context
        self.summarize_laws_for_primer = summarize_laws_for_primer
        self.temperature = temperature

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

        # 1) 메시지 구성
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        # (선택) 사전 법령 컨텍스트 프라이머 — 도구 모드에서만
        if allow_tools and primer_enable and self.prefetch_law_context and self.summarize_laws_for_primer:
            try:
                pre = self.prefetch_law_context(user_q, num_rows_per_law=3)
                primer = self.summarize_laws_for_primer(pre, max_items=6)
                if primer:
                    msgs.append({"role": "system", "content": primer})
            except Exception:
                # 프라이머 실패는 무시하고 계속
                pass

        msgs.append({"role": "user", "content": user_q})

        # 2) 1차 호출 (툴콜 허용/차단)
        tools = self.tools if allow_tools else []
        tool_choice = "auto" if allow_tools else "none"

        resp1 = self.scc(
            self.client,
            messages=msgs,
            model=self.model,
            stream=False,
            allow_retry=True,
            tools=tools,
            tool_choice=tool_choice,
            temperature=self.temperature,
            max_tokens=800,
        )

        if resp1.get("type") == "blocked_by_content_filter":
            yield ("final", resp1.get("message") or "안전정책으로 답변을 생성할 수 없습니다.", [])
            return
        if "resp" not in resp1:
            yield ("final", "모델이 일시적으로 응답하지 않습니다. 잠시 뒤 다시 시도해 주세요.", [])
            return

        msg1 = resp1["resp"].choices[0].message
        law_for_links: List[Dict[str, Any]] = []

        # 3) 툴 실행
        if getattr(msg1, "tool_calls", None):
            msgs.append({"role": "assistant", "tool_calls": msg1.tool_calls})
            for call in msg1.tool_calls:
                args = {}
                try:
                    import json
                    args = json.loads(call.function.arguments or "{}")
                except Exception:
                    pass

                if call.function.name == "search_one":
                    result = self.tool_search_one(**args)
                elif call.function.name == "search_multi":
                    result = self.tool_search_multi(**args)
                else:
                    result = {"error": f"unknown tool: {call.function.name}"}

                # 링크용 결과 축적
                if isinstance(result, dict) and result.get("items"):
                    law_for_links.extend(result["items"])
                elif isinstance(result, list):
                    for r in result:
                        if isinstance(r, dict) and r.get("items"):
                            law_for_links.extend(r["items"])

                msgs.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _safe_json_dumps(result),
                })

        # 4) 최종 호출
        if stream:
            resp2 = self.scc(
                self.client, messages=msgs, model=self.model,
                stream=True, allow_retry=True, temperature=self.temperature, max_tokens=1400,
            )
            if resp2.get("type") == "blocked_by_content_filter":
                yield ("final", resp2.get("message") or "안전정책으로 답변을 생성할 수 없습니다.", law_for_links)
                return

            # 스트리밍: delta를 그대로 전달, 종료 시 '조문 직링크' 블록만 추가로 한 번 더 흘려보냄
            out = ""
            for ch in resp2["stream"]:
                try:
                    c = ch.choices[0]
                    if getattr(c, "finish_reason", None):
                        break
                    d = getattr(c, "delta", None)
                    txt = getattr(d, "content", None) if d else None
                    if txt:
                        out += txt
                        yield ("delta", txt, law_for_links)
                except Exception:
                    continue

            # 스트림 종료: 본문에 조문 링크 블록 머지
            out2 = merge_article_links_block(out)
            addon = out2[len(out):]  # 추가된 꼬리만 delta로 전송
            if addon.strip():
                yield ("delta", addon, law_for_links)
            yield ("final", out2, law_for_links)
            return

        else:
            # 논-스트리밍: 최종 텍스트에 블록 머지 후 한 번만 반환
            resp2 = self.scc(
                self.client, messages=msgs, model=self.model,
                stream=False, allow_retry=True, temperature=self.temperature, max_tokens=1400,
            )
            if resp2.get("type") == "blocked_by_content_filter":
                yield ("final", resp2.get("message") or "안전정책으로 답변을 생성할 수 없습니다.", law_for_links)
                return

            final_text = resp2["resp"].choices[0].message.content or ""
            final_text = merge_article_links_block(final_text)
            yield ("final", final_text, law_for_links)
            return
