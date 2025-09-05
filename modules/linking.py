# modules/linking.py — COMPLETE (간결/안정 버전)
from urllib.parse import quote
import os, contextlib, re, requests, html

# 흔한 축약어를 정식 명칭으로 치환
ALIAS_MAP = {"형소법":"형사소송법","민소법":"민사소송법","민집법":"민사집행법"}

def _norm_law(n: str) -> str:
    n = (n or "").strip()
    return ALIAS_MAP.get(n, n)

def _norm_art(s: str) -> str:
    s = (s or "").strip()
    if s.isdigit():
        return f"제{s}조"
    if s.endswith("조") and s[:-1].isdigit():
        return "제" + s
    return s

def make_pretty_article_url(law_name: str, article_label: str) -> str:
    # 한글 법령/조문 직링크
    return f"https://law.go.kr/법령/{quote(_norm_law(law_name))}/{quote(_norm_art(article_label))}"

def make_pretty_law_main_url(law_name: str) -> str:
    return f"https://law.go.kr/법령/{quote(_norm_law(law_name))}"

def _moleg_key() -> str:
    v = (os.getenv("MOLEG_SERVICE_KEY") or "").strip()
    if v:
        return v
    with contextlib.suppress(Exception):
        import streamlit as st  # type: ignore
        vv = st.secrets.get("MOLEG_SERVICE_KEY")
        if vv:
            return str(vv).strip()
    return ""

def resolve_article_url(law_name: str, article_label: str) -> str:
    """
    기본은 '예쁜 한글주소'를 반환.
    (선택) 공공데이터포털 키가 있으면 DRF '법령상세링크'를 사용해 법령 메인 링크를 더 정확히 반환.
    조문까지 정확 매칭하는 DRF 엔드포인트가 없을 때가 있어, 우선은 예쁜주소를 유지.
    """
    url = make_pretty_article_url(law_name, article_label)
    key = _moleg_key()
    if not key:
        return url

    try:
        base = "https://apis.data.go.kr/1170000/law/lawSearchList.do"
        params = {"ServiceKey": key, "target": "law", "query": law_name, "numOfRows": 1, "pageNo": 1}
        r = requests.get(base, params=params, timeout=3.5)
        if r.status_code != 200:
            return url
        m = re.search(r"<법령상세링크>(.*?)</법령상세링크>", r.text or "")
        if m:
            # 조문 라벨은 없는 경우가 많으므로, 메인 링크를 보수적으로 유지
            main = html.unescape(m.group(1)).strip()
            return main or url
    except Exception:
        pass
    return url
