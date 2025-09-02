# === [REPLACE] modules/plan_executor.py : execute_plan 전체 + 스크랩 유틸 추가 ===
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

try:
    from .law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label as _jo_from_label,
        extract_article_block as _slice_article,
        find_mst_by_law_name,
    )
except Exception:
    from law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label as _jo_from_label,
        extract_article_block as _slice_article,
        find_mst_by_law_name,
    )

# 표시/스크랩용 딥링크 생성기
try:
    from .linking import make_pretty_article_url
except Exception:
    try:
        from linking import make_pretty_article_url
    except Exception:
        make_pretty_article_url = None  # type: ignore

def _scrape_deeplink(law_name: str, article_label: str, timeout: float = 6.0) -> Tuple[str, str]:
    """
    한글 조문 딥링크 페이지를 스크랩해 '요청 조문'만 잘라낸다.
    반환: (조문텍스트, 표시링크)
    """
    if not (law_name and article_label and make_pretty_article_url):
        return "", ""
    try:
        import requests
        from bs4 import BeautifulSoup
        url = make_pretty_article_url(law_name, article_label)
        r = requests.get(
            url, timeout=timeout, allow_redirects=True,
            headers={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/xhtml+xml","Accept-Language":"ko-KR,ko;q=0.9"}
        )
        if not (200 <= r.status_code < 400):
            return "", url
        html = r.text or ""
        if any(bad in html[:4000] for bad in ("존재하지 않는 조문","해당 한글주소명을 찾을 수 없습니다","접근이 제한되었습니다")):
            return "", url
        soup = BeautifulSoup(html, "lxml")
        main = (soup.select_one("#contentBody") or soup.select_one("#conBody")
                or soup.select_one("#conScroll") or soup.select_one(".conScroll")
                or soup.select_one("#content") or soup)
        full_text = (main.get_text("\n", strip=True) or "").strip()

        # 조문 블록만 슬라이스 (law_fetch.extract_article_block 사용)
        piece = _slice_article(full_text, article_label) or ""
        if not piece:
            import re
            num = re.sub(r"\D","", article_label)
            m = re.search(rf"(제{num}조(?:의\d+)?[\s\S]*?)(?=\n제\d+조|\n부칙|\Z)", full_text)
            piece = (m.group(1) if m else "").strip()

        return (piece[:4000] if piece else ""), url
    except Exception:
        return "", ""

# === [REPLACE ONLY THIS FUNCTION] modules/plan_executor.py ===
def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET_ARTICLE (딥링크 전용):
      - 한글 조문 딥링크 스크랩만 사용 (OC/DRF 호출 없음)
      - 공공데이터포털 '법령상세링크'가 있으면 표시 링크로 우선 사용
    """
    action = ((plan or {}).get("action") or "").upper()
    if action != "GET_ARTICLE":
        return {
            "type": "noop",
            "action": action or "QUICK",
            "message": "execute_plan: GET_ARTICLE 외 액션은 외부 경로에서 처리하세요."
        }

    law_name  = (plan.get("law_name") or "").strip()
    art_label = (plan.get("article_label") or "").strip()

    # 1) 조문 본문: 한글주소(딥링크) 스크랩
    text, link = _scrape_deeplink(law_name, art_label)

    # 2) 표시 링크 보강: 공공데이터포털 → 실패 시 조문 딥링크
    try:
        from .linking import fetch_drf_law_link_by_name, make_pretty_article_url
    except Exception:
        try:
            from linking import fetch_drf_law_link_by_name, make_pretty_article_url  # type: ignore
        except Exception:
            fetch_drf_law_link_by_name = None  # type: ignore
            make_pretty_article_url = None     # type: ignore

    if not link and fetch_drf_law_link_by_name:
        try:
            api_link = fetch_drf_law_link_by_name(law_name)  # MOLEG_SERVICE_KEY 사용
        except Exception:
            api_link = ""
        if api_link:
            link = api_link

    if not link and make_pretty_article_url:
        try:
            link = make_pretty_article_url(law_name, art_label)
        except Exception:
            link = ""

    return {
        "type": "article",
        "law": law_name,
        "article": art_label,
        "mst": "",   # DRF 제거
        "jo": "",    # DRF 제거
        "efYd": "",  # DRF 제거
        "text": (text or "").strip(),
        "link": link or "",
    }

