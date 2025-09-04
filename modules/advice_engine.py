# modules/advice_engine.py  — REPLACE ALL
from __future__ import annotations
from typing import List, Dict, Any

class AdviceEngine:
    def __init__(self, client, *, model: str, temperature: float = 0.3, tools=None):
        """
        client: OpenAI/Azure OpenAI Chat Completions 호환 객체
        model : 최종 답변용 모델
        tools : (호환용) 전달만 받고 내부에서는 사용하지 않음
        """
        self.client = client
        self.model = model
        self.temperature = temperature
        self._tools_ignored = tools  # keep for compatibility

    # 안전 래퍼
    def scc(self, client, *, messages: List[Dict[str, str]], model: str,
            stream: bool, allow_retry: bool, temperature: float,
            max_tokens: int, tools=None):
        return client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

    def generate(self, messages: List[Dict[str, str]], *, stream: bool = True) -> str:
        """
        앞단 도구(검색/스크랩) 결과가 messages에 이미 들어있다는 가정.
        여기서는 '최종 답변'만 작성한다. (도구 재호출 금지)
        """
        # 2차 호출 전에 공지: 이제 도구 호출 금지, 글만 작성
        messages.append({
            "role": "system",
            "content": "위 도구(검색/스크랩) 결과는 이미 반영됐다. 도구를 다시 호출하지 말고 한국어 최종 답변만 작성하라."
        })

        final_text = ""
        tool_called_in_stream = False

        try:
            if stream:
                # 2차 호출: 글만! (도구 비활성화)
                stream_resp = self.scc(
                    self.client, messages=messages, model=self.model,
                    tools=None, stream=True, allow_retry=True,
                    temperature=self.temperature, max_tokens=1400,
                )
                for ev in stream_resp:
                    try:
                        delta = ev.choices[0].delta
                    except Exception:
                        continue
                    if getattr(delta, "tool_calls", None):
                        tool_called_in_stream = True
                    if getattr(delta, "content", None):
                        final_text += delta.content

                # 본문이 비었거나 스트림에서 tool_calls만 있었으면 논-스트리밍 폴백
                if (not final_text.strip()) or tool_called_in_stream:
                    resp2 = self.scc(
                        self.client, messages=messages, model=self.model,
                        tools=None, stream=False, allow_retry=True,
                        temperature=self.temperature, max_tokens=1400,
                    )
                    final_text = (resp2.choices[0].message.content or "").strip()
            else:
                # 논-스트리밍
                resp2 = self.scc(
                    self.client, messages=messages, model=self.model,
                    tools=None, stream=False, allow_retry=True,
                    temperature=self.temperature, max_tokens=1400,
                )
                final_text = (resp2.choices[0].message.content or "").strip()
        except Exception:
            if not final_text.strip():
                final_text = "모델 스트리밍 중 오류가 발생했습니다. 아래 참고 링크와 함께 핵심만 요약해 드립니다."

        return (final_text or "").strip()
