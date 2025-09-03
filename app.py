# -*- coding: utf-8 -*-
# law_fetch.py — OC/DRF 비사용(OFF) 안정 버전
# - DRF(OpenAPI) 호출 경로를 완전히 끔 (USE_DRF=False)
# - DRF 관련 함수는 호출되어도 즉시 빈 값 반환(안전 가드)
# - 조문 슬라이스/JO 변환 유틸은 기존 호환을 위해 유지

from __future__ import annotations

import os
import re
import json
from typing import Tuple, Optional

import requests  # (현재 파일에선 DRF OFF지만, 의존성 호환 위해 유지)
from bs4 import BeautifulSoup
from urllib.parse import urlencode

# ─────────────────────────────────────────────────────────────────────
# 0) 전역 스위치: DRF 완전 비활성화
# ─────────────────────────────────────────────────────────────────────
USE_DRF = False  # ← True로 바꾸면 DRF 재활성화 (OC 필요)

def _get_oc() -> str:
    """OC 미사용 모드에서는 항상 빈 문자열을 반환."""
    return ""

# ─────────────────────────────────────────────────────────────────────
# 1) DRF 링크 생성 (OFF 시 링크 자체 미생성)
# ─────────────────────────────────────────────────────────────────────
def _build_drf_link(
    mst: str,
    typ: str = "HTML",
    *,
    efYd: Optional[str] = None,
    lang: str = "KO",
    jo: Optional[str] = None,
) -> str:
    if not USE_DRF:
        return ""  # DRF OFF
    base = "https://www.law.go.kr/DRF/lawService.do"
    q = {"OC": _get_oc(), "target": "law", "type": typ}
    if mst:
        q["MST"] = str(mst)
    if efYd:
        q["efYd"] = efYd
    if lang:
        q["LANG"] = lang
    if jo:
        q["JO"] = jo
    return base + "?" + urlencode(q, doseq=False, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────
# 2) 텍스트 평문화 헬퍼 (DRF JSON/HTML 용) — 호환성 유지
# ─────────────────────────────────────────────────────────────────────
def _extract_text_from_html(html_text: str) -> str:
    soup = BeautifulSoup(html_text or "", "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    main = (
        soup.select_one("#contentBody")
        or soup.select_one("#conBody")
        or soup.select_one("#conScroll")
        or soup.select_one(".conScroll")
        or soup.select_one("#content")
        or soup
    )
    txt = main.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", txt)

def _extract_text_from_json(json_text: str) -> str:
    try:
        data = json.loads(json_text or "{}")
    except Exception:
        return ""
    lines: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            al = v.get("조문여부") or v.get("AL")
            an = v.get("조문번호") or v.get("AN")
            at = v.get("조문제목") or v.get("AT")
            if (al == "Y") and an:
                head = f"제{an}조"
                if at:
                    head += f"({at})"
                lines.append(head)
            bt = v.get("본문") or v.get("BT")
            if isinstance(bt, str) and bt.strip():
                lines.append(bt.strip())
            for k in ("항", "호", "목", "조문", "조문내용"):
                x = v.get(k)
                if x:
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(data)
    return "\n".join(lines).strip()

# ─────────────────────────────────────────────────────────────────────
# 3) (과거 DRF 검색) 법령명→MST — DRF OFF에서는 빈 값
# ─────────────────────────────────────────────────────────────────────
def find_mst_by_law_name(
    law_name: str,
    efYd: Optional[str] = None,
    timeout: float = 8.0,
) -> str:
    if not USE_DRF:
        return ""  # DRF OFF
    law_name = (law_name or "").strip()
    if not law_name:
        return ""
    base = "https://www.law.go.kr/DRF/lawSearch.do"
    q = {"OC": _get_oc(), "target": "law", "type": "JSON", "query": law_name}
    if efYd:
        q["efYd"] = efYd

    url = base + "?" + urlencode(q)
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = json.loads(r.text or "{}")
    except Exception:
        return ""

    items = data.get("법령목록") or data.get("laws") or []
    if isinstance(items, dict):
        items = [items]

    # 정확 일치
    for it in items:
        nm = (it.get("법령명한글") or it.get("법령명") or "").strip()
        if nm == law_name:
            return (it.get("법령일련번호") or it.get("MST") or "").strip()
    # 첫 후보
    for it in items:
        m = (it.get("법령일련번호") or it.get("MST") or "").strip()
        if m:
            return m
    return ""

# ─────────────────────────────────────────────────────────────────────
# 4) DRF 호출(OFF 시 즉시 빈 값)
# ─────────────────────────────────────────────────────────────────────
def _drf_get(
    mst: str,
    *,
    typ: str = "JSON",
    jo: Optional[str] = None,
    efYd: Optional[str] = None,
    timeout: float = 10.0,
) -> Tuple[str, str]:
    if not USE_DRF:
        return "", ""  # DRF OFF
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
    # DRF가 200(OK)로 에러 HTML을 줄 수 있어 선제 필터
    bad = (
        "접근이 제한되었습니다",
        "페이지 접속에 실패하였습니다",
        "URL에 MST 요청값이 없습니다",
        "일치하는 법령이 없습니다",
        "로그인한 사용자 OC만 사용가능합니다",
    )
    if any(sig in head for sig in bad):
        return "", url
    if typ.upper() == "JSON":
        ct = (r.headers.get("Content-Type") or "").lower()
        if "json" not in ct and "<html" in head.lower():
            return "", url
    return text, url

def fetch_law_detail_text(
    mst: str,
    *,
    prefer: str = "JSON",
    jo: Optional[str] = None,
    efYd: Optional[str] = None,
    timeout: float = 10.0,
) -> Tuple[str, str, str]:
    """DRF OFF: 항상 빈 텍스트와 빈 링크를 반환(호출 호환용)."""
    if not USE_DRF:
        return "", prefer.upper(), ""  # DRF OFF
    order = [prefer.upper(), "HTML" if prefer.upper() == "JSON" else "JSON"]
    last_url = ""
    for typ in order:
        raw, last_url = _drf_get(mst, typ=typ, jo=jo, efYd=efYd, timeout=timeout)
        txt = _extract_text_from_json(raw) if typ == "JSON" else _extract_text_from_html(raw)
        if len(txt.strip()) >= 30:
            return txt, typ, last_url
    return "", order[-1], last_url

# ─────────────────────────────────────────────────────────────────────
# 5) 조문 슬라이스/JO 변환 (딥링크 스크랩 경로와 호환)
# ─────────────────────────────────────────────────────────────────────
_ART_HDR = re.compile(r"^\s*제\d{1,4}조(의\d{1,3})?\s*", re.M)

def extract_article_block(full_text: str, art_label: str, max_chars: int = 4000) -> str:
    """페이지 전체 텍스트에서 해당 조문 구간만 떼어내기."""
    if not full_text or not art_label:
        return ""
    mnum = re.search(r"(제\s*\d{1,4}\s*조(?:\s*의\s*\d{1,3})?)", art_label)
    key = mnum.group(1) if mnum else art_label
    m = (re.search(rf"^\s*{re.escape(key)}[^\n]*$", full_text, re.M)
         or re.search(rf"^\s*{re.escape(key)}\b.*$", full_text, re.M))
    if not m:
        return ""
    start = m.start()
    n = _ART_HDR.search(full_text, m.end())
    end = n.start() if n else len(full_text)
    return full_text[start:end].strip()[:max_chars]

def jo_from_art_label(art_label: str) -> Optional[str]:
    """'제83조', '제10조의2' → 6자리 조문코드(008300 / 001002)"""
    m = re.search(r"제\s*(\d{1,4})\s*조(?:\s*의\s*(\d{1,3}))?", art_label or "")
    if not m:
        return None
    main = int(m.group(1))
    sub = int(m.group(2)) if m.group(2) else 0
    return f"{main:04d}{sub:02d}"

# ─────────────────────────────────────────────────────────────────────
# 6) 최종 엔트리 (DRF OFF: 항상 빈 텍스트/링크)
#    - 실제 본문/링크는 plan_executor의 딥링크 스크랩 경로에서 제공
# ─────────────────────────────────────────────────────────────────────
def fetch_article_block_by_mst(
    mst: str,
    art_label: Optional[str],
    prefer: str = "JSON",
    efYd: Optional[str] = None,
    timeout: float = 10.0,
) -> Tuple[str, str]:
    if not USE_DRF:
        return "", ""  # DRF OFF
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
