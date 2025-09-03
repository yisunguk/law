# modules/__init__.py — robust exports
try:
    from .advice_engine import AdviceEngine, pick_mode
    from .legal_modes import Intent, classify_intent, build_sys_for_mode
except Exception:
    from advice_engine import AdviceEngine, pick_mode          # fallback
    from legal_modes import Intent, classify_intent, build_sys_for_mode

# ★ 빠져있던 것들 실제 임포트
try:
    from .router_llm import make_plan_with_llm, ROUTER_SYSTEM   # add
except Exception:
    from router_llm import make_plan_with_llm, ROUTER_SYSTEM    # fallback

try:
    from .plan_executor import execute_plan                     # add
except Exception:
    from plan_executor import execute_plan                      # fallback

__all__ = [
    "AdviceEngine", "pick_mode",
    "Intent", "classify_intent", "build_sys_for_mode",
    "make_plan_with_llm", "ROUTER_SYSTEM", "execute_plan",
]
