# modules/__init__.py — COMPLETE
import importlib

__all__ = [
    "AdviceEngine",
    "pick_mode", "Intent", "classify_intent", "build_sys_for_mode",
    "make_plan_with_llm", "ROUTER_SYSTEM", "execute_plan",
]

def __getattr__(name: str):
    # 모델/생성기
    if name == "AdviceEngine":
        return getattr(importlib.import_module(".advice_engine", __name__), name)

    # 모드/의도 분류/시스템 프롬프트
    if name in ("pick_mode", "Intent", "classify_intent", "build_sys_for_mode"):
        return getattr(importlib.import_module(".legal_modes", __name__), name)

    # 라우터(플랜 생성)
    if name in ("make_plan_with_llm", "ROUTER_SYSTEM"):
        return getattr(importlib.import_module(".router_llm", __name__), name)

    # 플랜 실행기
    if name == "execute_plan":
        return getattr(importlib.import_module(".plan_executor", __name__), name)

    raise AttributeError(name)
