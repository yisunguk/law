# modules/linking.py — COMPLETE (간결/안정 버전)
from urllib.parse import quote
import os, contextlib, re, requests, html

# 흔한 축약어를 정식 명칭으로 치환
ALIAS_MAP = {"형소법":"형사소송법","민소법":"민사소송법","민집법":"민사집행법"}

def _norm_law(n: str) -> str:
    n = (n or "").strip()
    return ALIAS_MAP.get(n, n)

# ✅ [PATCH] modules/linking.py : _norm_art 교체
def _norm_art(s: str) -> str:
    """
    다양한 입력을 '제N조' 또는 '제N조의M'로 표준화.
    허용 예: '83', '제83조', '83조', '제 83 조', '83조의2', '제83조의 2'
    """
    s = (s or "").strip()

    import re
    # 1) '제N조의M' / '제 N 조 의 M'
    m = re.fullmatch(r'제?\s*(\d{1,4})\s*조\s*의\s*(\d{1,3})', s)
    if m:
        return f"제{int(m.group(1))}조의{int(m.group(2))}"

    # 2) 'N조의M' (제 생략)
    m = re.fullmatch(r'(\d{1,4})\s*조\s*의\s*(\d{1,3})', s)
    if m:
        return f"제{int(m.group(1))}조의{int(m.group(2))}"

    # 3) '제N조' / '제 N 조'
    m = re.fullmatch(r'제?\s*(\d{1,4})\s*조', s)
    if m:
        return f"제{int(m.group(1))}조"

    # 4) 숫자만: '83' → '제83조'
    if s.isdigit():
        return f"제{int(s)}조"

    # 5) 기타는 원본 유지(이미 표준형일 수 있음)
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
