# modules/plan_executor.py
from __future__ import annotations
from typing import Dict, Any, Tuple
import re, logging

logger = logging.getLogger("lawbot.plan_executor")

# ── helpers ─────────────────────────────────────────────────────────

def _make_pretty_article_url(law: str, art: str) -> str:
    """가능하면 linking 모듈을 쓰고, 없으면 한글 경로로 직접 구성."""
    try:
        from .linking import make_pretty_article_url  # type: ignore
        return make_pretty_article_url(law, art)
    except Exception:
        try:
            from linking import make_pretty_article_url  # type: ignore
            return make_pretty_article_url(law, art)
        except Exception:
            return f"https://www.law.go.kr/법령/{law}/{art}"

# ✅ [REPLACE] modules/plan_executor.py : _slice_article
def _slice_article(full_text: str, article_label: str) -> str:
    """
    페이지 전체 텍스트에서 해당 조문 블록만 정밀 추출.
    - '제83조' 또는 '제83조의2' 모두 지원
    """
    import re
    label = (article_label or "").strip()
    if not (full_text and label):
        return ""

    # 1) 표준형 라벨 파싱
    m = re.search(r'제\s*(\d{1,4})\s*조(?:\s*의\s*(\d{1,3}))?', label)
    if m:
        main = int(m.group(1))
        sub  = m.group(2)
        if sub:
            # 제83조의2 형태
            pat = rf"(?m)^(제\s*{main}\s*조\s*의\s*{int(sub)}\b[\s\S]*?)(?=^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\b|\n부칙|\Z)"
        else:
            # 제83조 (단, 뒤의 '의' 조문까지 잡아먹지 않도록 (?!\s*의))
            pat = rf"(?m)^(제\s*{main}\s*조(?!\s*의)\b[\s\S]*?)(?=^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\b|\n부칙|\Z)"
        m2 = re.search(pat, full_text)
        if m2:
            return m2.group(1).strip()

    # 2) 라벨 그대로 1차 시도 (비표준 입력 대비)
    m3 = re.search(rf"(?m)^({re.escape(label)}[^\n]*\n(?:.+\n)*?)(?=^\s*제\d+조|\n부칙|\Z)", full_text)
    return (m3.group(1).strip() if m3 else "")


def _scrape_deeplink(law: str, art: str, timeout: float = 6.0) -> Tuple[str, str]:
    """법제처 한글 주소(딥링크) 페이지를 스크랩해서 해당 조문만 추출."""
    url = _make_pretty_article_url(law, art)
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(
            url, timeout=timeout, allow_redirects=True,
            headers={
                "User-Agent":"Mozilla/5.0",
                "Accept":"text/html,application/xhtml+xml",
                "Accept-Language":"ko-KR,ko;q=0.9",
            },
        )
        html = r.text or ""
        soup = BeautifulSoup(html, "lxml")
        main = (soup.select_one("#contentBody") or soup.select_one("#conBody")
                or soup.select_one("#conScroll") or soup.select_one(".conScroll")
                or soup.select_one("#content") or soup)
        full_text = (main.get_text("\n", strip=True) or "").strip()
        piece = _slice_article(full_text, art)
        return (piece[:4000] if piece else ""), url
    except Exception:
        # 네트워크/파서 문제 시에도 링크만이라도 반환
        return "", url

# ── public API ──────────────────────────────────────────────────────

def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    최소 구현: GET_ARTICLE만 처리.
    - 한글 조문 딥링크를 스크랩해서 본문을 돌려줍니다.
    """
    action = ((plan or {}).get("action") or "").upper()
    if action != "GET_ARTICLE":
        return {
            "type": "noop",
            "action": action or "QUICK",
            "message": "only GET_ARTICLE supported in plan_executor",
        }

    law = (plan.get("law_name") or "").strip()
    art = (plan.get("article_label") or "").strip()

    body, url = _scrape_deeplink(law, art)
    return {
        "type": "article",
        "law": law,
        "article_label": art,
        "title": "",
        "body_text": body,
        "clauses": [],
        "source_url": url,
    }

__all__ = ["execute_plan"]
