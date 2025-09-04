# modules/linking.py
from urllib.parse import quote
import os, contextlib

ALIAS_MAP = {
    "형소법": "형사소송법",
    "민소법": "민사소송법",
    "민집법": "민사집행법",
}

def _normalize_law_name(name: str) -> str:
    return ALIAS_MAP.get((name or "").strip(), (name or "").strip())

def _normalize_article_label(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # "83", "83조" → "제83조"; "제83조의2" 유지
    if s.isdigit():
        return f"제{s}조"
    if s.startswith("제") and "조" in s:
        return s
    if s.endswith("조") and s[:-1].isdigit():
        return "제" + s
    return s

def make_pretty_article_url(law_name: str, article_label: str) -> str:
    law = quote(_normalize_law_name(law_name))
    art = quote(_normalize_article_label(article_label))
    return f"https://law.go.kr/법령/{law}/{art}"

def make_pretty_law_main_url(law_name: str) -> str:
    return f"https://law.go.kr/법령/{quote(_normalize_law_name(law_name))}"

def _moleg_service_key() -> str:
    key = (os.getenv("MOLEG_SERVICE_KEY") or "").strip()
    if key:
        return key
    with contextlib.suppress(Exception):
        import streamlit as st  # type: ignore
        v = st.secrets.get("MOLEG_SERVICE_KEY")
        if v:
            return str(v).strip()
    return ""

def fetch_drf_law_link_by_name(law_name: str) -> str:
    """
    (옵션) 공공데이터포털 키가 있으면 DRF '법령상세링크'를 사용.
    키가 없거나 실패해도 조용히 빈 문자열 반환.
    """
    svc_key = _moleg_service_key()
    if not svc_key:
        return ""
    try:
        import requests, re, html
        base = "https://apis.data.go.kr/1170000/law/lawSearchList.do"
        params = {"ServiceKey": svc_key, "target": "law", "query": law_name, "numOfRows": 1, "pageNo": 1}
        r = requests.get(base, params=params, timeout=3.5)
        if r.status_code != 200:
            return ""
        m = re.search(r"<법령상세링크>\s*<!\[CDATA\[(.*?)\]\]>", r.text, re.S)
        path = (m.group(1) or "").strip() if m else ""
        if not path:
            return ""
        if not path.startswith("/"): path = "/" + path
        return "https://www.law.go.kr" + html.unescape(path)
    except Exception:
        return ""

def resolve_article_url(law_name: str, article_label: str) -> str:
    law = quote((_normalize_law_name(law_name) or "").strip())
    art = quote((_normalize_article_label(article_label) or "").strip())
    return f"https://www.law.go.kr/법령/{law}/{art}"
