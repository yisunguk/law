# modules/__init__.py
from .legal_modes import (
    Intent, SYS_COMMON, SYS_BRIEF, build_sys_for_mode,
    classify_intent, pick_mode
)
from .advice_engine import AdviceEngine
