# modules/__init__.py (권장 정리)
try:
    from .advice_engine import AdviceEngine, pick_mode
    from .legal_modes import Intent, classify_intent, build_sys_for_mode
except Exception:
    from advice_engine import AdviceEngine, pick_mode  # fallback
    from legal_modes import Intent, classify_intent, build_sys_for_mode  # fallback

# ⬇️ 이 두 줄은 try/except 밖에서 항상 import
from .router_llm import make_plan_with_llm, ROUTER_SYSTEM
from .plan_executor import execute_plan

__all__ = [
    "AdviceEngine", "pick_mode",
    "Intent", "classify_intent", "build_sys_for_mode",
    "make_plan_with_llm", "ROUTER_SYSTEM", "execute_plan",
]
