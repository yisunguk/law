# modules/__init__.py  (수정본)

# 패키지 내부 상대 임포트 우선
try:
    from .advice_engine import AdviceEngine, pick_mode
    from .legal_modes import Intent, classify_intent, build_sys_for_mode
except Exception:
    # 드물게 패키지 인식이 꼬인 환경 폴백
    from advice_engine import AdviceEngine, pick_mode  # type: ignore
    from legal_modes import Intent, classify_intent, build_sys_for_mode  # type: ignore

__all__ = [
    "AdviceEngine", "pick_mode",
    "Intent", "classify_intent", "build_sys_for_mode",
]
