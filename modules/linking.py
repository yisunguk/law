# linking.py — full resource link builders for law.go.kr (covers 1~35)
from __future__ import annotations
import re
from typing import List, Tuple, Dict

# =============== Common helpers ===============
def _h(s: str) -> str:
    """Hangul path: trim & remove spaces (law.go.kr 한글경로는 인코딩하지 않음)."""
    return (s or "").replace(" ", "").strip()

def _digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", s or "")

def _yyyymmdd(s: str) -> str:
    d = _digits(s)
    return d[:8] if len(d) >= 8 else ""

# ========== Law name / Article normalize ==========
_ABBR: Dict[str, str] = {
    # 약칭 → 정식명 필요시 여기에 추가
    # "부동산실명법": "부동산실명제에관한법률",
}

def _normalize_law_name(name: str) -> str:
    return _ABBR.get((name or "").strip(), (name or "").strip())

_ART_RE = re.compile(r"^(?:제)?\s*(\d+)(?:\s*조)?(?:\s*의\s*(\d+))?(?:\s*제\s*(\d+)\s*항)?\s*$")

def _norm_art(label: str) -> str:
    if not label:
        return ""
    label = label.replace(" ", "")
    if label.startswith("부칙"):
        return "부칙"
    m = _ART_RE.match(label)
    if not m:
        return label
    no, ei, hang = m.groups()
    base = f"제{int(no)}조"
    if ei:
        base += f"의{int(ei)}"
    if hang:
        base += f"제{int(hang)}항"
    return base

# =============== Article link builders ===============
def make_deep_article_url(law_name: str, article_label: str = "") -> str:
    name = _normalize_law_name(law_name)
    if not name:
        return "https://www.law.go.kr"
    art = _norm_art(article_label) if article_label else ""
    return f"https://www.law.go.kr/법령/{_h(name)}/{_h(art)}" if art else f"https://www.law.go.kr/법령/{_h(name)}"

# 구형 이름 호환
resolve_article_url = make_deep_article_url
deep_article_url    = make_deep_article_url
_deep_article_url   = make_deep_article_url

# =============== Article citation (조문) ===============
_LAW_PICK = re.compile(r"[\w\(\)\-·가-힣]+법(?:시행령|시행규칙)?")
_ART_PICK = re.compile(r"제\s*\d+\s*조(?:의\s*\d+)?(?:\s*제\s*\d+\s*항)?")

def extract_article_citations(text: str) -> List[Tuple[str, str]]:
    if not text:
        return []
    out: List[Tuple[str, str]] = []
    for lm in _LAW_PICK.finditer(text):
        law = lm.group(0)
        tail = text[lm.end(): lm.end() + 60]
        am = _ART_PICK.search(tail)
        if am:
            out.append((law, am.group(0)))
    return out

def render_article_links(pairs: List[Tuple[str, str]]) -> str:
    lines = []
    for law, art in pairs[:8]:
        url = make_deep_article_url(law, art)
        lines.append(f"- [{law} {art}]({url})")
    return "\n".join(lines)

def merge_article_links_block(text: str) -> str:
    pairs = extract_article_citations(text)
    if not pairs:
        return text
    block = "\n".join(["", "### 참고 링크(조문)", render_article_links(pairs), ""])
    return (text or "").rstrip() + "\n" + block

# =============== Case (판례) extraction & builder ===============
_CASE_NO = r"(?P<no>\d{4}[가-힣]{1,3}\d{1,7})"
DATE_PAIR   = re.compile(rf"\(\s*{_CASE_NO}\s*,\s*(?P<date>\d{{8}})\s*\)")
DATE_BEFORE = re.compile(rf"(?P<date>(?:19|20)\d{{2}}[.\-]?\d{{2}}[.\-]?\d{{2}})\s*(?:선고|자)?\s*{_CASE_NO}")
LONE_NO     = re.compile(_CASE_NO)

def _dd8(s: str | None) -> str | None:
    if not s: return None
    t = re.sub(r"\D", "", s)
    return t if len(t) == 8 else None

def extract_case_citations(text: str) -> List[Tuple[str, str | None]]:
    if not text:
        return []
    out: List[Tuple[str, str | None]] = []
    seen: set[Tuple[str, str | None]] = set()

    for m in DATE_PAIR.finditer(text):
        key = (m.group("no"), _dd8(m.group("date")))
        if key not in seen:
            seen.add(key); out.append(key)

    for m in DATE_BEFORE.finditer(text):
        key = (m.group("no"), _dd8(m.group("date")))
        if key not in seen:
            seen.add(key); out.append(key)

    for m in LONE_NO.finditer(text):
        key = (m.group("no"), None)
        if key not in seen:
            seen.add(key); out.append(key)
    return out

def make_case_url(case_no: str, decision_date: str | None = None) -> str:
    dd = _dd8(decision_date)
    base = "https://www.law.go.kr/판례"
    return f"{base}/({case_no},{dd})" if dd else f"{base}/({case_no})"

# =============== 1~35 Builders ===============
# 1) 법령 / 조문·부칙·삼단비교
def make_law_url(name: str, article_label: str = "") -> str:
    return make_deep_article_url(name, article_label)

def make_law_special_url(name: str, mode: str, a: str = "", b: str = "") -> str:
    base = f"https://www.law.go.kr/법령/{_h(_normalize_law_name(name))}/{_h(mode)}"
    if a and b:
        return f"{base}({_h(a)},{_yyyymmdd(b)})"
    return base

# 1-2) 제개정문 / 신구법비교
def make_law_revision_url(kind: str, name: str, a: str="", b: str="", c: str="") -> str:
    base = f"https://www.law.go.kr/법령/{_h(kind)}/{_h(_normalize_law_name(name))}"
    if a and b and c:
        return f"{base}/({_yyyymmdd(a)},{_digits(b)},{_yyyymmdd(c)})"
    if b and c:
        return f"{base}/({_digits(b)},{_yyyymmdd(c)})"
    return base

# 2) 영문법령
def make_english_law_url(name: str, pub_no: str="", pub_date: str="") -> str:
    base = f"https://www.law.go.kr/영문법령/{_h(name)}"
    return f"{base}/({_digits(pub_no)},{_yyyymmdd(pub_date)})" if pub_no and pub_date else base

# 3) 행정규칙
def make_admin_rule_url(name: str, doc_no: str="", doc_date: str="") -> str:
    base = f"https://www.law.go.kr/행정규칙/{_h(name)}"
    return f"{base}/({_h(doc_no)},{_yyyymmdd(doc_date)})" if doc_no and doc_date else base

# 4) 자치법규
def make_local_reg_url(name: str, pub_no: str="", pub_date: str="") -> str:
    base = f"https://www.law.go.kr/자치법규/{_h(name)}"
    return f"{base}/({_digits(pub_no)},{_yyyymmdd(pub_date)})" if pub_no and pub_date else base

# 5) 학칙공단
def make_institutional_rule_url(name: str, order_no: str="", order_date: str="") -> str:
    base = f"https://www.law.go.kr/학칙공단/{_h(name)}"
    return f"{base}/({_h(order_no)},{_yyyymmdd(order_date)})" if order_no and order_date else base

# 6) 조약
def make_treaty_url(name: str="", treaty_no: str="", effective_date: str="") -> str:
    if treaty_no and effective_date and not name:
        return f"https://www.law.go.kr/조약/({_digits(treaty_no)},{_yyyymmdd(effective_date)})"
    base = f"https://www.law.go.kr/조약/{_h(name)}" if name else "https://www.law.go.kr/조약"
    return f"{base}/({_digits(treaty_no)},{_yyyymmdd(effective_date)})" if treaty_no and effective_date else base

# 7) 판례
def make_case_resource_url(case_name: str="", case_no: str="", decision_date: str="") -> str:
    base = f"https://www.law.go.kr/판례/{_h(case_name)}" if case_name else "https://www.law.go.kr/판례"
    if case_no and decision_date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(decision_date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 8) 헌재결정례
def make_constcourt_url(title: str="", case_no: str="", decision_date: str="") -> str:
    base = f"https://www.law.go.kr/헌재결정례/{_h(title)}" if title else "https://www.law.go.kr/헌재결정례"
    if case_no and decision_date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(decision_date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 9) 법령해석례
def make_interpretation_url(title: str="", case_no: str="", opinion_date: str="") -> str:
    base = f"https://www.law.go.kr/법령해석례/{_h(title)}" if title else "https://www.law.go.kr/법령해석례"
    if case_no and opinion_date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(opinion_date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 10) 행정심판례
def make_admin_appeal_url(title: str="", claim_no: str="", decision_date: str="") -> str:
    base = f"https://www.law.go.kr/행정심판례/{_h(title)}" if title else "https://www.law.go.kr/행정심판례"
    if claim_no and decision_date:
        return f"{base}/({_h(claim_no)},{_yyyymmdd(decision_date)})"
    if claim_no:
        return f"{base}/({_h(claim_no)})"
    return base

# 11/12/13) 별표서식
def make_forms_url(kind: str, name: str, a: str="", b: str="") -> str:
    base = f"https://www.law.go.kr/{_h(kind)}/({_h(name)}"
    if kind == "행정규칙별표서식" and a and b:
        return f"{base},{_h(a)},{_h(b)})"
    if kind == "자치법규별표서식" and a and b:
        return f"{base},{_digits(a)},{_h(b)})"
    if a:
        return f"{base},{_h(a)})"
    return base + ")"

# 14) 법령체계도
def make_system_map_url(domain: str, title: str="", key: str="", date: str="") -> str:
    base = f"https://www.law.go.kr/법령체계도/{_h(domain)}"
    if title:
        base += f"/{_h(title)}"
    if key and date:
        return f"{base}/({_h(key)},{_yyyymmdd(date)})"
    if key:
        return f"{base}/({_h(key)})"
    return base

# 15) 용어
def make_term_url(term: str) -> str:
    return f"https://www.law.go.kr/용어/{_h(term)}"

# 16)~26) 각 위원회·기관
def make_ppc_url(title: str, case_no: str="") -> str:  # 개인정보보호위원회
    base = f"https://www.law.go.kr/개인정보보호위원회/{_h(title)}"
    return f"{base}/({_h(case_no)})" if case_no else base

def make_ei_review_url(title: str, case_no: str="") -> str:  # 고용보험심사위원회
    base = f"https://www.law.go.kr/고용보험심사위원회/{_h(title)}"
    return f"{base}/({_h(case_no)})" if case_no else base

def make_kftc_url(title: str, case_no: str="") -> str:  # 공정거래위원회
    base = f"https://www.law.go.kr/공정거래위원회/{_h(title)}"
    return f"{base}/({_h(case_no)})" if case_no else base

def make_aco_url(title: str, case_no: str="", date: str="") -> str:  # 국민권익위원회
    base = f"https://www.law.go.kr/국민권익위원회/{_h(title)}"
    if case_no and date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(date)})"
    return f"{base}/({_h(case_no)})" if case_no else base

def make_fsc_url(title: str, decision_no: str="") -> str:  # 금융위원회
    base = f"https://www.law.go.kr/금융위원회/{_h(title)}"
    return f"{base}/({_h(decision_no)})" if decision_no else base

def make_kcc_url(title: str, agenda_no: str="") -> str:  # 방송통신위원회
    base = f"https://www.law.go.kr/방송통신위원회/{_h(title)}"
    return f"{base}/({_h(agenda_no)})" if agenda_no else base

def make_iac_review_url(title: str, case_no: str="") -> str:  # 산재보상보험재심사위원회
    base = f"https://www.law.go.kr/산업재해보상보험재심사위원회/{_h(title)}"
    return f"{base}/({_h(case_no)})" if case_no else base

def make_nlrc_url(title: str, case_no: str="") -> str:  # 노동위원회
    base = f"https://www.law.go.kr/노동위원회/{_h(title)}"
    return f"{base}/({_h(case_no)})" if case_no else base

def make_clac_url(title: str) -> str:  # 중앙토지수용위원회
    return f"https://www.law.go.kr/중앙토지수용위원회/{_h(title)}"

def make_cedac_url(title: str, decision_no: str="") -> str:  # 중앙환경분쟁조정위원회
    base = f"https://www.law.go.kr/중앙환경분쟁조정위원회/{_h(title)}"
    return f"{base}/({_h(decision_no)})" if decision_no else base

def make_nhrck_url(title: str, case_no: str="", date: str="") -> str:  # 국가인권위원회
    base = f"https://www.law.go.kr/국가인권위원회/{_h(title)}"
    if case_no and date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(date)})"
    return f"{base}/({_h(case_no)})" if case_no else base

# 27~32) 중앙부처1차해석 (부처별 별칭은 모두 같은 규칙 사용)
def make_central_first_interp_url(title: str, case_no: str="", date: str="") -> str:
    base = f"https://www.law.go.kr/중앙부처1차해석/{_h(title)}"
    if case_no and date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(date)})"
    return f"{base}/({_h(case_no)})" if case_no else base

# 33) 조세심판재결례
def make_tax_appeal_url(title: str, claim_no: str="", date: str="") -> str:
    base = f"https://www.law.go.kr/조세심판재결례/{_h(title)}"
    if claim_no and date:
        return f"{base}/({_h(claim_no)},{_yyyymmdd(date)})"
    return f"{base}/({_h(claim_no)})" if claim_no else base

# 34) 특허심판재결례
def make_ip_appeal_url(title: str, request_no: str="") -> str:
    base = f"https://www.law.go.kr/특허심판재결례/{_h(title)}"
    return f"{base}/({_h(request_no)})" if request_no else base

# 35) 해양안전심판재결례
def make_marine_appeal_url(title: str, decision_no: str="", date: str="") -> str:
    base = f"https://www.law.go.kr/해양안전심판재결례/{_h(title)}"
    if decision_no and date:
        return f"{base}/({_h(decision_no)},{_yyyymmdd(date)})"
    return f"{base}/({_h(decision_no)})" if decision_no else base

# =============== Dispatcher (single entry) ===============
def make_pretty_article_url(law_name: str, article_label: str = "") -> str:
    return make_deep_article_url(law_name, article_label)

# 구형 이름도 계속 지원
build_korean_article_url  = make_pretty_article_url

# kind → builder 매핑 (1~35 전부)
_KIND = {
    # 1) 법령 계열
    "법령": lambda title, **kw: make_law_url(title, kw.get("article_label","")),
    "법률": lambda title, **kw: make_law_url(title, kw.get("article_label","")),
    "시행령": lambda title, **kw: make_law_url(title, kw.get("article_label","")),
    "시행규칙": lambda title, **kw: make_law_url(title, kw.get("article_label","")),
    "제개정문": lambda title, **kw: make_law_revision_url("제개정문", title, kw.get("a",""), kw.get("b",""), kw.get("c","")),
    "신구법비교": lambda title, **kw: make_law_revision_url("신구법비교", title, kw.get("a",""), kw.get("b",""), kw.get("c","")),
    # 2)~6)
    "영문법령": lambda title, **kw: make_english_law_url(title, kw.get("pub_no",""), kw.get("pub_date","")),
    "행정규칙": lambda title, **kw: make_admin_rule_url(title, kw.get("doc_no",""), kw.get("doc_date","")),
    "자치법규": lambda title, **kw: make_local_reg_url(title, kw.get("pub_no",""), kw.get("pub_date","")),
    "학칙공단": lambda title, **kw: make_institutional_rule_url(title, kw.get("order_no",""), kw.get("order_date","")),
    "조약": lambda title, **kw: make_treaty_url(title, kw.get("treaty_no",""), kw.get("effective_date","")),
    # 7)~10)
    "판례": lambda title, **kw: make_case_resource_url(title, kw.get("case_no",""), kw.get("decision_date","")),
    "헌재결정": lambda title, **kw: make_constcourt_url(title, kw.get("case_no",""), kw.get("decision_date","")),
    "헌재결정례": lambda title, **kw: make_constcourt_url(title, kw.get("case_no",""), kw.get("decision_date","")),
    "법령해석": lambda title, **kw: make_interpretation_url(title, kw.get("case_no",""), kw.get("opinion_date","")),
    "법령해석례": lambda title, **kw: make_interpretation_url(title, kw.get("case_no",""), kw.get("opinion_date","")),
    "행정심판": lambda title, **kw: make_admin_appeal_url(title, kw.get("claim_no",""), kw.get("decision_date","")),
    "행정심판례": lambda title, **kw: make_admin_appeal_url(title, kw.get("claim_no",""), kw.get("decision_date","")),
    # 11/12/13)
    "법령별표서식": lambda title, **kw: make_forms_url("법령별표서식", title, kw.get("a",""), kw.get("b","")),
    "행정규칙별표서식": lambda title, **kw: make_forms_url("행정규칙별표서식", title, kw.get("a",""), kw.get("b","")),
    "자치법규별표서식": lambda title, **kw: make_forms_url("자치법규별표서식", title, kw.get("a",""), kw.get("b","")),
    # 14)
    "법령체계도": lambda title, **kw: make_system_map_url(kw.get("domain",""), title, kw.get("key",""), kw.get("date","")),
    # 15)
    "용어": lambda title, **kw: make_term_url(title),
    # 16~26) 위원회/기관
    "개인정보보호위원회": lambda title, **kw: make_ppc_url(title, kw.get("case_no","")),
    "고용보험심사위원회": lambda title, **kw: make_ei_review_url(title, kw.get("case_no","")),
    "공정거래위원회": lambda title, **kw: make_kftc_url(title, kw.get("case_no","")),
    "국민권익위원회": lambda title, **kw: make_aco_url(title, kw.get("case_no",""), kw.get("date","")),
    "금융위원회": lambda title, **kw: make_fsc_url(title, kw.get("decision_no","")),
    "방송통신위원회": lambda title, **kw: make_kcc_url(title, kw.get("agenda_no","")),
    "산업재해보상보험재심사위원회": lambda title, **kw: make_iac_review_url(title, kw.get("case_no","")),
    "노동위원회": lambda title, **kw: make_nlrc_url(title, kw.get("case_no","")),
    "중앙토지수용위원회": lambda title, **kw: make_clac_url(title),
    "중앙환경분쟁조정위원회": lambda title, **kw: make_cedac_url(title, kw.get("decision_no","")),
    "국가인권위원회": lambda title, **kw: make_nhrck_url(title, kw.get("case_no",""), kw.get("date","")),
    # 27~32) 중앙부처1차해석 (부처별 별칭 동일 규칙)
    "중앙부처1차해석": lambda title, **kw: make_central_first_interp_url(title, kw.get("case_no",""), kw.get("date","")),
    "고용노동부법령해석": lambda title, **kw: make_central_first_interp_url(title, kw.get("case_no",""), kw.get("date","")),
    "국토교통부법령해석": lambda title, **kw: make_central_first_interp_url(title, kw.get("case_no",""), kw.get("date","")),
    "해양수산부법령해석": lambda title, **kw: make_central_first_interp_url(title, kw.get("case_no",""), kw.get("date","")),
    "행정안전부법령해석": lambda title, **kw: make_central_first_interp_url(title, kw.get("case_no",""), kw.get("date","")),
    "환경부법령해석": lambda title, **kw: make_central_first_interp_url(title, kw.get("case_no",""), kw.get("date","")),
    "관세청법령해석": lambda title, **kw: make_central_first_interp_url(title, kw.get("case_no",""), kw.get("date","")),
    # 33~35)
    "조세심판재결례": lambda title, **kw: make_tax_appeal_url(title, kw.get("claim_no",""), kw.get("date","")),
    "특허심판재결례": lambda title, **kw: make_ip_appeal_url(title, kw.get("request_no","")),
    "해양안전심판재결례": lambda title, **kw: make_marine_appeal_url(title, kw.get("decision_no",""), kw.get("date","")),
}

def make_pretty_resource_url(kind: str, title: str, **kwargs) -> str:
    kind = (kind or "").strip()
    title = title or ""
    # 법령 계열은 조문 라벨 지원
    if kind in ("법령", "법률", "시행령", "시행규칙"):
        return make_law_url(title, kwargs.get("article_label", ""))
    if kind in _KIND:
        return _KIND[kind](title, **kwargs)
    return "https://www.law.go.kr"

# 구형 이름도 계속 지원
build_korean_resource_url = make_pretty_resource_url

__all__ = [
    # 엔트리
    "make_pretty_resource_url", "make_pretty_article_url",
    # 조문 링크/추출
    "make_deep_article_url", "resolve_article_url", "extract_article_citations",
    "render_article_links", "merge_article_links_block",
    # 판례
    "extract_case_citations", "make_case_url",
    # 호환 alias
    "build_korean_resource_url", "build_korean_article_url", "deep_article_url", "_deep_article_url",
]
