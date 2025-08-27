# modules/linking.py
from __future__ import annotations
import os
import re
import html
import json
from typing import Dict, List, Tuple, Optional
from urllib.parse import quote
import contextlib

try:
    # requests가 없다면 graceful degradation
    import requests  # noqa
except Exception:  # pragma: no cover
    requests = None

# ──────────────────────────────────────────────────────────────────────────────
# 1) 약칭 보정
# ──────────────────────────────────────────────────────────────────────────────
ALIAS_MAP: Dict[str, str] = {
    "형소법": "형사소송법",
    "민소법": "민사소송법",
    "민집법": "민사집행법",
    # 필요 시 자유롭게 확장
}

# "민법 제839조의2" 패턴
ARTICLE_PAT = re.compile(
    r'(?P<law>[가-힣A-Za-z0-9·()\s]{2,40})\s*제(?P<num>\d{1,4})조(?P<ui>(의\d{1,3}){0,2})'
)

def _normalize_law_name(name: str) -> str:
    name = (name or "").strip()
    return ALIAS_MAP.get(name, name)

# ──────────────────────────────────────────────────────────────────────────────
# 2) URL 생성기
# ──────────────────────────────────────────────────────────────────────────────
def make_pretty_article_url(law_name: str, article_label: str) -> str:
    """
    사람이 읽기 좋은 딥링크: https://law.go.kr/법령/<법령명>/<제N조의M>
    """
    return f"https://law.go.kr/법령/{quote(law_name)}/{quote(article_label)}"

def make_pretty_law_main_url(law_name: str) -> str:
    return f"https://law.go.kr/법령/{quote(law_name)}"

def _moleg_service_key() -> Optional[str]:
    # Streamlit secrets 또는 환경변수에서 서비스키를 받습니다.
    # (없어도 동작은 하나, DRF 링크 우선 사용이 불가해집니다)
    key = os.getenv("MOLEG_SERVICE_KEY")
    if key:
        return key
    # streamlit이 아니어도 import 오류 없이 처리
    with contextlib.suppress(Exception):
        import streamlit as st  # type: ignore
        return st.secrets.get("MOLEG_SERVICE_KEY")
    return None

def fetch_drf_law_link_by_name(law_name: str) -> Optional[str]:
    """
    법제처 OpenAPI(법령정보 목록 조회)를 사용해 '법령상세링크'(DRF)를 받아옵니다.
    성공 시 https://www.law.go.kr/DRF/lawService.do?... 형태의 '전체 법령 HTML' 링크를 반환.
    실패/미설정 시 None.
    가이드: 국가법령정보 공유 서비스 OpenAPI 활용가이드:contentReference[oaicite:0]{index=0}
    """
    svc_key = _moleg_service_key()
    if not svc_key or not requests:
        return None

    base = "https://apis.data.go.kr/1170000/law/lawSearchList.do"
    params = {
        "ServiceKey": svc_key,
        "target": "law",
        "query": law_name,
        "numOfRows": 1,
        "pageNo": 1,
    }
    try:
        r = requests.get(base, params=params, timeout=3.5)
        if r.status_code != 200:
            return None

        # OpenAPI는 XML을 반환하지만, 간단히 문자열 파싱(의존도↓).
        text = r.text
        # <법령상세링크>...</법령상세링크> 추출
        m = re.search(r"<법령상세링크>\s*<!\[CDATA\[(.*?)\]\]>\s*</법령상세링크>|<법령상세링크>(.*?)</법령상세링크>", text, re.S)
        path = None
        if m:
            path = m.group(1) or m.group(2)
            path = html.unescape(path or "").strip()
        if not path:
            return None

        # path는 보통 "/DRF/lawService.do?...&MST=nnn&type=HTML" 형태
        if not path.startswith("/"):
            path = "/" + path
        return "https://www.law.go.kr" + path
    except Exception:
        return None

def _url_is_ok(url: str) -> bool:
    if not requests:
        return True  # 오프라인/requests 미설치 환경에서는 검증 스킵
    try:
        r = requests.get(url, timeout=3.5)
        if r.status_code != 200:
            return False
        # 일부 페이지는 200이더라도 '삭제' 알림이 포함될 수 있어 초반만 점검
        head = (r.text or "")[:3000]
        bad_signals = ("삭제", "존재하지 않는", "현행법이 아닙니다")
        return not any(s in head for s in bad_signals)
    except Exception:
        return False

def resolve_article_url(law_name: str, article_label: str) -> str:
    """
    우선순위:
      1) DRF 법령 메인(항상 유효) – OpenAPI 키가 있을 때
      2) 한글 조문 딥링크(검증 성공 시)
      3) 한글 법령 메인(최후 폴백)
    """
    law_name = _normalize_law_name(law_name)
    art = (article_label or "").strip()

    # 2) 사람이 읽기 좋은 조문 딥링크
    pretty_article = make_pretty_article_url(law_name, art)
    if _url_is_ok(pretty_article):
        return pretty_article

    # 1) DRF 메인(항상 유효) – 키가 있으면 이것이 더 낫습니다
    drf = fetch_drf_law_link_by_name(law_name)
    if drf:
        return drf

    # 3) 최후 폴백: 한글 법령 메인
    return make_pretty_law_main_url(law_name)

# ──────────────────────────────────────────────────────────────────────────────
# 3) 텍스트에서 조문 추출 및 렌더링
# ──────────────────────────────────────────────────────────────────────────────
def extract_article_citations(text: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for m in ARTICLE_PAT.finditer(text or ""):
        law = _normalize_law_name(m.group("law"))
        art = f"제{m.group('num')}조{m.group('ui') or ''}"
        found.append((law, art))
    # 유니크 보장
    return list({(l, a) for (l, a) in found})

def render_article_links(citations: List[Tuple[str, str]]) -> str:
    """
    링크는 'resolve_article_url'을 통해 항상 살아있는 주소로 출력됩니다.
    - 가능하면 조문 딥링크
    - 실패 시 DRF 메인
    - 최후에는 법령 메인
    """
    if not citations:
        return ""
    lines = ["", "### 참고 링크(조문)"]
    for law, art in sorted(citations):
        url = resolve_article_url(law, art)
        lines.append(f"- [{law} {art}]({url})")
    return "\n".join(lines)

def merge_article_links_block(text: str) -> str:
    """
    본문 어디에서든 발견한 '법령명 제N조(의M)'를 모아
    문서 끝에 '참고 링크(조문)' 블록을 추가/갱신합니다.
    """
    citations = extract_article_citations(text)
    block = render_article_links(citations)
    if not block:
        return text

    # 기존 블록이 있으면 교체, 없으면 맨 끝에 추가
    pat_block = re.compile(r'\n### 참고 링크\(조문\)[\s\S]*$', re.M)
    if pat_block.search(text):
        return pat_block.sub(block, text)
    return text.rstrip() + "\n" + block + "\n"
