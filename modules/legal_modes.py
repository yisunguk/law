# --- law_fetch.py: 드롭인 패치 (REPLACE) ---

# 1) JSON → 풀텍스트 평문화: "제n조(제목)" 머리줄을 복원
def _extract_text_from_json(text: str) -> tuple[str, dict]:
    try:
        data = json.loads(text)
    except Exception:
        return "", {}

    info = {}

    def _walk_pairs(v):
        if isinstance(v, dict):
            for k, x in v.items():
                yield k, x
                yield from _walk_pairs(x)
        elif isinstance(v, list):
            for x in v:
                yield from _walk_pairs(x)

    # 법령명 추출
    for k, v in _walk_pairs(data):
        if k in ("법령명한글", "법령명", "lawName") and isinstance(v, str) and v.strip():
            info["law_name"] = v.strip()
            break

    # 조문 트리 → 평문화
    lines = []

    def _emit_article(n):
        if not isinstance(n, dict):
            return
        num = (n.get("조문번호") or n.get("조문번호_한글") or "").strip()
        title = (n.get("조문제목") or "").strip()
        body = (n.get("조문내용") or n.get("내용") or n.get("text") or "").strip()
        head = (f"{num}{f'({title})' if title else ''}").strip()
        if head:
            lines.append(head)
        if body:
            lines.append(body)

        # 하위(항/호/목/children 등 일반 케이스 지원)
        for key in ("항", "호", "목", "조문", "children", "Items"):
            v = n.get(key)
            if isinstance(v, list):
                for c in v:
                    _emit_article(c)
            elif isinstance(v, dict):
                _emit_article(v)

    def _recur(x):
        if isinstance(x, dict):
            _emit_article(x)
            for v in x.values():
                _recur(v)
        elif isinstance(x, list):
            for v in x:
                _recur(v)

    _recur(data)

    if lines:
        flat = "\n".join(lines)
        return flat[:120000], info  # 넉넉한 상한
    # 폴백(기존 휴리스틱)
    texts = []
    for k, v in _walk_pairs(data):
        if isinstance(v, str) and k in {"조문내용", "조문", "내용", "text"} and len(v.strip()) >= 30:
            texts.append(v.strip())
            if len(texts) >= 3:
                break
    return ("\n".join(texts[:3]) if texts else ""), info


# 2) HTML 파서 선택자 보강(+ 상한 확장)
def _extract_text_from_html(text: str) -> str:
    soup = BeautifulSoup(text, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    main = soup.select_one(
        "#conScroll, .conScroll, .lawSeView, .lawView, "
        "#contentBody, #content, #wrap, pre, body"
    )
    out = (main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True))
    return out[:12000]


# 3) 조문 블록 슬라이스(기존 유지)
_ART_HDR = re.compile(r'^\s*제\d{1,4}조(의\d{1,3})?\s*', re.M)
def extract_article_block(full_text: str, art_label: str, max_chars: int = 4000) -> str:
    if not full_text or not art_label:
        return ""
    m = re.search(rf'^\s*{re.escape(art_label)}[^\n]*$', full_text, re.M)
    if not m:
        m = re.search(rf'^\s*{re.escape(art_label)}\s*', full_text, re.M)
    if not m:
        return ""
    start = m.start()
    n = _ART_HDR.search(full_text, m.end())
    end = n.start() if n else len(full_text)
    return full_text[start:end].strip()[:max_chars]


# 4) DRF 본문 조회 + 짧은 본문이면 자동 폴백(JSON/HTML 교차)
def fetch_article_block_by_mst(
    mst: str,
    art_label: str | None,
    prefer: str = "JSON",
    timeout: float = 8.0
) -> tuple[str, str]:
    """
    - prefer 포맷으로 먼저 시도
    - 결과가 없거나 너무 짧으면 반대 포맷으로 1회 폴백
    - art_label 없으면 앞부분 일부(미리보기) 반환
    """
    txt, used, _ = fetch_law_detail_text(mst, prefer=prefer)
    block = ""
    if txt:
        block = extract_article_block(txt, art_label) if art_label else txt[:2000]

    # 길이 기준(짧으면 실패 간주)으로 폴백
    if (not block) or (len(block) < 80):
        alt = "JSON" if (prefer or "").upper() == "HTML" else "HTML"
        txt2, _, _ = fetch_law_detail_text(mst, prefer=alt)
        if txt2:
            block2 = extract_article_block(txt2, art_label) if art_label else txt2[:2000]
            if len((block2 or "")) >= max(80, len(block or "")):
                block = block2

    link = _build_drf_link(mst, typ="HTML")
    return (block or "").strip(), link
