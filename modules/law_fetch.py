# === law_fetch.py (상단 import 아래) — OC 미사용 전환 스위치 ===
USE_DRF = False  # <- OC/DRF 전면 비활성화 (True로 바꾸면 다시 DRF 사용)

def _get_oc() -> str:
    """OC 미사용 모드에서는 항상 빈 문자열을 반환."""
    return ""


def _build_drf_link(
    mst: str,
    typ: str = "HTML",
    *,
    efYd: Optional[str] = None,
    lang: str = "KO",
    jo: Optional[str] = None
) -> str:
    # DRF 비활성화: 링크 자체를 만들지 않음
    if not USE_DRF:
        return ""
    base = "https://www.law.go.kr/DRF/lawService.do"
    q = {
        "OC": _get_oc(),   # 빈 문자열이더라도 USE_DRF가 False면 위에서 이미 차단됨
        "target": "law",
        "type": typ,
    }
    if mst:  q["MST"] = str(mst)
    if efYd: q["efYd"] = efYd
    if lang: q["LANG"] = lang
    if jo:   q["JO"] = jo
    return base + "?" + urlencode(q, doseq=False, encoding="utf-8")


def find_mst_by_law_name(
    law_name: str,
    efYd: Optional[str] = None,
    timeout: float = 8.0
) -> str:
    # DRF 비활성화: 바로 빈 값
    if not USE_DRF:
        return ""
    law_name = (law_name or "").strip()
    if not law_name:
        return ""
    base = "https://www.law.go.kr/DRF/lawSearch.do"
    q = {
        "OC": _get_oc(),
        "target": "law",
        "type": "JSON",
        "query": law_name,
    }
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

    for it in items:
        nm = (it.get("법령명한글") or it.get("법령명") or "").strip()
        if nm == law_name:
            return (it.get("법령일련번호") or it.get("MST") or "").strip()
    for it in items:
        m = (it.get("법령일련번호") or it.get("MST") or "").strip()
        if m:
            return m
    return ""


def _drf_get(
    mst: str,
    *,
    typ: str = "JSON",
    jo: Optional[str] = None,
    efYd: Optional[str] = None,
    timeout: float = 10.0,
) -> Tuple[str, str]:
    # DRF 비활성화: 호출하지 않고 즉시 빈 값
    if not USE_DRF:
        return "", ""
    url = _build_drf_link(mst, typ=typ, efYd=efYd, jo=jo)
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*", "Referer": "https://www.law.go.kr/DRF/index.do"},
        )
    except Exception:
        return "", url
    if not (200 <= r.status_code < 300):
        return "", url
    text = r.text or ""
    head = text[:2000]
    bad_signatures = (
        "접근이 제한되었습니다",
        "페이지 접속에 실패하였습니다",
        "URL에 MST 요청값이 없습니다",
        "일치하는 법령이 없습니다",
        "로그인한 사용자 OC만 사용가능합니다",
    )
    if any(sig in head for sig in bad_signatures):
        return "", url
    if typ.upper() == "JSON":
        ct = (r.headers.get("Content-Type") or "").lower()
        if "json" not in ct and "<html" in head.lower():
            return "", url
    return text, url


def fetch_law_detail_text(
    mst: str, *, prefer: str = "JSON", jo: Optional[str] = None, efYd: Optional[str] = None, timeout: float = 10.0
) -> tuple[str, str, str]:
    # DRF 비활성화: 본문/링크 모두 제공하지 않음 (딥링크 스크랩 경로가 대신 처리)
    if not USE_DRF:
        return "", prefer.upper(), ""
    order = [prefer.upper(), "HTML" if prefer.upper()=="JSON" else "JSON"]
    last_url = ""
    for typ in order:
        raw, last_url = _drf_get(mst, typ=typ, jo=jo, efYd=efYd, timeout=timeout)
        txt = _extract_text_from_json(raw) if typ=="JSON" else _extract_text_from_html(raw)
        if len(txt.strip()) >= 30:
            return txt, typ, last_url
    return "", order[-1], last_url


def fetch_article_block_by_mst(
    mst: str,
    art_label: Optional[str],
    prefer: str = "JSON",
    efYd: Optional[str] = None,
    timeout: float = 10.0
) -> tuple[str, str]:
    # DRF 비활성화: DRF 경로를 완전히 건너뛰고 빈 결과 반환
    # (본문·링크는 plan_executor의 딥링크 스크랩 경로에서 보장됨)
    if not USE_DRF:
        return "", ""
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
