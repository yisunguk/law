from .legal_modes import (
    Intent, SYS_COMMON, SYS_BRIEF, MODE_SYS,
    build_sys_for_mode, tidy_memo, classify_intent, route_intent,
)

try:
    from .advice_engine import AdviceEngine, pick_mode
except Exception:
    from .engine import AdviceEngine, pick_mode  # fallback

__all__ = [
    "Intent","SYS_COMMON","SYS_BRIEF","MODE_SYS",
    "build_sys_for_mode","tidy_memo","classify_intent","route_intent",
    "AdviceEngine","pick_mode",
]
