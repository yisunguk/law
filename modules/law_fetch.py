# modules/law_fetch.py — OC/DRF 비사용(OFF) 안정 버전
from __future__ import annotations
import re, json
from typing import Tuple, Optional
from urllib.parse import urlencode
import requests  # 호환 유지

# === OC/DRF 전면 비활성화 스위치 ===
USE_DRF = False

def _get_oc() -> str:
    return ""

def _build_drf_link(mst: str, typ: str="HTML", *, efYd: Optional[str]=None,
                    lang: str="KO", jo: Optional[str]=None) -> str:
    if not USE_DRF:
        return ""
    base = "https://www.law.go.kr/DRF/lawService.do"
    q = {"OC": _get_oc(), "target": "law", "type": typ}
    if mst:  q["MST"] = str(mst)
    if efYd: q["efYd"] = efYd
    if lang: q["LANG"] = lang
    if jo:   q["JO"] = jo
    return base + "?" + urlencode(q, doseq=False, encoding="utf-8")

def find_mst_by_law_name(law_name: str, efYd: Optional[str]=None, timeout: float=8.0) -> str:
    if not USE_DRF:
        return ""  # DRF OFF

def _drf_get(mst: str, *, typ: str="JSON", jo: Optional[str]=None,
             efYd: Optional[str]=None, timeout: float=10.0) -> Tuple[str,str]:
    if not USE_DRF:
        return "", ""  # DRF OFF

# ── (보조) 텍스트 평문화 ─────────────────────────────────────────────
def _extract_text_from_html(html_text: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text or "", "lxml")
        for t in soup(["script","style","noscript"]): t.decompose()
        main = (soup.select_one("#contentBody") or soup.select_one("#conBody")
                or soup.select_one("#conScroll") or soup.select_one(".conScroll")
                or soup.select_one("#content") or soup)
        txt = main.get_text("\n", strip=True)
    except Exception:
        txt = re.sub(r"<[^>]+>", "", html_text or "")
    return re.sub(r"\n{3,}", "\n\n", txt).strip()

def _extract_text_from_json(json_text: str) -> str:
    try:
        data = json.loads(json_text or "{}")
    except Exception:
        return ""
    lines: list[str] = []
    def walk(v):
        if isinstance(v, dict):
            al = v.get("AL") or v.get("조문여부")
            an = v.get("AN") or v.get("조문번호")
            at = v.get("AT") or v.get("조문제목")
            if (al == "Y") and an:
                h = f"제{an}조" + (f"({at})" if at else "")
                lines.append(h)
            bt = v.get("BT") or v.get("본문")
            if isinstance(bt, str) and bt.strip():
                lines.append(bt.strip())
            for k in ("항","호","목","조문","조문내용"):
                x = v.get(k)
                if x: walk(x)
        elif isinstance(v, list):
            for x in v: walk(x)
    walk(data)
    return "\n".join(lines).strip()

# DRF 계열 엔트리는 DRF OFF일 때 항상 빈 값 반환
def fetch_law_detail_text(mst: str, *, prefer: str="JSON",
                          jo: Optional[str]=None, efYd: Optional[str]=None,
                          timeout: float=10.0) -> tuple[str,str,str]:
    if not USE_DRF:
        return "", prefer.upper(), ""  # DRF OFF

_ART_HDR = re.compile(r"^\s*제\d{1,4}조(의\d{1,3})?\s*", re.M)

def extract_article_block(full_text: str, art_label: str, max_chars: int=4000) -> str:
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
    return f"{main:04d}{sub:02d}"

def fetch_article_block_by_mst(mst: str, art_label: Optional[str],
                               prefer: str="JSON", efYd: Optional[str]=None,
                               timeout: float=10.0) -> tuple[str,str]:
    if not USE_DRF:
        return "", ""  # DRF OFF
