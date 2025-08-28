# --- [PATCH] DRF 헤더 추가 + JSON/XML/HTML 폴백 + 프라이머 캡슐 ---

from __future__ import annotations
import os, re, json
from typing import Any
import requests
from bs4 import BeautifulSoup
from lxml import etree

# DRF가 JSON 대신 뷰어 HTML을 주는 경우가 있어 헤더를 명시합니다.
HEADERS_DRF = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.law.go.kr/DRF/index.do",
    "X-Requested-With": "XMLHttpRequest",
}

def _get_oc() -> str:
    """OC를 전역/환경변수에서 가져옵니다."""
    return (globals().get("LAW_API_OC") or os.getenv("LAW_API_OC") or "").strip()

def _drf_params(mst: str, typ: str, efYd: str | None = None) -> dict:
    p = {"OC": _get_oc(), "target": "law", "MST": str(mst), "type": typ}
    if efYd:
        p["efYd"] = efYd.replace("-", "")
    return p

def drf_fetch(mst: str, typ: str = "JSON", timeout: float = 10.0) -> requests.Response:
    """DRF 상세 호출 (헤더 포함)"""
    url = "https://www.law.go.kr/DRF/lawService.do"
    return requests.get(url, params=_drf_params(mst, typ), headers=HEADERS_DRF, timeout=timeout)

def _extract_text_from_json(text: str) -> tuple[str, dict]:
    """DRF JSON에서 조문/본문 텍스트를 최대한 수집"""
    try:
        data = json.loads(text)
    except Exception:
        return "", {}

    # 트리 순회 유틸
    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                yield k, x
                yield from walk(x)
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)

    # 법령명 후보
    law_name = ""
    for k, v in walk(data):
        if k in ("법령명한글", "법령명", "lawName", "법령명_한글") and isinstance(v, str) and v.strip():
            law_name = v.strip()
            break

    # 조문/본문 텍스트 후보
    texts: list[str] = []
    want_keys = {"조문내용", "조문", "내용", "text", "조문본문"}
    for k, v in walk(data):
        if k in want_keys and isinstance(v, str):
            s = v.strip()
            if len(s) >= 30:
                texts.append(s)
                if len(texts) >= 3:
                    break

    # 여전히 없으면 문자열 덩어리 아무거나
    if not texts:
        for k, v in walk(data):
            if isinstance(v, str):
                s = v.strip()
                if 100 <= len(s) <= 4000:
                    texts.append(s)
                    if len(texts) >= 3:
                        break

    snippet = "\n".join(texts[:3])
    return snippet, {"law_name": law_name}

def _extract_text_from_xml(text: str) -> str:
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except Exception:
        return ""
    parts = []
    for t in root.itertext():
        t = (t or "").strip()
        if t:
            parts.append(t)
    return "\n".join(parts)[:3000]

def _extract_text_from_html(text: str) -> str:
    soup = BeautifulSoup(text, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    main = soup.select_one("#conScroll, .conScroll, .lawView, #content, body")
    s = main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True)
    return s[:3000]

def fetch_law_detail_text(mst: str, prefer: str = "JSON") -> tuple[str, str, dict]:
    """
    DRF에서 본문을 받아 텍스트로 반환
    returns: (텍스트, 사용한타입(JSON/XML/HTML), 부가정보)
    """
    order = ["JSON", "XML", "HTML"] if prefer.upper() == "JSON" else ["XML", "JSON", "HTML"]
    for typ in order:
        r = drf_fetch(mst, typ=typ)
        ctype = (r.headers.get("content-type") or "").lower()
        text = r.text or ""

        if "json" in ctype or (typ == "JSON" and text.strip().startswith("{")):
            s, info = _extract_text_from_json(text)
            if s:
                return s, "JSON", info
        elif "xml" in ctype or (typ == "XML" and text.strip().startswith("<")):
            s = _extract_text_from_xml(text)
            if s:
                return s, "XML", {}
        else:
            s = _extract_text_from_html(text)
            if s:
                return s, "HTML", {}

    return "", "", {}

def _build_drf_link(mst: str, typ: str = "HTML", efYd: str | None = None) -> str:
    from urllib.parse import urlencode, quote
    oc = _get_oc()
    if not oc:
        return ""
    return "https://www.law.go.kr/DRF/lawService.do?" + urlencode(_drf_params(mst, typ, efYd), quote_via=quote)

def _summarize_laws_for_primer(law_items: list[dict], max_items: int = 6) -> str:
    """
    통합검색 결과(law_items)를 받아 각 항목별 '법령 본문 캡슐'을 만들어 반환.
    - DRF JSON 우선 → XML → HTML 순으로 본문을 확보
    - OC가 없거나 본문이 비어도 링크는 제공
    """
    if not law_items:
        return ""

    blocks: list[str] = []
    for it in law_items[:max_items]:
        mst = str(it.get("MST") or it.get("mst") or it.get("법령ID") or "").strip()
        if not mst:
            continue
        ef = (it.get("시행일자") or it.get("efYd") or "").strip()
        law_name = (it.get("법령명한글") or it.get("법령명") or "").strip()

        text, used_type, info = fetch_law_detail_text(mst, prefer="JSON")
        if not law_name:
            law_name = (info.get("law_name") or mst)

        link = _build_drf_link(mst, typ="HTML", efYd=ef)
        snippet = (text or "").replace("\r", "").strip()
        if len(snippet) > 800:
            snippet = snippet[:800] + " …"

        title = f"• 법령: {law_name}"
        if ef:
            title += f" (시행 {ef})"
        if link:
            title += f"\n  - 본문 보기: {link}"
        if snippet:
            title += f"\n  - 발췌: {snippet}"

        blocks.append(title)

    return "【법령 본문 캡슐】\n" + "\n\n".join(blocks) if blocks else ""
