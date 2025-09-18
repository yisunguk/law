# modules/advice_engine.py — COMPLETE, DROP-IN REPLACEMENT
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
import time
from openai import BadRequestError

# 안전 재프레이즈(라우터/소형 모델 사용 + 정규식 폴백)
from .router_llm import rewrite_safe_prompt


class AdviceEngine:
    VERSION = "safe-2025-09-18"
    """
    메인 답변 엔진.
    - 1차 호출이 Azure Responsible AI 콘텐츠 필터(violence 등)에 걸리면
      마지막 user 발화를 '법적 절차 중심'으로 안전 재프레이즈하여 동일 모델로 1회 재시도.
    - 스트리밍/논스트리밍 모두 지원.
    - 일반 오류(네트워크 등)는 지수 백오프로 최대 3회 재시도.
    """

    def __init__(
        self,
        client,
        model: str,
        *,
        temperature: float = 0.3,
        router_model: Optional[str] = None,
        max_tokens: int = 1400,
        tools: Optional[list[dict]] = None,
    ):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.router_model = router_model  # 재프레이즈 시 우선 사용할 라우터 배포명(없으면 env/폴백)
        self.max_tokens = max_tokens
        self.tools = tools  # 최종 답변 단계에선 보통 None

    # --------------------------- public API ---------------------------

    def generate(self, messages: List[Dict[str, Any]], *, stream: bool = True) -> str:
        """
        messages: OpenAI Chat messages 포맷
        stream:   True면 스트리밍으로 받아 누적, 필요 시 논스트리밍 1회 보정
        return:   최종 한국어 답변 텍스트
        """
        # 도구 재호출 금지 안내(최종 답안 전용) 문장 추가
        messages = list(messages)  # 얕은 복사
        messages.append(
            {
                "role": "system",
                "content": "이미 필요한 도구 호출/검색 결과는 반영되었다. "
                           "도구를 다시 호출하지 말고 한국어 최종 답변만 간결하고 정확하게 작성하라.",
            }
        )

        try:
            if stream:
                # 1) 스트리밍 1차 시도
                text, tool_called = self._stream_collect(messages)
                # 비었거나 tool call 신호가 섞였으면 논스트리밍으로 1회 보정
                if (not text.strip()) or tool_called:
                    text = self._once(messages, stream=False)
                return self._postprocess(text)

            # 비스트리밍 경로
            return self._postprocess(self._once(messages, stream=False))

        except BadRequestError as e:
            # Azure 콘텐츠 필터 → 안전 재프레이즈 후 동일 모델로 1회 재시도
            if self._is_content_filter(e):
                safe_msgs = self._rewrite_last_user(messages)
                if stream:
                    text, tool_called = self._stream_collect(safe_msgs)
                    if (not text.strip()) or tool_called:
                        text = self._once(safe_msgs, stream=False)
                    return self._postprocess(text)
                return self._postprocess(self._once(safe_msgs, stream=False))
            # 그 외 BadRequestError는 상위로
            raise

    # ------------------------ internal helpers ------------------------

    def _once(self, messages: List[Dict[str, Any]], *, stream: bool) -> str:
        """
        Chat Completions 1회 호출 (content_filter 제외, 지수 백오프 재시도 포함).
        stream=True면 내부에서 누적한 텍스트를 반환.
        """
        attempts = 3
        delay = 0.6
        last_err: Optional[Exception] = None

        for i in range(attempts):
            try:
                if stream:
                    text, _ = self._stream_collect(messages)
                    return text
                else:
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        **({"tools": self.tools} if self.tools else {}),
                    )
                    return (resp.choices[0].message.content or "").strip()
            except BadRequestError as e:
                # 콘텐츠 필터는 여기서 처리하지 않고 위로 올려 안전 재프레이즈 시도
                if self._is_content_filter(e):
                    raise
                last_err = e
            except Exception as e:
                last_err = e

            if i < attempts - 1:
                time.sleep(delay)
                delay *= 1.7

        if last_err:
            raise last_err
        raise RuntimeError("Unknown error in AdviceEngine._once")

    def _stream_collect(self, messages: List[Dict[str, Any]]) -> Tuple[str, bool]:
        """
        스트리밍 응답 수집.
        return: (누적 텍스트, tool_calls 감지 여부)
        """
        acc: list[str] = []
        tool_called = False
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
            **({"tools": self.tools} if self.tools else {}),
        )
        for ev in stream:
            try:
                delta = ev.choices[0].delta  # ChatCompletionChunk
            except Exception:
                continue
            if getattr(delta, "tool_calls", None):
                tool_called = True
            if getattr(delta, "content", None):
                acc.append(delta.content)
        return ("".join(acc).strip(), tool_called)

    def _rewrite_last_user(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        마지막 user 발화만 안전 프롬프트로 재작성하여 교체.
        """
        out = [dict(m) for m in messages]
        last_idx = -1
        for i, m in enumerate(out):
            if m.get("role") == "user":
                last_idx = i
        if last_idx >= 0:
            original = out[last_idx].get("content", "") or ""
            safe_text = rewrite_safe_prompt(
                self.client,
                original,
                model=self.router_model,  # 있으면 사용
                temperature=0.0,
            )
            out[last_idx]["content"] = safe_text
        return out

    @staticmethod
    def _is_content_filter(err: Exception) -> bool:
        text = f"{getattr(err, 'code', '')} {str(err)}"
        return ("content_filter" in text) or ("ResponsibleAIPolicyViolation" in text)

    @staticmethod
    def _postprocess(text: str) -> str:
        if not text:
            return ""
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text.strip()
