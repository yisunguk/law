# law_fetch.py  (상단 import 옆에)
import os, json, re, requests
from bs4 import BeautifulSoup
from lxml import etree

HEADERS_DRF = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.law.go.kr/DRF/index.do",
    "X-Requested-With": "XMLHttpRequest",
}

def _get_oc() -> str:
    return (globals().get("LAW_API_OC") or os.getenv("LAW_API_OC") or "").strip()

def _drf_params(mst: str, typ: str, efYd: str | None = None) -> dict:
    p = {"OC": _get_oc(), "target": "law", "MST": str(mst), "type": typ}
    if efYd:
        p["efYd"] = efYd.replace("-", "")
    return p

def drf_fetch(mst: str, typ: str = "JSON", timeout: float = 10.0) -> requests.Response:
    url = "https://www.law.go.kr/DRF/lawService.do"
    return requests.get(url, params=_drf_params(mst, typ), headers=HEADERS_DRF, timeout=timeout)

def _extract_text_from_json(text: str) -> tuple[str, dict]:
    try:
        data = json.loads(text)
    except Exception:
        return "", {}
    # 간단 추출
    def walk(v):
        if isinstance(v, dict):
            for k,x in v.items():
                yield k,x; yield from walk(x)
        elif isinstance(v, list):
            for x in v: yield from walk(x)
    law_name = ""
    for k,v in walk(data):
        if k in ("법령명한글","법령명","lawName") and isinstance(v,str) and v.strip():
            law_name = v.strip(); break
    texts = []
    for k,v in walk(data):
        if isinstance(v,str) and len(v.strip())>=30 and k in {"조문내용","조문","내용","text","조문본문"}:
            texts.append(v.strip()); 
            if len(texts)>=3: break
    if not texts:
        for k,v in walk(data):
            if isinstance(v,str) and 100<=len(v.strip())<=4000:
                texts.append(v.strip()); 
                if len(texts)>=3: break
    return "\n".join(texts[:3]), {"law_name": law_name}

def _extract_text_from_xml(text: str) -> str:
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except Exception:
        return ""
    return "\n".join(t.strip() for t in root.itertext() if t and t.strip())[:3000]

def _extract_text_from_html(text: str) -> str:
    soup = BeautifulSoup(text, "lxml")
    for tag in soup(["script","style","noscript"]): tag.decompose()
    main = soup.select_one("#conScroll, .conScroll, .lawView, #content, body")
    return (main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True))[:3000]

def fetch_law_detail_text(mst: str, prefer: str = "JSON") -> tuple[str, str, dict]:
    order = ["JSON","XML","HTML"] if prefer.upper()=="JSON" else ["XML","JSON","HTML"]
    for typ in order:
        r = drf_fetch(mst, typ=typ)
        ctype = (r.headers.get("content-type") or "").lower()
        text  = r.text or ""
        if "json" in ctype or (typ=="JSON" and text.strip().startswith("{")):
            s, info = _extract_text_from_json(text)
            if s: return s, "JSON", info
        elif "xml" in ctype or (typ=="XML" and text.strip().startswith("<")):
            s = _extract_text_from_xml(text)
            if s: return s, "XML", {}
        else:
            s = _extract_text_from_html(text)
            if s: return s, "HTML", {}
    return "", "", {}

def _build_drf_link(mst: str, typ: str = "HTML", efYd: str | None = None) -> str:
    from urllib.parse import urlencode, quote
    oc = _get_oc()
    if not oc: return ""
    return "https://www.law.go.kr/DRF/lawService.do?" + urlencode(_drf_params(mst, typ, efYd), quote_via=quote)

def _summarize_laws_for_primer(law_items: list[dict], max_items: int = 6) -> str:
    if not law_items: return ""
    blocks = []
    for it in law_items[:max_items]:
        mst = str(it.get("MST") or it.get("mst") or it.get("법령ID") or "").strip()
        if not mst: continue
        ef  = (it.get("시행일자") or it.get("efYd") or "").strip()
        law = (it.get("법령명한글") or it.get("법령명") or "").strip()
        text, used, info = fetch_law_detail_text(mst, prefer="JSON")
        if not law: law = (info.get("law_name") or mst)
        link = _build_drf_link(mst, typ="HTML", efYd=ef)
        snippet = (text or "").replace("\r","").strip()
        if len(snippet) > 3000: snippet = snippet[:3000] + " …"
        block = f"• 법령: {law}" + (f" (시행 {ef})" if ef else "")
        if link:   block += f"\n  - 본문 보기: {link}"
        if snippet: block += f"\n  - 발췌: {snippet}"
        blocks.append(block)
    return "【법령 본문 캡슐】\n" + "\n\n".join(blocks) if blocks else ""
# --- ⬇️ add: 조문 블록 추출 & DRF 한 번에 ---
import re as _re

_ART_HDR = _re.compile(r'^\s*제\d{1,4}조(의\d{1,3})?\s*', _re.M)

def extract_article_block(full_text: str, art_label: str, max_chars: int = 4000) -> str:
    """
    DRF에서 받은 전체 텍스트에서 '제83조(…)' 같은 조문 블록만 잘라 반환.
    다음 조문 헤더(제n조) 직전까지를 포함.
    """
    if not full_text or not art_label:
        return ""
    m = _re.search(rf'^\s*{_re.escape(art_label)}[^\n]*$', full_text, _re.M)
    if not m:
        # 괄호 제목 없이 '제83조'만 있는 경우까지 커버
        m = _re.search(rf'^\s*{_re.escape(art_label)}\s*', full_text, _re.M)
    if not m:
        return ""
    start = m.start()
    n = _ART_HDR.search(full_text, m.end())
    end = n.start() if n else len(full_text)
    block = full_text[start:end].strip()
    return block[:max_chars]

def fetch_article_block_by_mst(mst: str, art_label: str, prefer: str = "JSON") -> tuple[str, str]:
    """
    MST로 DRF를 치고 해당 조문만 잘라 반환.
    return: (조문텍스트, HTML보기링크)
    """
    txt, used, _ = fetch_law_detail_text(mst, prefer=prefer)
    if not txt:
        return "", ""
    art = extract_article_block(txt, art_label)
    link = _build_drf_link(mst, typ="HTML")
    return art, link
# --- add: 조문 블록 추출 + 단건 조회 helper (modules/law_fetch.py 맨 아래에 붙이기) ---
import re as _re

_ART_HDR = _re.compile(r'^\s*제\d{1,4}조(의\d{1,3})?\s*', _re.M)

def extract_article_block(full_text: str, art_label: str, max_chars: int = 4000) -> str:
    """
    DRF에서 받은 전체 텍스트에서 '제83조(…)' 같은 조문 블록만 잘라 반환.
    다음 조문 헤더(제n조) 직전까지 포함.
    """
    if not full_text or not art_label:
        return ""
    # ① 완전 라벨 (예: "제83조(벌점제도)") 우선
    m = _re.search(rf'^\s*{_re.escape(art_label)}[^\n]*$', full_text, _re.M)
    if not m:
        # ② 괄호 제목 없이 "제83조"만 있는 경우도 허용
        m = _re.search(rf'^\s*{_re.escape(art_label)}\s*', full_text, _re.M)
    if not m:
        return ""
    start = m.start()
    # 다음 조문 헤더가 나오기 전까지 자르기
    n = _ART_HDR.search(full_text, m.end())
    end = n.start() if n else len(full_text)
    block = full_text[start:end].strip()
    return block[:max_chars]

def fetch_article_block_by_mst(mst: str, art_label: str, prefer: str = "JSON", timeout: float = 8.0) -> tuple[str, str]:
    """
    MST를 DRF로 조회해 해당 '제n조' 조문만 잘라 반환.
    return: (조문텍스트, HTML원문링크)
    """
    # 이 파일에 이미 있는 함수들을 재사용합니다.
    txt, used, _ = fetch_law_detail_text(mst, prefer=prefer)
    if not txt:
        return "", ""
    block = extract_article_block(txt, art_label)
    link = _build_drf_link(mst, typ="HTML")
    return (block or "").strip(), link
