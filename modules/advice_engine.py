# --- [REPLACE in modules/advice_engine.py] ---------------------------------
# (툴 실행 결과를 messages에 append한 직후, 최종 답변 생성부 전체 교체)

# 2차 호출 전에 모델에 못박기: "이제 도구 호출 금지, 글만 써라"
messages.append({
    "role": "system",
    "content": "위 도구(검색/스크랩) 결과는 이미 반영됐다. 도구를 다시 호출하지 말고 한국어 최종 답변만 작성하라."
})

final_text = ""
resp2 = None                     # ← 초기화 (참조 오류 방지)
tool_called_in_stream = False    # ← 스트리밍 중 도구 호출 감지

try:
    if stream:
        # 2차 호출: 글만! (tools=None)
        stream_resp = self.scc(
            self.client,
            messages=messages,
            model=self.model,
            tools=None,                   # ★ 도구 금지
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
            # 도구 호출 신호가 나오면 폴백 대상으로 마킹
            if getattr(delta, "tool_calls", None):
                tool_called_in_stream = True
            # 본문 chunk 수집
            if getattr(delta, "content", None):
                final_text += delta.content

        # 스트림이 끝났는데 본문이 비어있거나(tool_calls만 있었거나) 너무 짧으면 논-스트리밍 폴백
        if (not final_text.strip()) or tool_called_in_stream:
            resp2 = self.scc(
                self.client,
                messages=messages,
                model=self.model,
                tools=None,               # ★ 도구 금지
                stream=False,
                allow_retry=True,
                temperature=self.temperature,
                max_tokens=1400,
            )
            final_text = (resp2.choices[0].message.content or "").strip()

    else:
        # 논-스트리밍 모드
        resp2 = self.scc(
            self.client,
            messages=messages,
            model=self.model,
            tools=None,                   # ★ 도구 금지
            stream=False,
            allow_retry=True,
            temperature=self.temperature,
            max_tokens=1400,
        )
        final_text = (resp2.choices[0].message.content or "").strip()

except Exception as e:
    # 안전 폴백: 모델 오류 시에도 텍스트가 비지 않게 함
    final_text = (final_text or "").strip()
    if not final_text:
        final_text = "모델 스트리밍 중 오류가 발생했습니다. 아래 참고 링크와 함께 핵심만 요약해 드립니다."

# 이후 final_text를 그대로 반환/표시
# ---------------------------------------------------------------------------
