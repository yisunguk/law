# modules/linking.py — COMPLETE (간결/안정 버전)
import re
from urllib.parse import quote
import os, contextlib, re, requests, html

# 흔한 축약어를 정식 명칭으로 치환
ALIAS_MAP = {"형소법":"형사소송법","민소법":"민사소송법","민집법":"민사집행법"}

def _norm_law(n: str) -> str:
    n = (n or "").strip()
    return ALIAS_MAP.get(n, n)

# ✅ [PATCH] modules/linking.py : _norm_art 교체
def _norm_art(s: str) -> str:
    """
    다양한 입력을 '제N조' 또는 '제N조의M'로 표준화.
    허용 예: '83', '제83조', '83조', '제 83 조', '83조의2', '제83조의 2'
    """
    s = (s or "").strip()

    import re
    # 1) '제N조의M' / '제 N 조 의 M'
    m = re.fullmatch(r'제?\s*(\d{1,4})\s*조\s*의\s*(\d{1,3})', s)
    if m:
        return f"제{int(m.group(1))}조의{int(m.group(2))}"

    # 2) 'N조의M' (제 생략)
    m = re.fullmatch(r'(\d{1,4})\s*조\s*의\s*(\d{1,3})', s)
    if m:
        return f"제{int(m.group(1))}조의{int(m.group(2))}"

    # 3) '제N조' / '제 N 조'
    m = re.fullmatch(r'제?\s*(\d{1,4})\s*조', s)
    if m:
        return f"제{int(m.group(1))}조"

    # 4) 숫자만: '83' → '제83조'
    if s.isdigit():
        return f"제{int(s)}조"

    # 5) 기타는 원본 유지(이미 표준형일 수 있음)
    return s

def make_pretty_article_url(law_name: str, article_label: str) -> str:
    # 한글 법령/조문 직링크
    return f"https://law.go.kr/법령/{quote(_norm_law(law_name))}/{quote(_norm_art(article_label))}"

# === LAW.GO.KR Korean URL builders ==================================
# URL 인코딩: 괄호/콤마는 경로에 남겨야 함
def _q(s: str) -> str:
    return quote((s or "").strip(), safe="(),-._~/")

# 공백/괄호 등 정리
_KOR_TRIM = re.compile(r"[「」『』\[\]（）()]")
def _clean(s: str) -> str:
    s = (s or "").strip()
    s = _KOR_TRIM.sub("", s)
    s = re.sub(r"\s+", " ", s)
    return s

# '제83조', '83조', '제 83 조의2' → '제83조(의2 포함)'
_ART = re.compile(r"제?\s*(\d{1,4})\s*조(?:\s*의\s*(\d{1,3}))?", re.I)
def _norm_article(lbl: str) -> str:
    m = _ART.search(lbl or "")
    if not m:
        return (lbl or "").strip()
    n, ui = m.group(1), m.group(2)
    return f"제{n}조" + (f"의{ui}" if ui else "")

# ---- 공통 조합자 -----------------------------------------------------
def _paren(*parts) -> str:
    """비어있지 않은 값만 골라 '(a,b,...)' 문자열 생성"""
    vals = [str(p).strip() for p in parts if p]
    return f"({','.join(vals)})" if vals else ""

def _law_revision_path(prefix: str, title: str, *, eff=None, pub_no=None, pub_date=None):
    # /법령/제개정문/법령명/(시행일자,공포번호,공포일자) 등
    par = _paren(eff, pub_no, pub_date) or _paren(pub_no, pub_date)
    base = f"/법령/{prefix}/{_q(_clean(title))}"
    return base + (f"/{_q(par)}" if par else "")

# ---- 본체: 전분야 빌더 -----------------------------------------------
def build_korean_resource_url(
    kind: str,
    title: str | None = None,
    *,
    # 법령/조문
    article_label: str | None = None,
    supplement: bool | str = False,        # True 또는 '부칙', '부칙번호' 같은 라벨
    supp_no: str | None = None,             # 부칙의 (공포번호)
    supp_date: str | None = None,           # 부칙의 (공포일자)
    triple_compare: bool | None = None,     # True면 /법령/3단비교/법령명
    # 연혁/정밀링크 공통
    eff_date: str | None = None,            # 시행일자
    pub_no: str | None = None,              # 공포번호 (또는 발령/조약/안건/의결/사건 등 '번호'류)
    pub_date: str | None = None,            # 공포일자 (또는 의결/판결/발효 등 '일자'류)
    # 별표서식류
    annex_label: str | None = None,         # '별표28의2' / '서식1' 등
    # 체계도 서브도메인
    taxonomy_sub: str | None = None,        # '법령','행정규칙','판례','법령해석례','행정심판례'
) -> str:
    """
    law.go.kr 1~35 전 분야 한글주소 생성기.
    - kind: 분야명(법령, 영문법령, 행정규칙, 자치법규, 판례, 헌재결정례, 법령해석례, 행정심판례,
                   법령별표서식, 행정규칙별표서식, 자치법규별표서식, 법령체계도, 용어,
                   개인정보보호위원회, 고용보험심사위원회, ... , 해양안전심판재결례 등)
    - title: 문서/사건/법령명(일부 특별 메뉴는 title 없이 동작)
    - 조합 인자는 위 키워드 파라미터 참고
    """
    k = (kind or "").strip()
    t = _clean(title or "")

    # 동의어 보정
    alias = {
        "법률": "법령",
        "해양안전심판재결례": "해양안전심판결례",
    }
    k = alias.get(k, k)

    # 0) 법령 추가정보(타이틀 불필요)
    if k == "법령" and t in ("최신공포법령","최신시행법령","시행예정법령"):
        return f"https://www.law.go.kr/법령/{_q(t)}"

    # 1) 법령
    if k == "법령":
        if article_label:
            return f"https://www.law.go.kr/법령/{_q(t)}/{_q(_norm_article(article_label))}"
        if supplement:
            sup = "부칙" if supplement is True else str(supplement).strip() or "부칙"
            extra = _paren(supp_no, supp_date)
            return "https://www.law.go.kr" + \
                   f"/법령/{_q(t)}/{_q(sup)}" + (f"/{_q(extra)}" if extra else "")
        if triple_compare:
            return f"https://www.law.go.kr/법령/3단비교/{_q(t)}"
        # 연혁/정밀 링크 (시행일자,공포번호,공포일자) 또는 (공포번호,공포일자)
        par = _paren(eff_date, pub_no, pub_date) or _paren(pub_no, pub_date) or _paren(pub_no)
        base = f"/법령/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 1-α) 법령의 제개정문/신구법비교
    if k in ("제개정문","신구법비교"):
        return "https://www.law.go.kr" + _law_revision_path(_q(k), t, eff=eff_date, pub_no=pub_no, pub_date=pub_date)

    # 2) 영문법령
    if k == "영문법령":
        par = _paren(pub_no, pub_date)
        base = f"/영문법령/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 3) 행정규칙
    if k == "행정규칙":
        par = _paren(pub_no, pub_date)           # (발령번호,발령일자)
        base = f"/행정규칙/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 4) 자치법규
    if k == "자치법규":
        par = _paren(pub_no, pub_date)           # (공포번호,공포일자)
        base = f"/자치법규/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 5) 학칙공단
    if k == "학칙공단":
        par = _paren(pub_no, pub_date)           # (발령번호,발령일자)
        base = f"/학칙공단/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 6) 조약
    if k == "조약":
        par = _paren(pub_no, pub_date)           # (조약번호,발효일자)
        base = f"/조약/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 7) 판례
    if k == "판례":
        # /(사건번호,판결일자) 또는 /(사건번호)
        par = _paren(pub_no, pub_date) or _paren(pub_no)
        base = f"/판례/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 8) 헌재결정례
    if k == "헌재결정례":
        par = _paren(pub_no, pub_date) or _paren(pub_no)
        base = f"/헌재결정례/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 9) 법령해석례
    if k == "법령해석례":
        par = _paren(pub_no, pub_date) or _paren(pub_no)  # (사건번호,해석일자)
        base = f"/법령해석례/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 10) 행정심판례
    if k == "행정심판례":
        par = _paren(pub_no, pub_date) or _paren(pub_no)  # (사건번호,의결일자)
        base = f"/행정심판례/{_q(t)}"
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 11~13) 별표서식류
    if k == "법령별표서식":
        # /(법령명, 별표X)
        if not annex_label:
            raise ValueError("법령별표서식: annex_label(예: '별표28의2') 필요")
        tup = f"({_clean(t)},{annex_label.strip()})"
        return f"https://www.law.go.kr/법령별표서식/{_q(tup)}"

    if k == "행정규칙별표서식":
        # /(행정규칙명, 발행번호, 별표X)
        if not annex_label:
            raise ValueError("행정규칙별표서식: annex_label(예: '별표3') 필요")
        tup = f"({_clean(t)},{pub_no or ''},{annex_label.strip()})"
        return f"https://www.law.go.kr/행정규칙별표서식/{_q(tup)}"

    if k == "자치법규별표서식":
        # /(자치법규명, 공포번호, 서식X)
        if not annex_label:
            raise ValueError("자치법규별표서식: annex_label(예: '서식1') 필요")
        tup = f"({_clean(t)},{pub_no or ''},{annex_label.strip()})"
        return f"https://www.law.go.kr/자치법규별표서식/{_q(tup)}"

    # 14) 법령체계도
    if k == "법령체계도":
        sub = (taxonomy_sub or "").strip() or "법령"
        base = f"/법령체계도/{_q(sub)}/{_q(t)}"
        # 판례 하위: /(사건번호,의결일자) 등
        par = _paren(pub_no, pub_date)
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 15) 법령 용어
    if k == "용어":
        return f"https://www.law.go.kr/용어/{_q(t)}"

    # 16~35) 각종 위원회/재결례: 공통 포맷 '/{kind}/{title}/(번호[,일자])'
    #   번호 키는 사건번호/안건번호/의결번호/재결번호/발행번호 등, 일자는 의결일자/결정일자/발표일자 등
    generic = {
        "개인정보보호위원회", "고용보험심사위원회", "공정거래위원회", "국민권익위원회",
        "금융위원회", "방송통신위원회", "산업재해보상보험재심사위원회", "노동위원회",
        "중앙토지수용위원회", "중앙환경분쟁조정위원회", "국가인권위원회",
        "중앙부처1차해석", "관세청 법령해석", "조세심판재결례", "특허심판재결례",
        "해양안전심판결례",
    }
    if k in generic:
        base = f"/{_q(k)}/{_q(t)}"
        par = _paren(pub_no, pub_date) or _paren(pub_no)
        return "https://www.law.go.kr" + (base + (f"/{_q(par)}" if par else ""))

    # 미매핑 분야도 일반 규칙 적용: /분야/제목
    return f"https://www.law.go.kr/{_q(k)}/{_q(t)}"


# --- 레코드(dict) 기반 편의 빌더 --------------------------------------
_KOREAN_KEYS = {
    "분야":"kind","제목":"title","법령명":"title","조문":"article_label",
    "공포번호":"pub_no","발령번호":"pub_no","조약번호":"pub_no","안건번호":"pub_no",
    "의결번호":"pub_no","사건번호":"pub_no","발행번호":"pub_no","재결번호":"pub_no",
    "공포일자":"pub_date","발령일자":"pub_date","발효일자":"pub_date",
    "판결일자":"pub_date","의결일자":"pub_date","결정일자":"pub_date",
    "시행일자":"eff_date","별표":"annex_label","서식":"annex_label",
}

def build_korean_url_from_record(rec: dict) -> str:
    """검색 API/LLM 레코드(dict)에서 바로 URL 생성"""
    kw = {}
    for k, v in (rec or {}).items():
        k2 = _KOREAN_KEYS.get(k, k)
        kw[k2] = v
    return build_korean_resource_url(**kw)

# 과거 코드 호환 alias
make_pretty_resource_url = build_korean_resource_url
# =====================================================================



def make_pretty_law_main_url(law_name: str) -> str:
    return f"https://law.go.kr/법령/{quote(_norm_law(law_name))}"

def _moleg_key() -> str:
    v = (os.getenv("MOLEG_SERVICE_KEY") or "").strip()
    if v:
        return v
    with contextlib.suppress(Exception):
        import streamlit as st  # type: ignore
        vv = st.secrets.get("MOLEG_SERVICE_KEY")
        if vv:
            return str(vv).strip()
    return ""

def resolve_article_url(law_name: str, article_label: str) -> str:
    """
    기본은 '예쁜 한글주소'를 반환.
    (선택) 공공데이터포털 키가 있으면 DRF '법령상세링크'를 사용해 법령 메인 링크를 더 정확히 반환.
    조문까지 정확 매칭하는 DRF 엔드포인트가 없을 때가 있어, 우선은 예쁜주소를 유지.
    """
    url = make_pretty_article_url(law_name, article_label)
    key = _moleg_key()
    if not key:
        return url

    try:
        base = "https://apis.data.go.kr/1170000/law/lawSearchList.do"
        params = {"ServiceKey": key, "target": "law", "query": law_name, "numOfRows": 1, "pageNo": 1}
        r = requests.get(base, params=params, timeout=3.5)
        if r.status_code != 200:
            return url
        m = re.search(r"<법령상세링크>(.*?)</법령상세링크>", r.text or "")
        if m:
            # 조문 라벨은 없는 경우가 많으므로, 메인 링크를 보수적으로 유지
            main = html.unescape(m.group(1)).strip()
            return main or url
    except Exception:
        pass
    return url
