# modules/__init__.py — robust exports (REPLACE)
try:
    from .advice_engine import AdviceEngine, pick_mode
    from .legal_modes import Intent, classify_intent, build_sys_for_mode
except Exception:
    from advice_engine import AdviceEngine, pick_mode          # fallback
    from legal_modes import Intent, classify_intent, build_sys_for_mode

# 🔧 반드시 실제 import 해서 내보냄
try:
    from .router_llm import make_plan_with_llm, ROUTER_SYSTEM
except Exception:
    from router_llm import make_plan_with_llm, ROUTER_SYSTEM

try:
    from .plan_executor import execute_plan
except Exception:
    from plan_executor import execute_plan

__all__ = [
    "AdviceEngine", "pick_mode",
    "Intent", "classify_intent", "build_sys_for_mode",
    "make_plan_with_llm", "ROUTER_SYSTEM", "execute_plan",
]
