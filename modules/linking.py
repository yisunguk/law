# modules/linking.py — REPLACE (간결 버전)
from urllib.parse import quote
import os, contextlib, re, requests, html

ALIAS_MAP = {"형소법":"형사소송법","민소법":"민사소송법","민집법":"민사집행법"}

def _norm_law(n: str) -> str:
    n = (n or "").strip()
    return ALIAS_MAP.get(n, n)

def _norm_art(s: str) -> str:
    s = (s or "").strip()
    if s.isdigit(): return f"제{s}조"
    if s.endswith("조") and s[:-1].isdigit(): return "제"+s
    return s

def make_pretty_article_url(law_name: str, article_label: str) -> str:
    return f"https://law.go.kr/법령/{quote(_norm_law(law_name))}/{quote(_norm_art(article_label))}"

def make_pretty_law_main_url(law_name: str) -> str:
    return f"https://law.go.kr/법령/{quote(_norm_law(law_name))}"

def _moleg_key() -> str:
    v = (os.getenv("MOLEG_SERVICE_KEY") or "").strip()
    if v: return v
    with contextlib.suppress(Exception):
        import streamlit as st  # type: ignore
        vv = st.secrets.get("MOLEG_SERVICE_KEY")
        if vv: return str(vv).strip()
    return ""

def resolve_article_url(law_name: str, article_label: str) -> str:
    """기본은 예쁜 한글주소. (선택) 공공데이터포털 키가 있으면 DRF '법령상세링크'로 대체."""
    url = make_pretty_article_url(law_name, article_label)
    key = _moleg_key()
    if not key:
        return url
    try:
        base = "https://apis.data.go.kr/1170000/law/lawSearchList.do"
        params = {"ServiceKey": key, "target":"law", "query": law_name, "numOfRows":1, "pageNo":1}
        r = requests.get(base, params=params, timeout=3.5)
        if r.status_code != 200: return url
        m = re.search(r"<법령상세링크>(.*?)</법령상세링크>", r.text or "")
        if m:
            return html.unescape(m.group(1)).strip() or url
    except Exception:
        pass
    return url
