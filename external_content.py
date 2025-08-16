# external_content.py
from __future__ import annotations

import re
import requests
from typing import Tuple
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# -------------------------------
# URL 판별/추출 유틸
# -------------------------------
_URL_RE = re.compile(r'^https?://', re.I)
_FIRST_URL_RE = re.compile(r'(https?://\S+)', re.I)

def is_url(text: str) -> bool:
    """문자열 전체가 URL 형태인지 검사"""
    return bool(text and _URL_RE.match(text.strip()))

def extract_first_url(text: str) -> str | None:
    """문장 속에서 첫 번째 URL만 추출"""
    m = _FIRST_URL_RE.search(text or "")
    return m.group(1) if m else None

def extract_all_urls(text: str, limit: int = 3) -> list[str]:
    """문장 속 모든 URL을 추출(최대 limit개)"""
    urls = _FIRST_URL_RE.findall(text or "")
    return urls[:limit]

# -------------------------------
# 보안: 로컬/사설망 차단 (간단 SSRF 가드)
# -------------------------------
_PRIVATE_PREFIXES = ("127.", "10.", "192.168.", "169.254.")
def _is_private_host(host: str) -> bool:
    if not host:
        return True
    host_l = host.lower()
    return (
        host_l == "localhost"
        or host_l.startswith(_PRIVATE_PREFIXES)
    )

# -------------------------------
# 본문 정리/추출
# -------------------------------
def _clean_text(t: str) -> str:
    t = (t or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in t.split("\n")]
    lines = [ln for ln in lines if ln]  # 빈줄 제거
    return "\n".join(lines)

def _extract_naver_news(soup: BeautifulSoup) -> str | None:
    """
    네이버 뉴스 전용 본문 셀렉터 (신/구 버전 호환)
    """
    area = soup.select_one("#newsct_article") or soup.select_one("#dic_area")
    return area.get_text(separator="\n", strip=True) if area else None

def _extract_generic(soup: BeautifulSoup) -> str:
    """
    범용 본문 추출: <article> → #content → main → body 순 폴백
    """
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for sel in ("article", "#content", "main"):
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)

# -------------------------------
# 외부 기사 가져오기
# -------------------------------
def fetch_article_text(url: str, timeout: int = 10, max_chars: int = 4000) -> Tuple[str, str]:
    """
    외부 페이지에서 (제목, 본문 일부) 반환
    실패 시 (에러표시, 메시지) 반환
    """
    try:
        host = urlparse(url).hostname or ""
        if _is_private_host(host):
            return "[에러: 비허용 대상]", "로컬/사설망 주소는 접근할 수 없습니다."

        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        title = (soup.title.string or "").strip() if soup.title else ""

        # 사이트별 전용 → 범용 순으로 폴백
        text = _extract_naver_news(soup) or _extract_generic(soup)
        text = _clean_text(text)[:max_chars]

        return (title or url), (text or "[본문 추출 실패]")
    except Exception as e:
        return "[에러: 기사 요청 실패]", f"{type(e).__name__}: {e}"

# -------------------------------
# 프롬프트용 블록 생성
# -------------------------------
def make_url_context(url: str) -> str:
    """
    모델 프롬프트에 바로 넣기 좋은 컨텍스트 블록 생성
    """
    title, text = fetch_article_text(url)
    return f"""[외부 링크 원문]
제목: {title}
URL: {url}

본문(발췌):
{text}
"""
