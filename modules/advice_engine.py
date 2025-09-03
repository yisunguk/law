# ─────────────────────────────────────────────────────────────
# 2차 호출(최종 답변) 생성부 — 드롭인 교체
#  - 도구 재호출 금지(tools=None)
#  - resp2 참조 가드
#  - 스트리밍 중 tool_calls 감지 시 논-스트리밍 폴백
# ─────────────────────────────────────────────────────────────
# 2차 호출 전에 모델에 공지: 이제는 글만 작성하라(도구 금지)
messages.append({
    "role": "system",
    "content": "위 도구(검색/스크랩) 결과는 이미 반영됐다. 도구를 다시 호출하지 말고 한국어 최종 답변만 작성하라."
})

final_text = ""
resp2 = None
tool_called_in_stream = False

try:
    if stream:
        # 2차 호출: 글만! (도구 비활성화)
        stream_resp = self.scc(
            self.client,
            messages=messages,
            model=self.model,
            tools=None,                  # ★ 핵심: 도구 금지
            stream=True,
            allow_retry=True,
            temperature=self.temperature,
            max_tokens=1400,
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

        # 본문이 비었거나(tool_calls만 있었던 경우 포함) 폴백
        if (not final_text.strip()) or tool_called_in_stream:
            resp2 = self.scc(
                self.client,
                messages=messages,
                model=self.model,
                tools=None,              # ★ 도구 금지
                stream=False,
                allow_retry=True,
                temperature=self.temperature,
                max_tokens=1400,
            )
            final_text = (resp2.choices[0].message.content or "").strip()

    else:
        # 논-스트리밍 2차 호출 (도구 금지)
        resp2 = self.scc(
            self.client,
            messages=messages,
            model=self.model,
            tools=None,                  # ★ 도구 금지
            stream=False,
            allow_retry=True,
            temperature=self.temperature,
            max_tokens=1400,
        )
        final_text = (resp2.choices[0].message.content or "").strip()

except Exception:
    if not final_text.strip():
        final_text = "모델 스트리밍 중 오류가 발생했습니다. 아래 참고 링크와 함께 핵심만 요약해 드립니다."

# ▼ 이후 코드에서 final_text를 그대로 반환/표시
# ─────────────────────────────────────────────────────────────
