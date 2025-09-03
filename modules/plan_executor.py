# modules/plan_executor.py — 딥링크 스크랩러 (REPLACE)
from __future__ import annotations
from typing import Dict, Any, Tuple
import re, logging, requests

logger = logging.getLogger("lawbot.plan_executor")

def _make_pretty_article_url(law: str, art: str) -> str:
    try:
        from .linking import make_pretty_article_url
        return make_pretty_article_url(law, art)
    except Exception:
        try:
            from linking import make_pretty_article_url
            return make_pretty_article_url(law, art)
        except Exception:
            return f"https://www.law.go.kr/법령/{law}/{art}"

_SLICE_NEXT = re.compile(r"\n(?=제\d{1,4}조(의\d{1,3})?|\s*부칙|\Z)")

def _slice_article(full_text: str, article_label: str) -> str:
    label = (article_label or "").strip()
    if not (full_text and label): return ""
    m = re.search(rf"({re.escape(label)}[^\n]*\n(?:.+\n)*?){_SLICE_NEXT.pattern}", full_text)
    if m: return m.group(1).strip()
    num = re.sub(r"\D", "", label)
    if num:
        m = re.search(rf"(제{num}조(?:의\d+)?[\s\S]*?){_SLICE_NEXT.pattern}", full_text)
        return (m.group(1) if m else "").strip()
    return ""

def _html_to_text(html: str) -> str:
    # bs4가 없으면 태그 제거 폴백
    try:
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(html or "", "lxml")
        except Exception:
            soup = BeautifulSoup(html or "", "html.parser")
        main = (soup.select_one("#contentBody") or soup.select_one("#conBody")
                or soup.select_one("#conScroll") or soup.select_one(".conScroll")
                or soup.select_one("#content") or soup)
        return (main.get_text("\n", strip=True) or "").strip()
    except Exception:
        txt = re.sub(r"<script[\s\S]*?</script>", "", html or "", flags=re.I)
        txt = re.sub(r"<style[\s\S]*?</style>", "", txt, flags=re.I)
        txt = re.sub(r"<[^>]+>", "", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt)
        return txt.strip()

def _scrape_deeplink(law: str, art: str, timeout: float = 7.0) -> Tuple[str, str]:
    url = _make_pretty_article_url(law, art)
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
        full_text = _html_to_text(r.text or "")
        piece = _slice_article(full_text, art)
        return (piece[:4000] if piece else ""), url
    except Exception:
        return "", url  # 최소 링크는 보장

def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    action = ((plan or {}).get("action") or "").upper()
    if action != "GET_ARTICLE":
        return {"type":"noop","action":action or "QUICK","message":"only GET_ARTICLE supported"}
    law = (plan.get("law_name") or "").strip()
    art = (plan.get("article_label") or "").strip()
    body, url = _scrape_deeplink(law, art)
    return {"type":"article","law":law,"article_label":art,"title":"",
            "body_text":body,"clauses":[],"source_url":url}

__all__ = ["execute_plan"]
