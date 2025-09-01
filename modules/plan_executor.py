# === [REPLACE] modules/plan_executor.py : execute_plan() 전체 교체 블록 ===
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# Safe imports (package-relative first)
# ──────────────────────────────────────────────────────────────────────────────
try:
    from .law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label,
        find_mst_by_law_name,
    )
except ImportError:  # dev/hot-reload fallback
    from law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label,
        find_mst_by_law_name,
    )

# 목록 검색 유틸 (법령명 → 후보 리스트) — 선택적
_find_all_law_data = None
try:
    from .linking import find_all_law_data as _find_all_law_data  # project utility
except Exception:
    try:
        from linking import find_all_law_data as _find_all_law_data
    except Exception:
        _find_all_law_data = None  # graceful fallback

# ──────────────────────────────────────────────────────────────────────────────
# [NEW] 최후 폴백(스크랩)용 의존성: 실패해도 앱은 계속 동작하도록 안전하게 로드
# ──────────────────────────────────────────────────────────────────────────────
try:
    from .linking import make_pretty_article_url  # 한글 조문 딥링크 생성기
except Exception:
    try:
        from linking import make_pretty_article_url
    except Exception:
        make_pretty_article_url = None  # type: ignore

try:
    import requests  # 최후 폴백 시 페이지 요청
except Exception:    # requests 미설치 환경에서도 죽지 않게
    requests = None  # type: ignore

try:
    from bs4 import BeautifulSoup  # HTML → 텍스트 추출
except Exception:
    BeautifulSoup = None  # type: ignore

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
    프로젝트 유틸이 있으면 목록 검색으로 MST를 보강.
    없으면 빈 문자열 반환.
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

# ──────────────────────────────────────────────────────────────────────────────
# Public: execute_plan
# plan 예:
# {
#   "action": "ADVICE" | "GET_ARTICLE" | "SEARCH_LAW",
#   "law_name": "민법",
#   "mst": "",
#   "article_label": "제839조의2",
#   "jo": "008302",
#   "efYd": "20250708",
#   "notes": "",
#   "candidates": [...]
# }
# ──────────────────────────────────────────────────────────────────────────────
def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM 라우터가 만든 plan을 실행한다.

    하드닝:
      - GET_ARTICLE에서 mst가 비면 법령명으로 DRF 검색하여 mst를 보강(find_mst_by_law_name)
      - jo가 비면 article_label로부터 계산(jo_from_art_label)
      - DRF 본문은 JSON 우선, 필요시 HTML 폴백(fetch_article_block_by_mst 내부에 폴백 포함)
      - 🔴 최후 폴백: DRF 본문이 완전히 비면 '법령 한글주소' 조문 페이지를 스크랩(딥링크 우선)
    """
    action = ((plan or {}).get("action") or "").upper()

    if action != "GET_ARTICLE":
        # 이 구현은 GET_ARTICLE 전용. 다른 액션은 기존 경로에서 처리하거나
        # 간단한 메시지만 반환합니다.
        return {
            "type": "noop",
            "action": action or "QUICK",
            "message": "execute_plan: GET_ARTICLE 외 액션은 외부 경로에서 처리하세요.",
        }

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

    # 3) MST 보강 (우선: DRF lawSearch → 보조: 프로젝트 목록검색)
    if (not mst) and law_name:
        try:
            mst = find_mst_by_law_name(law_name, efYd=efYd) or ""  # DRF 직접
        except Exception:
            mst = ""
        if not mst:
            mst = _resolve_mst_by_name(law_name) or ""

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

    # 5) DRF 본문 호출 (JSON 우선, 내부에서 HTML 폴백/슬라이스 처리)
    text, link = fetch_article_block_by_mst(mst, article_label, prefer="JSON", efYd=efYd)
    if not (text and text.strip()):
        text2, link2 = fetch_article_block_by_mst(mst, article_label, prefer="HTML", efYd=efYd)
        if text2 and text2.strip():
            text, link = text2.strip(), link2

    # 6) 🔴 최후 폴백: DRF가 모두 실패한 경우, 한글주소 조문 페이지 스크랩
    if not (text and text.strip()):
        if make_pretty_article_url and requests and BeautifulSoup and law_name and article_label:
            try:
                url = make_pretty_article_url(law_name, article_label)
                r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
                if 200 <= r.status_code < 400 and "존재하지 않는 조문" not in (r.text or ""):
                    soup = BeautifulSoup(r.text, "lxml")
                    # 사이트 구조 변화에 대비해 여러 후보를 순차 탐색
                    main = (
                        soup.select_one("#contentBody")
                        or soup.select_one("#conBody")
                        or soup.select_one("#conScroll")
                        or soup.select_one(".conScroll")
                        or soup.select_one("#content")
                        or soup
                    )
                    scraped = (main.get_text("\n", strip=True) or "").strip()
                    if scraped:
                        text = scraped[:4000]
                        link = url
            except Exception:
                # 스크랩 실패는 조용히 무시 (최종적으로 빈 본문 반환)
                pass

    # 7) 결과 반환
    return {
        "type": "article",
        "law": law_name,
        "article": article_label,
        "mst": mst,
        "jo": jo,
        "efYd": efYd,
        "text": (text or "").strip(),
        "link": link or "",
    }
