# law_fetch.py — DRF 본문(조문 단위) 안정 추출 모듈

from __future__ import annotations
import os, re, json
from typing import Tuple, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode

# -------------------------
# 0) DRF 링크 빌더
# -------------------------
def _build_drf_link(mst: str, typ: str = "HTML", *, efYd: Optional[str] = None,
                    lang: str = "KO", jo: Optional[str] = None) -> str:
    base = "https://www.law.go.kr/DRF/lawService.do"
    q = {
        "OC": os.environ.get("LAW_API_OC", ""),
        "target": "law",
        "MST": str(mst),
        "type": typ,
    }
    if efYd: q["efYd"] = efYd
    if lang: q["LANG"] = lang
    if jo:   q["JO"]   = jo
    return base + "?" + urlencode(q)

# ---------------------------------
# 1) DRF 호출 + 포맷별 텍스트 평문화
# ---------------------------------
def _extract_text_from_html(html_text: str) -> str:
    soup = BeautifulSoup(html_text or "", "html.parser")
    main = soup.select_one("#contentBody") or soup.select_one("#conBody") \
           or soup.select_one("#content") or soup.select_one("body") or soup
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
                if at:
                    head += f"({at})"
                lines.append(head)
            bt = v.get("본문") or v.get("BT")
            if isinstance(bt, str) and bt.strip():
                lines.append(bt.strip())
            for k in ("항", "호", "목", "조문", "조문내용"):
                x = v.get(k)
                if x: walk(x)
        elif isinstance(v, list):
            for x in v: walk(x)
    walk(data)
    return "\n".join(lines).strip()

def _drf_get(mst: str, *, typ: str = "JSON", jo: Optional[str] = None,
             efYd: Optional[str] = None, timeout: float = 10.0) -> Tuple[str, str]:
    url = _build_drf_link(mst, typ=typ, efYd=efYd, jo=jo)
    s = requests.Session()
    r = s.get(url, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": "https://www.law.go.kr/DRF/index.do",
    })
    r.raise_for_status()
    return r.text or "", url

def fetch_law_detail_text(mst: str, *, prefer: str = "JSON",
                          jo: Optional[str] = None, efYd: Optional[str] = None,
                          timeout: float = 10.0) -> Tuple[str, str, str]:
    """
    DRF lawService 본문을 평문으로 반환.
    - prefer(JSON/HTML) 우선 시도 → 실패 시 1회 폴백
    - jo(조문 6자리)가 있으면 해당 조문만 서버에서 필터링 (권장)
    반환: (plain_text, used_type, url)
    """
    order = [prefer.upper(), "HTML" if prefer.upper() == "JSON" else "JSON"]
    last_url = ""
    for typ in order:
        text, last_url = _drf_get(mst, typ=typ, jo=jo, efYd=efYd, timeout=timeout)
        plain = _extract_text_from_json(text) if typ == "JSON" else _extract_text_from_html(text)
        if len(plain.strip()) >= 30:
            return plain, typ, last_url
    return "", order[-1], last_url

# -----------------------------------------
# 2) 조문 블록 슬라이스(헤더 관대 매칭)
# -----------------------------------------
_ART_HDR = re.compile(r"^\s*제\d{1,4}조(의\d{1,3})?\s*", re.M)

def extract_article_block(full_text: str, art_label: str, max_chars: int = 4000) -> str:
    if not full_text or not art_label:
        return ""
    mnum = re.search(r"(제\s*\d{1,4}\s*조(?:\s*의\s*\d{1,3})?)", art_label)
    key = mnum.group(1) if mnum else art_label
    m = re.search(rf"^\s*{re.escape(key)}[^\n]*$", full_text, re.M) or \
        re.search(rf"^\s*{re.escape(key)}\b.*$", full_text, re.M)
    if not m:
        return ""
    start = m.start()
    n = _ART_HDR.search(full_text, m.end())
    end = n.start() if n else len(full_text)
    return full_text[start:end].strip()[:max_chars]

# -----------------------------------------
# 3) '제n조(의m)' → JO 6자리 변환
# -----------------------------------------
def jo_from_art_label(art_label: str) -> Optional[str]:
    m = re.search(r"제\s*(\d{1,4})\s*조(?:\s*의\s*(\d{1,3}))?", art_label or "")
    if not m: return None
    main = int(m.group(1))
    sub  = int(m.group(2)) if m.group(2) else 0
    return f"{main:04d}{sub:02d}"  # 83조 → 008300, 10조의2 → 001002

# -----------------------------------------
# 4) 최종: MST + (옵션)조문 라벨 → 본문
# -----------------------------------------
def fetch_article_block_by_mst(mst: str, art_label: Optional[str],
                               prefer: str = "JSON", efYd: Optional[str] = None,
                               timeout: float = 10.0) -> Tuple[str, str]:
    """
    - art_label이 있으면 JO 파라미터를 사용해 서버에서 조문만 받아온다(가장 안정).
    - JO가 불가/실패면 평문화 텍스트에서 조문 슬라이스.
    반환: (조문 텍스트 또는 미리보기, 원문 HTML 링크)
    """
    jo = jo_from_art_label(art_label) if art_label else None
    txt, used, url = fetch_law_detail_text(mst, prefer=prefer, jo=jo, efYd=efYd, timeout=timeout)

    block = txt
    if art_label and not jo:
        block = extract_article_block(txt, art_label)
    if not (block and block.strip()):
        alt = "HTML" if (prefer or "").upper() == "JSON" else "JSON"
        txt2, _, _ = fetch_law_detail_text(mst, prefer=alt, jo=jo, efYd=efYd, timeout=timeout)
        block = (extract_article_block(txt2, art_label) if (art_label and not jo) else txt2) or ""

    link = _build_drf_link(mst, typ="HTML", efYd=efYd, jo=jo)
    return (block or "").strip(), link
