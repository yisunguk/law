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

def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET_ARTICLE:
      1) DRF(JSON→HTML) 우선
      2) DRF 실패/차단 or MST 없음 → 한글 조문 딥링크 스크랩 폴백
    """
    action = ((plan or {}).get("action") or "").upper()
    if action != "GET_ARTICLE":
        return {"type":"noop","action":action or "QUICK","message":"execute_plan: GET_ARTICLE 외 액션은 외부 경로에서 처리하세요."}

    law_name  = (plan.get("law_name") or "").strip()
    art_label = (plan.get("article_label") or "").strip()
    mst       = (plan.get("mst") or "").strip()
    jo        = (plan.get("jo") or "").strip()
    efYd_raw  = (plan.get("efYd") or plan.get("eff_date") or "").strip()
    efYd      = "".join(ch for ch in efYd_raw if ch.isdigit())

    if (not jo) and art_label:
        try: jo = _jo_from_label(art_label) or ""
        except Exception: jo = ""

    # (가능하면) MST 보강 → DRF 본문 시도
    if (not mst) and law_name:
        try: mst = find_mst_by_law_name(law_name, efYd=efYd) or ""
        except Exception: mst = ""

    text, link = "", ""

    # 1) DRF(JSON→HTML)
    if mst:
        t1, l1 = fetch_article_block_by_mst(mst, art_label, prefer="JSON", efYd=efYd)
        if not (t1 and t1.strip()):
            t1b, l1b = fetch_article_block_by_mst(mst, art_label, prefer="HTML", efYd=efYd)
            if t1b and t1b.strip():
                t1, l1 = t1b.strip(), l1b
        text, link = (t1 or "").strip(), (l1 or "")

    # 2) 🔴 최후 폴백 — MST가 없거나 DRF가 비었으면 조문 딥링크 스크랩
    if not (text and text.strip()):
        t2, l2 = _scrape_deeplink(law_name, art_label)
        if t2:
            text, link = t2, l2
        elif not link and make_pretty_article_url:
            link = make_pretty_article_url(law_name, art_label)

    return {
        "type":"article","law":law_name,"article":art_label,
        "mst":mst,"jo":jo,"efYd":efYd,
        "text":(text or "").strip(),
        "link":link or "",
    }
