# modules/__init__.py (권장 정리)
try:
    from .advice_engine import AdviceEngine, pick_mode
    from .legal_modes import Intent, classify_intent, build_sys_for_mode
except Exception:
    from advice_engine import AdviceEngine, pick_mode  # fallback
    from legal_modes import Intent, classify_intent, build_sys_for_mode  # fallback

__all__ = [
    "AdviceEngine", "pick_mode",
    "Intent", "classify_intent", "build_sys_for_mode",
    "make_plan_with_llm", "ROUTER_SYSTEM", "execute_plan",
]
