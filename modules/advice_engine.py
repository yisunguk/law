# modules/advice_engine.py — COMPLETE
from __future__ import annotations
from typing import List, Dict, Any

class AdviceEngine:
    def __init__(self, client, *, model: str, temperature: float = 0.3, tools=None):
        self.client = client
        self.model = model
        self.temperature = temperature
        self._tools_ignored = tools

    def scc(
        self,
        client,
        *,
        messages: List[Dict[str, str]],
        model: str,
        stream: bool,
        allow_retry: bool,
        temperature: float,
        max_tokens: int,
        tools=None,
    ):
        # 단순 래퍼: 안전가드(safe_chat_completion)를 쓰지 않고
        # 클린하게 OpenAI API만 호출 (상위에서 이미 필터링/가드 적용한 상태 가정)
        return client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

    def generate(self, messages: List[Dict[str, str]], *, stream: bool = True) -> str:
        # 도구는 이미 실행/반영되었다는 전제를 모델에 명시
        messages.append({
            "role": "system",
            "content": "위 도구(검색/스크랩) 결과는 이미 반영됐다. 도구를 다시 호출하지 말고 한국어 최종 답변만 작성하라."
        })

        final_text, tool_called = "", False
        try:
            if stream:
                evs = self.scc(
                    self.client,
                    messages=messages,
                    model=self.model,
                    tools=None,
                    stream=True,
                    allow_retry=True,
                    temperature=self.temperature,
                    max_tokens=1400,
                )
                for ev in evs:
                    try:
                        delta = ev.choices[0].delta
                    except Exception:
                        continue
                    if getattr(delta, "tool_calls", None):
                        tool_called = True
                    if getattr(delta, "content", None):
                        final_text += delta.content

                # 스트리밍 중 텍스트가 비었거나 tool 호출이 섞이면 비스트리밍으로 한 번 더
                if (not final_text.strip()) or tool_called:
                    resp2 = self.scc(
                        self.client,
                        messages=messages,
                        model=self.model,
                        tools=None,
                        stream=False,
                        allow_retry=True,
                        temperature=self.temperature,
                        max_tokens=1400,
                    )
                    final_text = (resp2.choices[0].message.content or "").strip()
            else:
                resp = self.scc(
                    self.client,
                    messages=messages,
                    model=self.model,
                    tools=None,
                    stream=False,
                    allow_retry=True,
                    temperature=self.temperature,
                    max_tokens=1400,
                )
                final_text = (resp.choices[0].message.content or "").strip()
        except Exception:
            final_text = "죄송합니다. 답변 작성 중 오류가 발생했습니다."

        return final_text or "죄송합니다. 답변을 생성하지 못했습니다."
