# modules/plan_executor.py
from __future__ import annotations
from typing import Dict, Any, Optional

# 패키지 상대 임포트 (modules 패키지 내부에서 안전)
try:
    from .law_fetch import fetch_article_block_by_mst, jo_from_art_label
except ImportError:
    # 스트림릿 핫리로드/경로 이슈 대비
    from law_fetch import fetch_article_block_by_mst, jo_from_art_label

__all__ = ["execute_plan"]  # 내보낼 심볼 명시

def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    act = (plan.get("action") or "").upper()

    if act == "GET_ARTICLE":
        mst: str = (plan.get("mst") or "").strip()
        art: str = (plan.get("article_label") or "").strip()
        jo:  str = (plan.get("jo") or "").strip()
        efYd: Optional[str] = (plan.get("efYd") or None)

        # jo가 비어 있으면 백업 계산(하위호환)
        if (not jo) and art:
            jo = jo_from_art_label(art) or ""

        # DRF 호출: JSON 우선, 실패 시 HTML 폴백은 내부에서 처리됨
        text, html_link = fetch_article_block_by_mst(
            mst, art, prefer="JSON", efYd=efYd
        )
        return {
            "type": "article",
            "text": (text or "").strip(),
            "link": html_link,
            "mst": mst,
            "jo": jo,
            "efYd": efYd,
        }

    if act == "SEARCH_LAW":
        # 목록 검색 연결 지점 (프로젝트의 검색 함수에 붙이세요)
        return {"type": "search", "items": [], "msg": "connect list-search here"}

    return {"type": "none", "msg": "no-op"}
