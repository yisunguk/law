# modules/plan_executor.py
from __future__ import annotations
from typing import Dict, Any, Tuple
import re, logging
# [ADD ①] 전 분야 리소스 본문 가져오기 유틸
import re, requests
from bs4 import BeautifulSoup

# linking 경로 호환
try:
    from modules.linking import build_korean_resource_url as make_pretty_resource_url, make_pretty_article_url
except Exception:
    from linking import build_korean_resource_url as make_pretty_resource_url, make_pretty_article_url

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

def _fetch_html_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=_HTTP_HEADERS, timeout=20)
    # 인코딩 안전장치
    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1"):
        r.encoding = "utf-8"
    return BeautifulSoup(r.text, "html.parser")

def _pick_main_node(soup: BeautifulSoup):
    # law.go.kr 공통 본문 컨테이너 후보들 (없으면 body)
    return (
        soup.select_one("#contentArea")
        or soup.select_one("#conTop")
        or soup.select_one("#conTable")
        or soup.select_one("#container")
        or soup.body
        or soup
    )

def _clean_lines(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    # 빈 줄 과다 제거
    out, prev_blank = [], False
    for ln in lines:
        is_blank = (ln == "")
        if is_blank and prev_blank:
            continue
        out.append(ln)
        prev_blank = is_blank
    return "\n".join(out).strip()

# ── 조문 라벨 표준화 + 블록 추출 ────────────────────────────────────────
_ART_RE = re.compile(r"제?\s*(\d{1,4})\s*조(?:\s*의\s*(\d{1,3}))?", re.I)

def _norm_article_label(lbl: str) -> str:
    m = _ART_RE.search(lbl or "")
    if not m: return (lbl or "").strip()
    n, ui = m.group(1), m.group(2)
    return f"제{n}조" + (f"의{ui}" if ui else "")

def _extract_article_block(full_text: str, art_label: str) -> str | None:
    """
    페이지 전체 텍스트에서 '제83조(…)' 블록만 잘라냅니다.
    다음 '제n조' 또는 '부칙' 이전까지를 본문으로 봅니다.
    """
    target = _norm_article_label(art_label)
    # ^제83조(…)\n  ...  (?=^제n조|^부칙|$)
    pat = re.compile(
        rf"(^\s*{re.escape(target)}[^\n]*\n)(.*?)(?=^\s*제\d{{1,4}}조(?:\s*의\s*\d{{1,3}})?\b|^\s*부칙\b|$\Z)",
        re.M | re.S,
    )
    m = pat.search(full_text or "")
    if not m:
        return None
    head, body = m.group(1), m.group(2)
    return _clean_lines((head + body).strip())

# ── 전 분야 리소스 본문 파서(핵심) ───────────────────────────────────────
def fetch_resource_text(
    kind: str,
    title: str,
    *,
    article_label: str | None = None,
    pub_no: str | None = None,
    pub_date: str | None = None,
    eff_date: str | None = None,
    annex_label: str | None = None,
) -> dict:
    """
    law.go.kr 전 분야(1~35) 리소스를 열람해 텍스트를 반환합니다.
    - 법령류(+조문): 조문 블록만 정밀 추출
    - 그 외(판례/재결/조약/해석 등): 메인 본문 컨테이너 텍스트를 제너릭 추출
    반환: {type, kind, title, article_label?, url, text}
    """
    url = make_pretty_resource_url(
        kind, title,
        article_label=article_label,
        pub_no=pub_no, pub_date=pub_date, eff_date=eff_date,
        annex_label=annex_label,
    )

    # 1) 법령/자치법규 계열 + 조문 => 조문 블록만
    if (kind in ("법령", "법률", "시행령", "시행규칙", "자치법규")) and article_label:
        soup = _fetch_html_soup(url)
        main = _pick_main_node(soup)
        full_text = _clean_lines(main.get_text("\n"))
        art_text = _extract_article_block(full_text, article_label) or full_text
        return {
            "type": "resource", "kind": kind, "title": title,
            "article_label": _norm_article_label(article_label),
            "url": url, "text": art_text
        }

    # 2) 그 외 분야: 페이지 본문 전체를 제너릭 추출
    soup = _fetch_html_soup(url)
    main = _pick_main_node(soup)
    text = _clean_lines(main.get_text("\n"))
    return {"type": "resource", "kind": kind, "title": title, "url": url, "text": text}

logger = logging.getLogger("lawbot.plan_executor")

# ── helpers ─────────────────────────────────────────────────────────

def _make_pretty_article_url(law: str, art: str) -> str:
    """가능하면 linking 모듈을 쓰고, 없으면 한글 경로로 직접 구성."""
    try:
        from .linking import make_pretty_article_url  # type: ignore
        return make_pretty_article_url(law, art)
    except Exception:
        try:
            from linking import make_pretty_article_url  # type: ignore
            return make_pretty_article_url(law, art)
        except Exception:
            return f"https://www.law.go.kr/법령/{law}/{art}"

# ✅ [REPLACE] modules/plan_executor.py : _slice_article
def _slice_article(full_text: str, article_label: str) -> str:
    """
    페이지 전체 텍스트에서 해당 조문 블록만 정밀 추출.
    - '제83조' 또는 '제83조의2' 모두 지원
    """
    import re
    label = (article_label or "").strip()
    if not (full_text and label):
        return ""

    # 1) 표준형 라벨 파싱
    m = re.search(r'제\s*(\d{1,4})\s*조(?:\s*의\s*(\d{1,3}))?', label)
    if m:
        main = int(m.group(1))
        sub  = m.group(2)
        if sub:
            # 제83조의2 형태
            pat = rf"(?m)^(제\s*{main}\s*조\s*의\s*{int(sub)}\b[\s\S]*?)(?=^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\b|\n부칙|\Z)"
        else:
            # 제83조 (단, 뒤의 '의' 조문까지 잡아먹지 않도록 (?!\s*의))
            pat = rf"(?m)^(제\s*{main}\s*조(?!\s*의)\b[\s\S]*?)(?=^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\b|\n부칙|\Z)"
        m2 = re.search(pat, full_text)
        if m2:
            return m2.group(1).strip()

    # 2) 라벨 그대로 1차 시도 (비표준 입력 대비)
    m3 = re.search(rf"(?m)^({re.escape(label)}[^\n]*\n(?:.+\n)*?)(?=^\s*제\d+조|\n부칙|\Z)", full_text)
    return (m3.group(1).strip() if m3 else "")


def _scrape_deeplink(law: str, art: str, timeout: float = 6.0) -> Tuple[str, str]:
    """법제처 한글 주소(딥링크) 페이지를 스크랩해서 해당 조문만 추출."""
    url = _make_pretty_article_url(law, art)
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(
            url, timeout=timeout, allow_redirects=True,
            headers={
                "User-Agent":"Mozilla/5.0",
                "Accept":"text/html,application/xhtml+xml",
                "Accept-Language":"ko-KR,ko;q=0.9",
            },
        )
        html = r.text or ""
        soup = BeautifulSoup(html, "lxml")
        main = (soup.select_one("#contentBody") or soup.select_one("#conBody")
                or soup.select_one("#conScroll") or soup.select_one(".conScroll")
                or soup.select_one("#content") or soup)
        full_text = (main.get_text("\n", strip=True) or "").strip()
        piece = _slice_article(full_text, art)
        return (piece[:4000] if piece else ""), url
    except Exception:
        # 네트워크/파서 문제 시에도 링크만이라도 반환
        return "", url

def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET_ARTICLE + GET_RESOURCE 처리
    - 조문 딥링크 스크랩(법령/조문)
    - 전 분야(판례/재결/조약/해석 등) 원문 가져오기
    """
    action = ((plan or {}).get("action") or "").upper()

    # 1) 기존: 조문 본문 추출
    if action == "GET_ARTICLE":
        law = (plan.get("law_name") or "").strip()
        art = (plan.get("article_label") or "").strip()
        body, url = _scrape_deeplink(law, art)
        return {
            "type": "article",
            "law": law,
            "article_label": art,
            "title": "",
            "body_text": body,
            "clauses": [],
            "source_url": url,
        }

    # 2) 신규: 전 분야 리소스 본문 추출
    elif action == "GET_RESOURCE":
        # 한글 키도 허용 (LLM이 {"분야","제목","조문"...}을 낼 수 있으므로)
        kind  = plan.get("kind")  or plan.get("분야")  or ""
        title = plan.get("title") or plan.get("제목")  or ""

        res = fetch_resource_text(
            kind, title,
            article_label = plan.get("article_label") or plan.get("조문"),
            pub_no   = (plan.get("pub_no")   or plan.get("공포번호") or plan.get("발령번호")
                        or plan.get("사건번호") or plan.get("의결번호") or plan.get("재결번호")
                        or plan.get("조약번호") or plan.get("청구번호") or plan.get("안건번호")),
            pub_date = (plan.get("pub_date") or plan.get("공포일자") or plan.get("발령일자")
                        or plan.get("판결일자") or plan.get("의결일자") or plan.get("결정일자")
                        or plan.get("발효일자")),
            eff_date = plan.get("eff_date") or plan.get("시행일자"),
            annex_label = plan.get("annex_label") or plan.get("별표") or plan.get("서식"),
        )
        return res  # {"type":"resource", "kind":..., "url":..., "text":...}

    # 3) 그 외
    else:
        return {
            "type": "noop",
            "action": action or "QUICK",
            "message": "unsupported action",
        }

