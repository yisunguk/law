# modules/advice_engine.py
from __future__ import annotations
from typing import Callable, Dict, List, Optional, Tuple, Generator, Any
from .legal_modes import Intent, classify_intent, pick_mode, build_sys_for_mode

ToolFn = Callable[..., Dict[str, Any]]
PrefetchFn = Callable[..., Any]
SummarizeFn = Callable[..., str]

class AdviceEngine:
    """
    · stream=True: ("delta"/"final", text, law_links) 제너레이터
    · stream=False: ("final", text, law_links) 한 번만 반환
    외부 의존성(클라이언트, 모델명, 툴콜 함수 등)을 주입해서 순환참조를 피함.
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
        num_rows: int = 5,
        stream: bool = True,
        forced_mode: Optional[str] = None,
        brief: bool = False,
    ) -> Generator[Tuple[str, str, List[Dict[str, Any]]], None, None]:

        if not self.client or not self.model:
            yield ("final", "엔진이 설정되지 않았습니다.", [])
            return

        # 1) 모드 결정
        det_intent, conf = classify_intent(user_q)
        try:
            mode = Intent(forced_mode) if forced_mode in {m.value for m in Intent} else pick_mode(det_intent, conf)
        except Exception:
            mode = pick_mode(det_intent, conf)

        use_tools = (mode in (Intent.LAWFINDER, Intent.MEMO))
        sys_prompt = build_sys_for_mode(mode, brief=brief)

        # 2) 메시지 구성
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
        # 도구 모드에서만 프라이머 주입(있을 때만)
        if use_tools and self.prefetch_law_context and self.summarize_laws_for_primer:
            try:
                pre = self.prefetch_law_context(user_q, num_rows_per_law=3)
                primer = self.summarize_laws_for_primer(pre, max_items=6)
                if primer:
                    msgs.append({"role": "system", "content": primer})
            except Exception:
                pass

        msgs.append({"role": "user", "content": user_q})

        # 3) 1차 호출 (툴콜 허용/차단)
        tools = self.tools if use_tools else []
        tool_choice = "auto" if use_tools else "none"

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

        # 4) 툴 실행
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

        # 5) 최종 호출
        if stream:
            resp2 = self.scc(
                self.client, messages=msgs, model=self.model,
                stream=True, allow_retry=True, temperature=self.temperature, max_tokens=1400,
            )
            if resp2.get("type") == "blocked_by_content_filter":
                yield ("final", resp2.get("message") or "안전정책으로 답변을 생성할 수 없습니다.", law_for_links)
                return

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
            yield ("final", out, law_for_links)
            return

            # (stream=False)
        else:
            resp2 = self.scc(
                self.client, messages=msgs, model=self.model,
                stream=False, allow_retry=True, temperature=self.temperature, max_tokens=1400,
            )
            if resp2.get("type") == "blocked_by_content_filter":
                yield ("final", resp2.get("message") or "안전정책으로 답변을 생성할 수 없습니다.", law_for_links)
                return

            final_text = resp2["resp"].choices[0].message.content or ""
            yield ("final", final_text, law_for_links)
            return


def _safe_json_dumps(obj: Any) -> str:
    try:
        import json
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"
