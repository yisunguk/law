# modules/__init__.py — FIX
import importlib

__all__ = [
    "AdviceEngine",
    "pick_mode", "Intent", "classify_intent", "build_sys_for_mode",
    "make_plan_with_llm", "ROUTER_SYSTEM", "execute_plan",
]

def __getattr__(name: str):
    if name == "AdviceEngine":
        return getattr(importlib.import_module(".advice_engine", __name__), name)
    if name in ("pick_mode", "Intent", "classify_intent", "build_sys_for_mode"):
        return getattr(importlib.import_module(".legal_modes", __name__), name)
    if name in ("make_plan_with_llm", "ROUTER_SYSTEM"):
        return getattr(importlib.import_module(".router_llm", __name__), name)
    if name == "execute_plan":
        return getattr(importlib.import_module(".plan_executor", __name__), name)
    raise AttributeError(name)
