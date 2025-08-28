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
        if len(snippet) > 800: snippet = snippet[:800] + " …"
        block = f"• 법령: {law}" + (f" (시행 {ef})" if ef else "")
        if link:   block += f"\n  - 본문 보기: {link}"
        if snippet: block += f"\n  - 발췌: {snippet}"
        blocks.append(block)
    return "【법령 본문 캡슐】\n" + "\n\n".join(blocks) if blocks else ""
