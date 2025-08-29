# === modules/__init__.py (교체) ===
try:
    from .advice_engine import AdviceEngine, pick_mode
    from .legal_modes import Intent, classify_intent, build_sys_for_mode
except Exception:
    # 패키지 인식이 꼬인 환경 폴백
    from advice_engine import AdviceEngine, pick_mode  # type: ignore
    from legal_modes import Intent, classify_intent, build_sys_for_mode  # type: ignore

__all__ = [
    "AdviceEngine", "pick_mode",
    "Intent", "classify_intent", "build_sys_for_mode",
]
