# external_content.py
from __future__ import annotations
import re, requests
from typing import Optional, Tuple
from bs4 import BeautifulSoup

# URL 판별용
_URL_RE = re.compile(r'^https?://', re.I)

def is_url(text: str) -> bool:
    """문자열이 URL인지 확인"""
    return bool(text and _URL_RE.match(text.strip()))

def _clean_text(t: str) -> str:
    t = (t or "").replace('\r\n', '\n').replace('\r', '\n')
    lines = [ln.strip() for ln in t.split('\n')]
    lines = [ln for ln in lines if ln]  # 빈 줄 제거
    return '\n'.join(lines)

def _extract_naver_news(soup: BeautifulSoup) -> Optional[str]:
    """네이버 뉴스 본문 추출 (신/구 버전 호환)"""
    area = soup.select_one("#newsct_article") or soup.select_one("#dic_area")
    return area.get_text(separator="\n", strip=True) if area else None

def _extract_generic(soup: BeautifulSoup) -> str:
    """기타 사이트 본문 추출"""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for sel in ["article", "#content", "main"]:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)

def fetch_article_text(url: str, timeout: int = 10, max_chars: int = 6000) -> Tuple[str, str]:
    """
    외부 기사 URL에서 (제목, 본문 일부) 반환
    실패 시 (에러표시, 메시지) 반환
    """
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = (soup.title.string or "").strip() if soup.title else ""
        text = _extract_naver_news(soup) or _extract_generic(soup)
        text = _clean_text(text)[:max_chars]
        return (title or url), text or "[본문 추출 실패]"
    except Exception as e:
        return "[에러: 기사 요청 실패]", f"{type(e).__name__}: {e}"

def make_url_context(url: str) -> str:
    """프롬프트에 바로 넣기 좋은 블록 생성"""
    title, text = fetch_article_text(url)
    return f"""[외부 링크 원문]
제목: {title}
URL: {url}

본문(발췌):
{text}
"""
