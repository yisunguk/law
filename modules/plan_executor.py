# modules/plan_executor.py
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# Safe imports (package-relative first)
# ──────────────────────────────────────────────────────────────────────────────
try:
    from .law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label,
        _build_drf_link,  # for SEARCH_LAW items (HTML link)
    )
except ImportError:
    # Fallback when relative import is not available (dev/hot-reload)
    from law_fetch import fetch_article_block_by_mst, jo_from_art_label, _build_drf_link

# 목록 검색 유틸 (법령명 → 후보 리스트)
_find_all_law_data = None
try:
    from .linking import find_all_law_data as _find_all_law_data  # project utility
except Exception:
    try:
        from linking import find_all_law_data as _find_all_law_data
    except Exception:
        _find_all_law_data = None  # graceful fallback

__all__ = ["execute_plan"]

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _pick_first(*vals: Any) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)) and str(v).strip():
            return str(v).strip()
    return ""

def _get_mst_from_item(it: Dict[str, Any]) -> str:
    """다양한 키 스펙을 고려하여 MST(법령일련번호) 추출."""
    return _pick_first(
        it.get("법령일련번호"), it.get("MST"), it.get("LawMST"),
        it.get("id_seq"), it.get("lsiSeq"), it.get("lsi_seq")
    )

def _get_name_from_item(it: Dict[str, Any]) -> str:
    return _pick_first(
        it.get("법령명한글"), it.get("법령명"), it.get("lawNameKor"), it.get("lawName")
    )

def _resolve_mst_by_name(law_name: str) -> str:
    """
    목록 검색으로 정확한 MST를 알아냅니다.
    - 프로젝트의 linking.find_all_law_data(...) 가 있으면 활용
    - 없으면 빈 문자열 반환
    """
    if not law_name or not _find_all_law_data:
        return ""
    try:
        items = _find_all_law_data(law_name, num_rows=5, hint_laws=[law_name]) or []
        # 1) 완전일치 우선
        for it in items:
            if _get_name_from_item(it) == law_name:
                return _get_mst_from_item(it)
        # 2) 첫 번째 항목 폴백
        if items:
            return _get_mst_from_item(items[0])
    except Exception:
        pass
    return ""

def _fetch_article_text_with_retry(
    mst: str,
    article_label: str,
    *,
    efYd: Optional[str] = None
) -> Tuple[str, str]:
    """
    DRF에서 조문 블록을 안정적으로 받아옵니다.
    - JSON 우선, 실패 시 HTML 폴백 (law_fetch.fetch_article_block_by_mst 내부도 폴백 포함)
    - 반환: (text, html_link)
    """
    text, link = fetch_article_block_by_mst(mst, article_label, prefer="JSON", efYd=efYd)
    if not (text and text.strip()):
        text2, link2 = fetch_article_block_by_mst(mst, article_label, prefer="HTML", efYd=efYd)
        if text2 and text2.strip():
            return text2.strip(), link2
    return (text or "").strip(), link

# ──────────────────────────────────────────────────────────────────────────────
# Public: execute_plan
# plan 스키마(예): {
#   "action": "ADVICE" | "GET_ARTICLE" | "SEARCH_LAW",
#   "law_name": "...",
#   "mst": "...",
#   "article_label": "제83조의2",
#   "jo": "008302",
#   "efYd": "20250828",
#   "notes": "",
#   "candidates": [{"law_name":"민법","article_label":"제839조의2","mst":"","jo":""}, ...]
# }
# ──────────────────────────────────────────────────────────────────────────────
from typing import Any, Dict

try:
    # 패키지/단일파일 양쪽에서 동작하도록 이중 import
    from .law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label,
        find_mst_by_law_name,
    )
except Exception:  # pragma: no cover
    from law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label,
        find_mst_by_law_name,
    )


def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM 라우터가 만든 plan을 실행한다.

    하드닝(중요):
      - GET_ARTICLE 액션에서 mst(법령일련번호)가 비어 있으면
        법령명으로 DRF 검색을 돌려 mst를 반드시 보강한다.
      - jo(조문 6자리)가 비어 있으면 article_label로부터 계산한다.
      - DRF 본문 호출은 law_fetch.fetch_article_block_by_mst가 담당
        (JSON 우선, 내부에서 HTML 폴백/평문화/조문 슬라이스 처리)

    반환 형식(성공 시):
      {
        "type": "article",
        "law": <법령명>,
        "article": <조문라벨>,
        "mst": <MST>,
        "jo": <JO>,
        "efYd": <시행일자YYYYMMDD>,
        "text": <조문본문(평문화)>,
        "link": <원문링크>
      }
    """
    action = ((plan or {}).get("action") or "").upper()

    if action == "GET_ARTICLE":
        # 1) 입력 정규화
        law_name: str = (plan.get("law_name") or "").strip()
        article_label: str = (plan.get("article_label") or "").strip()

        mst: str = (plan.get("mst") or "").strip()
        jo: str = (plan.get("jo") or "").strip()
        efYd_raw: str = (plan.get("efYd") or plan.get("eff_date") or "").strip()
        efYd: str = "".join(ch for ch in efYd_raw if ch.isdigit())

        # 2) JO 보강 (예: '제83조' -> '008300')
        if (not jo) and article_label:
            try:
                jo = jo_from_art_label(article_label) or ""
            except Exception:
                jo = ""

        # 3) MST 보강 (법령명으로 DRF 검색 → 정확 일치 우선)
        if (not mst) and law_name:
            try:
                mst = find_mst_by_law_name(law_name, efYd=efYd) or ""
            except Exception:
                mst = ""

        # 4) MST 없으면 실패 반환
        if not mst:
            return {
                "type": "article",
                "law": law_name,
                "article": article_label,
                "mst": "",
                "jo": jo,
                "efYd": efYd,
                "text": "",
                "link": "",
                "error": "MST(법령일련번호) 해석 실패",
            }

        # 5) DRF 본문 호출 (JSON 우선, 내부에서 폴백/슬라이스 처리)
        text, link = fetch_article_block_by_mst(mst, article_label, prefer="JSON", efYd=efYd)

        return {
            "type": "article",
            "law": law_name,
            "article": article_label,
            "mst": mst,
            "jo": jo,
            "efYd": efYd,
            "text": (text or "").strip(),
            "link": (link or ""),
        }

    # 알 수 없는 액션은 그대로 에코(또는 필요 시 확장)
    return dict(plan or {})
