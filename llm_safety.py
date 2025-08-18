# llm_safety.py
from typing import Any, Dict, List, Union
from errors import is_content_filter_error

USER_FRIENDLY_GUIDE = (
    "현재 질문은 안전 관련 민감 표현으로 인식되어 자동 보호 장치에 의해 응답이 제한되었습니다. "
    "표현을 중립적으로 바꿔 다시 시도해 보세요.\n\n"
    "예) '…다쳤어 보상 받을 수 있나?' → "
    "'대중교통 이용 중 발생한 사고에 대한 일반적인 법적 절차와 보상 청구 방법을 알려줘.'"
)

def safe_chat_completion(
    client: Any,
    *,
    messages: List[Dict[str, str]],
    model: str,
    stream: bool = False,
    allow_retry: bool = True,
    **kwargs
) -> Dict[str, Union[str, Any, Dict]]:
    """
    Azure content_filter(400)을 포착해 사용자 친화 메시지를 반환.
    ✅ 비스트리밍: OpenAI 원 응답 객체(resp)를 그대로 반환 -> {"type":"ok","resp": resp}
    ✅ 스트리밍: stream generator 그대로 반환 -> {"type":"stream","stream": stream}
    ✅ 차단: {"type":"blocked_by_content_filter","message": USER_FRIENDLY_GUIDE}
    나머지 파라미터는 **kwargs 로 그대로 OpenAI에 전달합니다.
    """
    try:
        if stream:
            s = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                **kwargs,
            )
            return {"type": "stream", "stream": s}

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
            **kwargs,
        )
        return {"type": "ok", "resp": resp}

    except Exception as e:
        categories = is_content_filter_error(e)
        if categories is not None:
            # 1) 사용자 안내
            friendly = {
                "type": "blocked_by_content_filter",
                "message": USER_FRIENDLY_GUIDE,
                "categories": categories,  # 로깅용
            }
            # 2) 선택적 재시도(완화 system 추가)
            if allow_retry:
                try:
                    retry_msgs = _make_softened_messages(messages)
                    if stream:
                        s = client.chat.completions.create(
                            model=model,
                            messages=retry_msgs,
                            stream=True,
                            **kwargs,
                        )
                        return {"type": "stream", "stream": s}
                    else:
                        resp = client.chat.completions.create(
                            model=model,
                            messages=retry_msgs,
                            stream=False,
                            **kwargs,
                        )
                        return {"type": "ok", "resp": resp}
                except Exception:
                    pass
            return friendly
        # content_filter 외 에러는 상위로
        raise

def _make_softened_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    softened_system = {
        "role": "system",
        "content": (
            "민감 표현을 중립적·일반적 법률 정보 요청으로 재해석해 답하세요. "
            "개별 사건의 보장을 단정하지 말고 절차·요건·예시 중심으로 설명하세요. "
            "위험·폭력·자해·선정적 표현은 사용하지 마세요."
        ),
    }
    return [softened_system, *messages]

def extract_text(resp: Any) -> str:
    """편의 헬퍼: OpenAI 비스트리밍 응답에서 본문 텍스트만 꺼냄"""
    try:
        return resp.choices[0].message.content or ""
    except Exception:
        return ""
