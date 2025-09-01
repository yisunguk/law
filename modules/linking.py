# ✅ [DROP-IN] modules/linking.py — 공용 링크 생성기(딥링크 우선 → DRF → 메인)
from __future__ import annotations
import os, re, html, contextlib
from typing import Dict, List, Tuple, Optional
from urllib.parse import quote

try:
    import requests
except Exception:
    requests = None

ALIAS_MAP: Dict[str, str] = {
    "형소법": "형사소송법",
    "민소법": "민사소송법",
    "민집법": "민사집행법",
}

def _normalize_law_name(name: str) -> str:
    return ALIAS_MAP.get((name or "").strip(), (name or "").strip())

def make_pretty_article_url(law_name: str, article_label: str) -> str:
    return f"https://law.go.kr/법령/{quote(law_name)}/{quote(article_label)}"

def make_pretty_law_main_url(law_name: str) -> str:
    return f"https://law.go.kr/법령/{quote(law_name)}"

def _moleg_service_key() -> Optional[str]:
    key = (os.getenv("MOLEG_SERVICE_KEY") or "").strip()
    if key:
        return key
    with contextlib.suppress(Exception):
        import streamlit as st  # type: ignore
        val = st.secrets.get("MOLEG_SERVICE_KEY")
        if val:
            return str(val).strip()
    return None

def fetch_drf_law_link_by_name(law_name: str) -> Optional[str]:
    """
    공공데이터포털(OpenAPI)로 '법령상세링크'를 조회하여
    https://www.law.go.kr/DRF/lawService.do?... 형태의 DRF HTML 링크를 받는다.
    키가 없거나 실패하면 None.
    """
    svc_key = _moleg_service_key()
    if not svc_key or not requests:
        return None
    base = "https://apis.data.go.kr/1170000/law/lawSearchList.do"
    params = {"ServiceKey": svc_key, "target": "law", "query": law_name, "numOfRows": 1, "pageNo": 1}
    try:
        r = requests.get(base, params=params, timeout=3.5)
        if r.status_code != 200:
            return None
        text = r.text
        m = re.search(r"<법령상세링크>\s*<!\[CDATA\[(.*?)\]\]>\s*</법령상세링크>|<법령상세링크>(.*?)</법령상세링크>", text, re.S)
        path = (m.group(1) or m.group(2) or "").strip() if m else ""
        if not path:
            return None
        if not path.startswith("/"):
            path = "/" + path
        return "https://www.law.go.kr" + html.unescape(path)
    except Exception:
        return None

def _url_is_ok(url: str) -> bool:
    if not requests:
        return True
    try:
        r = requests.get(url, timeout=3.5, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code != 200:
            return False
        head = (r.text or "")[:3000]
        bad = ("삭제", "존재하지 않는", "현행법이 아닙니다")
        return not any(s in head for s in bad)
    except Exception:
        return False

def resolve_article_url(law_name: str, article_label: str) -> str:
    """
    우선순위:
      1) 한글 조문 딥링크 (검증 통과 시)
      2) DRF 법령 메인(공공데이터포털 키 있을 때)
      3) 한글 법령 메인
    """
    law_name = _normalize_law_name(law_name)
    art = (article_label or "").strip()

    # 1) 조문 딥링크
    pretty = make_pretty_article_url(law_name, art)
    if _url_is_ok(pretty):
        return pretty

    # 2) DRF 메인(항상 열림) — 키가 있으면 활용
    drf = fetch_drf_law_link_by_name(law_name)
    if drf:
        return drf

    # 3) 최후 폴백: 법령 메인
    return make_pretty_law_main_url(law_name)