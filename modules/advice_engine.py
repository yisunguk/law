# modules/advice_engine.py — COMPLETE
from __future__ import annotations
from typing import List, Dict, Any

class AdviceEngine:
    def __init__(self, client, *, model: str, temperature: float = 0.3, tools=None):
        self.client = client
        self.model = model
        self.temperature = temperature
        self._tools_ignored = tools

    # advice_engine.py
    def scc(
        self,
        client,
        *,
        messages,
        model,
        stream,
        allow_retry,
        temperature,
        max_tokens,
        tools=None,
    ):
        kwargs = {}
        if tools:  # <-- None이면 보내지 않음
            kwargs["tools"] = tools

        return client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
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
        # advice_engine.py — [REPLACE] 예외 처리: 미니 모델 1회 재시도 → 최소 가이드

# (기존 try: ... except Exception: ~ return final_text 사이를 아래 블록으로 교체하세요)
        except Exception:
            # 1차: 더 가벼운 모델로 1회 재시도
            try:
                resp = self.scc(
                    self.client,
                    messages=messages,
                    model="gpt-4o-mini",   # ← 경량 모델로 폴백
                    tools=None,
                    stream=False,
                    allow_retry=False,
                    temperature=0.2,
                    max_tokens=900,
                )
                final_text = (resp.choices[0].message.content or "").strip()
            except Exception:
                # 2차: 최소 안내문(에러 문구 대신 실무 가이드 제시)
                final_text = (
                    "지금은 서버 연결이 원활하지 않아 간단 요약만 안내드립니다.\n\n"
                    "1) 사안의 핵심 쟁점을 먼저 정리하시고,\n"
                    "2) 관련 조문(민법·특별법)과 최근 판례를 함께 검토하세요.\n"
                    "3) 증빙자료(계약서·통지내역·사진 등)를 확보한 뒤 절차(내용증명→조정/소송)를 진행하십시오.\n"
                    "\n※ 아래 ‘적용 법령/근거’ 링크를 참고해 정확한 조문을 확인해 주세요."
                )

        return final_text or "죄송합니다. 답변을 생성하지 못했습니다."

