# --- modules/plan_executor.py (PATCH) ---
# 파일 상단 어느 위치든 한 번만 추가(이미 있다면 생략 가능)
import logging, time

logger = logging.getLogger("lawbot.deeplink")
if not logger.handlers:
    # 라이브러리 성격 고려: 기본 레벨만 설정(앱에서 원하는 레벨로 올리면 됨)
    logger.setLevel(logging.INFO)

def _dbg(msg: str):
    """streamlit이 있으면 화면에도, 없으면 로거에만 남깁니다."""
    try:
        import streamlit as st  # type: ignore
        # st.echo/st.write는 앱 레이아웃에 맞춰 사용하세요.
        st.write("🔎 [deeplink]", msg)
    except Exception:
        logger.info(msg)


def _scrape_deeplink(law_name: str, article_label: str, timeout: float = 6.0) -> tuple[str, str]:
    """
    한글 조문 딥링크 페이지를 스크랩해 '요청 조문'만 잘라낸다.
    반환: (조문텍스트, 표시링크)
    - 디버그 로그: URL, 상태코드, HTML 길이, 컨테이너 길이, 슬라이스 길이/성공여부
    """
    # 방어 코드: 인자 확인
    law_name = (law_name or "").strip()
    article_label = (article_label or "").strip()
    if not (law_name and article_label):
        _dbg(f"[skip] 입력 누락 law='{law_name}', article='{article_label}'")
        return "", ""

    # URL 생성
    try:
        from .linking import make_pretty_article_url  # type: ignore
    except Exception:
        try:
            from linking import make_pretty_article_url  # type: ignore
        except Exception:
            make_pretty_article_url = None  # type: ignore

    if not make_pretty_article_url:
        _dbg("[error] make_pretty_article_url 미가용")
        return "", ""

    url = make_pretty_article_url(law_name, article_label)
    _dbg(f"[request] {url} (timeout={timeout}s)")

    # HTTP 요청
    t0 = time.time()
    try:
        import requests
        from bs4 import BeautifulSoup

        r = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
        )
        dt = (time.time() - t0) * 1000
        html = r.text or ""
        _dbg(f"[response] status={r.status_code}, bytes≈{len(html)}, elapsed={dt:.1f}ms")

        # 상단 경고 시그널 검사
        head = html[:4000]
        bad_signs = ("존재하지 않는 조문", "해당 한글주소명을 찾을 수 없습니다", "접근이 제한되었습니다")
        if not (200 <= r.status_code < 400):
            _dbg(f"[error] HTTP status={r.status_code} (링크 표시만 반환)")
            return "", url
        if any(sig in head for sig in bad_signs):
            _dbg(f"[warn] 페이지 경고 감지: {[s for s in bad_signs if s in head]}")
            return "", url

        # 본문 컨테이너 추출
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
        _dbg(f"[parse] container_text_len={len(full_text)}")

        # 조문 블록만 슬라이스
        try:
            # 우선 정식 슬라이서 사용
            from .law_fetch import extract_article_block as _slice_article  # type: ignore
        except Exception:
            try:
                from law_fetch import extract_article_block as _slice_article  # type: ignore
            except Exception:
                _slice_article = None  # type: ignore

        piece = ""
        if _slice_article:
            piece = _slice_article(full_text, article_label) or ""

        # 보조 정규식 슬라이스
        if not piece:
            import re
            num = re.sub(r"\D", "", article_label)
            m = re.search(rf"(제{num}조(?:의\d+)?[\s\S]*?)(?=\n제\d+조|\n부칙|\Z)", full_text)
            piece = (m.group(1) if m else "").strip()

        _dbg(f"[slice] label='{article_label}', piece_len={len(piece)}"
             + (" ✅" if piece else " ❌"))

        return (piece[:4000] if piece else ""), url

    except Exception as e:
        _dbg(f"[exception] {type(e).__name__}: {e}")
        return "", url
