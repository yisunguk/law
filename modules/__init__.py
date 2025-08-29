# modules/__init__.py  ← 전체 교체

# 패키지 내부 상대 임포트
try:
    from .legal_modes import (
        AdviceEngine,
        Intent,
        classify_intent,
        pick_mode,
        build_sys_for_mode,
    )
except ImportError:  # 실행 환경에 따라 폴백
    from legal_modes import (  # type: ignore
        AdviceEngine,
        Intent,
        classify_intent,
        pick_mode,
        build_sys_for_mode,
    )

__all__ = [
    "AdviceEngine",
    "Intent",
    "classify_intent",
    "pick_mode",
    "build_sys_for_mode",
]
