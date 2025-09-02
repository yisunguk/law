# 교체블록: plan_executor.py 내 execute_plan 함수 전체 교체
from typing import Any, Dict

try:
    from .law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label as _jo_from_label,
        find_mst_by_law_name,
    )
except Exception:  # pragma: no cover
    from law_fetch import (
        fetch_article_block_by_mst,
        jo_from_art_label as _jo_from_label,
        find_mst_by_law_name,
    )

# linking 모듈은 선택적
try:
    from .linking import make_pretty_article_url  # 사람이 읽기 좋은 /법령/법령명/제N조
except Exception:
    try:
        from linking import make_pretty_article_url
    except Exception:
        make_pretty_article_url = None  # type: ignore

# === [REPLACE] modules/plan_executor.py : _scrape_deeplink 함수 교체 ===
def _scrape_deeplink(law_name: str, article_label: str, timeout: float = 6.0) -> tuple[str, str]:
    """
    한글 조문 딥링크 페이지에서 텍스트를 가져온 뒤,
    law_fetch.extract_article_block()으로 '해당 조문'만 잘라서 반환한다.
    """
    if not (law_name and article_label and make_pretty_article_url):
        return "", ""
    try:
        import requests
        from bs4 import BeautifulSoup
        try:
            # 슬라이싱 유틸(있으면 사용)
            from .law_fetch import extract_article_block as _slice_article
        except Exception:
            from law_fetch import extract_article_block as _slice_article  # type: ignore

        url = make_pretty_article_url(law_name, article_label)
        r = requests.get(
            url, timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            allow_redirects=True,
        )
        if not (200 <= r.status_code < 400):
            return "", url

        html = r.text or ""
        # 유지보수/차단/오류 페이지 방어
        head = html[:4000]
        bad = ("존재하지 않는 조문", "해당 한글주소명을 찾을 수 없습니다",
               "페이지 접속에 실패하였습니다", "접근이 제한되었습니다")
        if any(b in head for b in bad):
            return "", url

        soup = BeautifulSoup(html, "lxml")
        main = (
            soup.select_one("#contentBody")
            or soup.select_one("#conBody")
            or soup.select_one("#conScroll")
            or soup.select_one(".conScroll")
            or soup.select_one("#content")
            or soup
        )
        full_text = (main.get_text("\n", strip=True) or "").strip()

        # ★ 핵심: 페이지 전체가 아니라 '요청 조문'만 슬라이스
        try:
            piece = _slice_article(full_text, article_label) or ""
        except Exception:
            piece = ""

        if not piece:
            # 슬라이스 실패 시 간이 정규식으로라도 구간 추출
            import re
            art = (article_label or "").strip()
            num = re.sub(r"\D", "", art)  # 83
            # '제83조' ~ 다음 '제84조' 직전까지
            p = re.compile(rf"(제{num}조(?:의\d+)?[^\\n]*)(.*?)(?=\\n제\d+조|\\n부칙|\\Z)", re.S)
            m = p.search(full_text)
            if m:
                piece = (m.group(0) or "").strip()

        return (piece[:4000] if piece else ""), url
    except Exception:
        return "", ""



def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM 라우터가 만든 plan을 실행한다.
    - DRF(JSON→HTML) 우선
    - 실패/차단 시 한글주소(딥링크) 스크랩을 'MST 유무와 무관하게' 최후 폴백으로 수행
    """
    action = ((plan or {}).get("action") or "").upper()
    if action != "GET_ARTICLE":
        return {"type": "noop", "action": action or "QUICK",
                "message": "execute_plan: GET_ARTICLE 외 액션은 외부 경로에서 처리하세요."}

    law_name  = (plan.get("law_name") or "").strip()
    art_label = (plan.get("article_label") or "").strip()
    mst       = (plan.get("mst") or "").strip()
    jo        = (plan.get("jo") or "").strip()
    efYd_raw  = (plan.get("efYd") or plan.get("eff_date") or "").strip()
    efYd      = "".join(ch for ch in efYd_raw if ch.isdigit())

    # JO 보강 ('제83조' → '008300')
    if (not jo) and art_label:
        try:
            jo = _jo_from_label(art_label) or ""
        except Exception:
            jo = ""

    # MST 보강(가능하면): DRF 검색 → 없으면 그대로 진행
    if (not mst) and law_name:
        try:
            mst = find_mst_by_law_name(law_name, efYd=efYd) or ""
        except Exception:
            mst = ""

    text, link = "", ""

    # 1) DRF(JSON→HTML) 본문 시도 (MST가 있으면)
    if mst:
        t1, l1 = fetch_article_block_by_mst(mst, art_label, prefer="JSON", efYd=efYd)
        if not (t1 and t1.strip()):
            t1b, l1b = fetch_article_block_by_mst(mst, art_label, prefer="HTML", efYd=efYd)
            if t1b and t1b.strip():
                t1, l1 = t1b.strip(), l1b
        text, link = (t1 or "").strip(), (l1 or "")

    # 2) 🔴 최후 폴백: DRF가 비었거나 실패한 경우, 조문 딥링크 스크랩 (MST 유무 무관)
    if not (text and text.strip()):
        t2, l2 = _scrape_deeplink(law_name, art_label)
        if t2:
            text, link = t2, l2
        elif not link:  # 본문은 못 가져와도 링크는 제공
            # 딥링크가 실패하면 법령 메인이라도 돌려줌
            if make_pretty_article_url:
                try:
                    link = make_pretty_article_url(law_name, art_label)
                except Exception:
                    link = ""

    return {
        "type": "article",
        "law": law_name, "article": art_label,
        "mst": mst, "jo": jo, "efYd": efYd,
        "text": (text or "").strip(), "link": link or "",
    }
