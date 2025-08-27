# --- 1) DRF 상세 페이지에서 텍스트 추출 ---
def _fetch_detail_text_from_item(it: dict, max_chars: int = 3000, timeout: float = 4.0) -> str:
    """
    목록 아이템(it)의 '법령상세링크/상세링크'를 요청해 본문을 평문으로 추출.
    - type=XML이어도 괜찮지만 호환성을 위해 HTML로 강제 변환해 파싱.
    - 너무 길면 max_chars로 컷.
    """
    import re, requests
    from urllib.parse import urljoin
    try:
        link = (
            it.get("법령상세링크") or it.get("상세링크") or
            it.get("url") or it.get("link") or it.get("detail_url") or ""
        ).strip()
        if not link:
            # MST만 있을 때는 DRF 상세 URL을 구성
            mst = (it.get("MST") or it.get("mst") or it.get("LawMST") or "").strip()
            if not mst:
                return ""
            eff = (it.get("시행일자") or "").replace("-", "")
            link = f"/DRF/lawService.do?OC={LAW_API_OC}&target=law&MST={mst}&type=HTML" + (f"&efYd={eff}" if eff else "")

        # 절대 URL로 정규화
        url = normalize_law_link(link) if 'normalize_law_link' in globals() else urljoin("https://www.law.go.kr", link)
        url = re.sub(r"type=XML", "type=HTML", url)

        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            return ""
        # HTML → 텍스트
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        for bad in soup(["script", "style", "noscript"]):
            bad.extract()
        text = soup.get_text("\n", strip=True)
        # 노이즈 줄이기: 연속 공백 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception:
        return ""

# --- 2) 기존 프라이머를 확장: 상위 n개 법령의 '조문 발췌 캡슐'을 함께 주입 ---
def _summarize_laws_for_primer(law_items: list[dict], max_items: int = 5, with_articles: bool = True) -> str:
    """
    (기존) 법령 후보 요약 + (옵션) 각 후보의 DRF 상세에서 발췌한 본문 캡슐을 프롬프트에 포함.
    """
    if not law_items:
        return ""
    rows = []
    picks = law_items[:max_items]
    for i, d in enumerate(picks, 1):
        nm   = (d.get("법령명") or d.get("법령명한글") or d.get("행정규칙명") or d.get("자치법규명") or "").strip()
        kind = (d.get("법령구분") or d.get("법령구분명") or d.get("자치법규종류") or d.get("행정규칙종류") or "").strip()
        dept = (d.get("소관부처명") or d.get("지자체기관명") or "").strip()
        eff  = (d.get("시행일자") or "").strip()
        pub  = (d.get("공포일자") or "").strip()
        rows.append(f"{i}) {nm} ({kind}; {dept}; 시행 {eff}, 공포 {pub})")

    header = (
        "아래는 사용자 사건과 관련도가 높은 법령 후보 목록이다. "
        "답변을 작성할 때 적용 범위·책임주체·구성요건·의무·제재를 교차 검토하라.\n"
        + "\n".join(rows) +
        "\n가능하면 각 법령을 분리 소제목으로 정리하고, 핵심 조문(1~2개)만 간단 인용하라."
    )

    if not with_articles:
        return header

    capsules = []
    # 후보당 1500자씩만 가져와 토큰 폭주 방지
    per_item = 1500
    for d in picks:
        nm = (d.get("법령명") or d.get("법령명한글") or d.get("행정규칙명") or d.get("자치법규명") or "").strip() or "관련 법령"
        body = _fetch_detail_text_from_item(d, max_chars=per_item)
        if body:
            capsules.append(f"〈{nm} 조문(발췌)〉\n{body}")

    return header + ("\n\n" + "\n\n".join(capsules) if capsules else "")
