# errors.py
from typing import Optional, Dict, Any

class ContentFilterHit(Exception):
    """Azure OpenAI content filter로 차단된 경우."""
    def __init__(self, message: str, categories: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.categories = categories or {}

def is_content_filter_error(e: Exception) -> Optional[Dict[str, Any]]:
    """
    Azure OpenAI의 content_filter 400 에러인지 감지.
    SDK/HTTP 클라이언트 종류에 따라 구조가 조금 달라서 보수적으로 탐색합니다.
    반환값: 카테고리 딕셔너리(감지 시) 또는 None
    """
    try:
        # OpenAI SDK 계열: e.response.status_code 존재 가능
        status = getattr(getattr(e, "response", None), "status_code", None) \
                 or getattr(e, "status_code", None)

        # e.response.json() 또는 e.error/dict 또는 e.args[0]에 정보가 있을 수 있음
        data = getattr(getattr(e, "response", None), "json", lambda: {})() \
               if hasattr(getattr(e, "response", None), "json") else None
        if not data and hasattr(e, "error"):
            data = getattr(e, "error")
        if not data and getattr(e, "args", None):
            data = e.args[0] if isinstance(e.args[0], dict) else {}

        if status == 400 and isinstance(data, dict):
            code = (data.get("code")
                    or data.get("error", {}).get("code")
                    or data.get("innererror", {}).get("code"))
            if code and "content_filter" in str(code).lower():
                return data.get("innererror", {}).get("content_filter_result") or {}
    except Exception:
        pass
    return None
