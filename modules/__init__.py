# modules/__init__.py (robust)
# Public API re-exporter for the app to use as: from modules import ...
# - Tries relative imports first (package layout), then top-level fallbacks.

# ---- legal_modes ----
try:
    from .legal_modes import (
        Intent,
        SYS_COMMON,
        SYS_BRIEF,
        MODE_SYS,
        build_sys_for_mode,
        tidy_memo,
        classify_intent,
        route_intent,
    )
except Exception:  # fallback: flat layout
    from legal_modes import (
        Intent,
        SYS_COMMON,
        SYS_BRIEF,
        MODE_SYS,
        build_sys_for_mode,
        tidy_memo,
        classify_intent,
        route_intent,
    )

# ---- advice_engine ----
try:
    from .advice_engine import AdviceEngine, pick_mode
except Exception:  # fallback: flat layout
    from advice_engine import AdviceEngine, pick_mode

__all__ = [
    "Intent",
    "SYS_COMMON",
    "SYS_BRIEF",
    "MODE_SYS",
    "build_sys_for_mode",
    "tidy_memo",
    "classify_intent",
    "route_intent",
    "AdviceEngine",
    "pick_mode",
]
