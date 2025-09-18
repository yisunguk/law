# modules/__init__.py  — clean re-exports only
from __future__ import annotations

# Public API (explicit re-exports)
from .advice_engine import AdviceEngine
from .legal_modes import pick_mode, Intent, classify_intent, build_sys_for_mode
from .router_llm import make_plan_with_llm, ROUTER_SYSTEM
from .plan_executor import execute_plan

__all__ = [
    "AdviceEngine",
    "pick_mode", "Intent", "classify_intent", "build_sys_for_mode",
    "make_plan_with_llm", "ROUTER_SYSTEM",
    "execute_plan",
]
