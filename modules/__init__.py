# modules/__init__.py — lazy exports (REPLACE ALL)
import importlib

__all__ = [
    "AdviceEngine", "pick_mode",
    "Intent", "classify_intent", "build_sys_for_mode",
    "make_plan_with_llm", "ROUTER_SYSTEM", "execute_plan",
]

def __getattr__(name: str):
    if name in ("AdviceEngine", "pick_mode"):
        mod = importlib.import_module(".advice_engine", __name__)
        return getattr(mod, name)
    if name in ("Intent", "classify_intent", "build_sys_for_mode"):
        mod = importlib.import_module(".legal_modes", __name__)
        return getattr(mod, name)
    if name in ("make_plan_with_llm", "ROUTER_SYSTEM"):
        mod = importlib.import_module(".router_llm", __name__)
        return getattr(mod, name)
    if name == "execute_plan":
        mod = importlib.import_module(".plan_executor", __name__)
        return getattr(mod, name)
    raise AttributeError(name)
