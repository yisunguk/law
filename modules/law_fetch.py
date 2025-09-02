# law_fetch.py — Variant A: JSON-first + JO(조문) 지원 (권장)
from __future__ import annotations
import os, re, json
from typing import Tuple, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
# --- add to top of law_fetch.py (imports 아래) ---
# 교체블록: law_fetch.py 내 _get_oc 함수 전체 교체
def _get_oc() -> str:
    """
    DRF OC 코드를 한 군데에서 안전하게 가져온다.
    - 우선순위: 환경변수(LAW_API_OC/LAW_API_KEY) → streamlit secrets → 빈 값
    """
    import os
    oc = (os.environ.get("LAW_API_OC") or os.environ.get("LAW_API_KEY") or "").strip()
    if oc:
        return oc
    try:
        import streamlit as st  # type: ignore
        oc = (st.secrets.get("LAW_API_OC") or st.secrets.get("LAW_API_KEY") or "").strip()
    except Exception:
        oc = ""
    return oc


def _build_drf_link(
    mst: str,
    typ: str = "HTML",
    *,
    efYd: Optional[str] = None,
    lang: str = "KO",
    jo: Optional[str] = None
) -> str:
    base = "https://www.law.go.kr/DRF/lawService.do"
    q = {
        "OC": _get_oc(),         # <-- 핵심 수정: env만 보지 않고 secrets까지
        "target": "law",
        "type": typ,
    }
    if mst:
        q["MST"] = str(mst)
    if efYd:
        q["efYd"] = efYd
    if lang:
        q["LANG"] = lang
    if jo:
        q["JO"] = jo
    from urllib.parse import urlencode
    return base + "?" + urlencode(q, doseq=False, encoding="utf-8")


# ---------------------------------
# 포맷별 텍스트 평문화
# ---------------------------------
def _extract_text_from_html(html_text: str) -> str:
    soup = BeautifulSoup(html_text or "", "lxml")
    for t in soup(["script","style","noscript"]): t.decompose()
    main = (soup.select_one("#contentBody") or soup.select_one("#conBody") or
            soup.select_one("#conScroll") or soup.select_one(".conScroll") or
            soup.select_one("#content") or soup.select_one("body") or soup)
    txt = main.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", txt)

def _extract_text_from_json(json_text: str) -> str:
    try:
        data = json.loads(json_text or "{}")
    except Exception:
        return ""
    lines = []
    def walk(v):
        if isinstance(v, dict):
            al = v.get("조문여부") or v.get("AL")
            an = v.get("조문번호") or v.get("AN")
            at = v.get("조문제목") or v.get("AT")
            if (al == "Y") and an:
                head = f"제{an}조"
                if at: head += f"({at})"
                lines.append(head)
            bt = v.get("본문") or v.get("BT")
            if isinstance(bt, str) and bt.strip():
                lines.append(bt.strip())
            for k in ("항","호","목","조문","조문내용"):
                x = v.get(k)
                if x: walk(x)
        elif isinstance(v, list):
            for x in v: walk(x)
    walk(data)
    return "\n".join(lines).strip()
# law_fetch.py
from urllib.parse import urlencode

def find_mst_by_law_name(
    law_name: str,
    efYd: Optional[str] = None,
    timeout: float = 8.0
) -> str:
    """
    DRF lawSearch API로 법령명을 검색해 MST(법령일련번호)를 찾아준다.
    - 정확 일치 우선, 없으면 첫 후보
    """
    law_name = (law_name or "").strip()
    if not law_name:
        return ""

    base = "https://www.law.go.kr/DRF/lawSearch.do"
    q = {
        "OC": _get_oc(),         # <-- 핵심 수정
        "target": "law",
        "type": "JSON",
        "query": law_name,
    }
    if efYd:
        q["efYd"] = efYd

    url = base + "?" + urlencode(q)
    try:
        r = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        r.raise_for_status()
        data = json.loads(r.text or "{}")
    except Exception:
        return ""

    items = data.get("법령목록") or data.get("laws") or []
    if isinstance(items, dict):
        items = [items]

    # 1) 정확 일치
    for it in items:
        nm = (it.get("법령명한글") or it.get("법령명") or "").strip()
        if nm == law_name:
            return (it.get("법령일련번호") or it.get("MST") or "").strip()

    # 2) 첫 후보
    for it in items:
        m = (it.get("법령일련번호") or it.get("MST") or "").strip()
        if m:
            return m
    return ""


# ---------------------------------
# DRF 호출
# ---------------------------------
from typing import Optional, Tuple

def _drf_get(
    mst: str,
    *,
    typ: str = "JSON",
    jo: Optional[str] = None,
    efYd: Optional[str] = None,
    timeout: float = 10.0,
) -> Tuple[str, str]:
    """
    DRF lawService 호출(문자열 응답, 에러페이지 감지 포함)
    반환: (text, used_url)
      - 에러/차단/파라미터 문제로 보이면 text="" 로 반환
    """
    url = _build_drf_link(mst, typ=typ, efYd=efYd, jo=jo)

    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "*/*",
                "Referer": "https://www.law.go.kr/DRF/index.do",
            },
        )
    except Exception:
        return "", url

    if not (200 <= r.status_code < 300):
        return "", url

    text = r.text or ""
    head = text[:2000]

    # DRF가 에러를 HTML로 200과 함께 돌려줄 때를 방어
    bad_signatures = (
        "접근이 제한되었습니다",
        "페이지 접속에 실패하였습니다",
        "URL에 MST 요청값이 없습니다",
        "일치하는 법령이 없습니다",
        "로그인한 사용자 OC만 사용가능합니다",
    )
    if any(sig in head for sig in bad_signatures):
        return "", url

    # JSON 요청인데 HTML 형태로 내려오면 에러로 간주
    if typ.upper() == "JSON":
        ct = (r.headers.get("Content-Type") or "").lower()
        if "json" not in ct and "<html" in head.lower():
            return "", url

    return text, url


def fetch_law_detail_text(mst: str, *, prefer: str = "JSON",
                          jo: Optional[str] = None, efYd: Optional[str] = None,
                          timeout: float = 10.0) -> tuple[str,str,str]:
    order = [prefer.upper(), "HTML" if prefer.upper()=="JSON" else "JSON"]
    last_url = ""
    for typ in order:
        raw, last_url = _drf_get(mst, typ=typ, jo=jo, efYd=efYd, timeout=timeout)
        txt = _extract_text_from_json(raw) if typ=="JSON" else _extract_text_from_html(raw)
        if len(txt.strip()) >= 30:
            return txt, typ, last_url
    return "", order[-1], last_url

# ---------------------------------
# 조문 슬라이스/JO 변환
# ---------------------------------
_ART_HDR = re.compile(r"^\s*제\d{1,4}조(의\d{1,3})?\s*", re.M)

def extract_article_block(full_text: str, art_label: str, max_chars: int = 4000) -> str:
    if not full_text or not art_label: return ""
    mnum = re.search(r"(제\s*\d{1,4}\s*조(?:\s*의\s*\d{1,3})?)", art_label)
    key = mnum.group(1) if mnum else art_label
    m = (re.search(rf"^\s*{re.escape(key)}[^\n]*$", full_text, re.M) or
         re.search(rf"^\s*{re.escape(key)}\b.*$", full_text, re.M))
    if not m: return ""
    start = m.start()
    n = _ART_HDR.search(full_text, m.end())
    end = n.start() if n else len(full_text)
    return full_text[start:end].strip()[:max_chars]

def jo_from_art_label(art_label: str) -> Optional[str]:
    m = re.search(r"제\s*(\d{1,4})\s*조(?:\s*의\s*(\d{1,3}))?", art_label or "")
    if not m: return None
    main = int(m.group(1)); sub = int(m.group(2)) if m.group(2) else 0
    return f"{main:04d}{sub:02d}"  # 83조 -> 008300, 10조의2 -> 001002

# ---------------------------------
# 최종 엔트리: MST + (옵션)조문라벨 -> 텍스트
# ---------------------------------
def fetch_article_block_by_mst(mst: str, art_label: Optional[str],
                               prefer: str = "JSON", efYd: Optional[str] = None,
                               timeout: float = 10.0) -> tuple[str,str]:
    jo = jo_from_art_label(art_label) if art_label else None
    txt, _, _ = fetch_law_detail_text(mst, prefer=prefer, jo=jo, efYd=efYd, timeout=timeout)
    block = txt
    if art_label and not jo:
        block = extract_article_block(txt, art_label)
    if not (block and block.strip()):
        alt = "HTML" if (prefer or "").upper() == "JSON" else "JSON"
        txt2, _, _ = fetch_law_detail_text(mst, prefer=alt, jo=jo, efYd=efYd, timeout=timeout)
        block = (extract_article_block(txt2, art_label) if (art_label and not jo) else txt2) or ""
    link = _build_drf_link(mst, typ="HTML", efYd=efYd, jo=jo)
    return (block or "").strip(), link