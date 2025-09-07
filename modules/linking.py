# linking.py — full resource link builders for law.go.kr (KR)
# Covers: 1) 법령 ~ 35) 해양안전심판재결례
# Drop-in module: pure builders + a few extractors. No external deps.

from __future__ import annotations
import re
from typing import List, Tuple, Dict, Any

# ===============
# Common helpers
# ===============

def _h(s: str) -> str:
    """Normalize Hangul path segments: remove spaces, trim. Do NOT URL-encode."""
    return (s or "").replace(" ", "").strip()


def _digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", s or "")


def _yyyymmdd(s: str) -> str:
    d = _digits(s)
    return d[:8] if len(d) >= 8 else ""


# =====================
# 법령 / 조문 정규화 헬퍼
# =====================

_ABBR: Dict[str, str] = {
    # add common nickname→official normalization here if desired
    # "부동산실명법": "부동산실명제에관한법률",
}


def _normalize_law_name(name: str) -> str:
    name = (name or "").strip()
    return _ABBR.get(name, name)


_ART_RE = re.compile(
    r"^(?:제)?\s*(\d+)(?:\s*조)?(?:\s*의\s*(\d+))?(?:\s*제\s*(\d+)\s*항)?\s*$"
)


def _norm_art(label: str) -> str:
    """Normalize article label into law.go.kr style: '제3조', '제3조의2', with optional '제4항'.
    Accepts inputs like '3', '제3조', '3조의2', '제3조의2 제4항'.
    """
    if not label:
        return ""
    label = label.replace(" ", "")
    # 부칙
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


# ==============================
# Core: deep article URL builder
# ==============================

def make_deep_article_url(law_name: str, article_label: str) -> str:
    name = _normalize_law_name(law_name)
    art  = _norm_art(article_label)
    if not name:
        return "https://law.go.kr"
    if art:
        return f"https://law.go.kr/법령/{_h(name)}/{_h(art)}"
    return f"https://law.go.kr/법령/{_h(name)}"


# Backward‑compat alias used by app
resolve_article_url = make_deep_article_url


# ======================
# Article citation finder
# ======================

_LAW_PICK = re.compile(r"[\w\(\)\-·가-힣]+법(?:시행령|시행규칙)?")
_ART_PICK = re.compile(r"제\s*\d+\s*조(?:의\s*\d+)?(?:\s*제\s*\d+\s*항)?")


def extract_article_citations(text: str) -> List[Tuple[str, str]]:
    """Very lightweight law/article pair extractor.
    Returns list of (law_name, article_label).
    """
    if not text:
        return []
    out: List[Tuple[str, str]] = []
    for lm in _LAW_PICK.finditer(text):
        # find nearest article mention after the law name
        law = lm.group(0)
        tail = text[lm.end(): lm.end() + 60]
        am = _ART_PICK.search(tail)
        if am:
            out.append((law, am.group(0)))
    return out


# ======================
# Case link helpers
# ======================

_CASE_RE = re.compile(r"((?:19|20)\d{2}[가-힣]{1,2}\d{2,6})")  # e.g., 2012다89399
_DATE_RE = re.compile(
    r"((?:19|20)\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.?)|"  # 2013.12.18.
    r"((?:19|20)\d{2}-\d{1,2}-\d{1,2})|"                 # 2013-12-18
    r"((?:19|20)\d{7})|"                                  # 20131218
    r"((?:19|20)\d{2}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일)"
)


def resolve_case_url(case_no: str, decision_date: str) -> str:
    d = _yyyymmdd(decision_date)
    if not (case_no and d):
        return ""
    return f"https://law.go.kr/판례/({_h(case_no)},{d})"


def extract_case_citations(text: str) -> List[Tuple[str, str]]:
    """Find case numbers and nearest date in text: returns [(case_no, yyyymmdd)]."""
    if not text:
        return []
    cases = [(m.group(0), m.start()) for m in _CASE_RE.finditer(text)]
    dates = [(_yyyymmdd(m.group(0)), m.start()) for m in _DATE_RE.finditer(text)]
    dates = [(d, p) for (d, p) in dates if d]
    out: List[Tuple[str, str]] = []
    if not cases:
        return out
    if len(dates) == 1:
        d = dates[0][0]
        for c, _ in cases:
            out.append((c, d))
        return out
    for c, pos in cases:
        nearest, best = "", 10**9
        for d, dpos in dates:
            dist = abs(pos - dpos)
            if dist < best:
                best, nearest = dist, d
        if nearest:
            out.append((c, nearest))
    return out


# ===============================
# Builders per resource (1~35)
# ===============================

# 1) 법령 (정확명/약칭 + 조문/부칙/삼단비교)

def make_law_url(name: str, article_label: str = "") -> str:
    return make_deep_article_url(name, article_label)


def make_law_special_url(name: str, mode: str, a: str = "", b: str = "") -> str:
    # mode in {"부칙", "삼단비교"}
    base = f"https://law.go.kr/법령/{_h(_normalize_law_name(name))}/{_h(mode)}"
    if a and b:
        return f"{base}({_h(a)},{_yyyymmdd(b)})"
    return base

# 1-2) 제개정문/신구법비교 (별도 경로)

def make_law_revision_url(kind: str, name: str, a: str = "", b: str = "", c: str = "") -> str:
    # kind in {"제개정문", "신구법비교"}
    base = f"https://law.go.kr/법령/{_h(kind)}/{_h(_normalize_law_name(name))}"
    if a and b and c:
        return f"{base}/({_yyyymmdd(a)},{_digits(b)},{_yyyymmdd(c)})"
    if b and c:
        return f"{base}/({_digits(b)},{_yyyymmdd(c)})"
    return base

# 2) 영문법령

def make_english_law_url(name: str, pub_no: str = "", pub_date: str = "") -> str:
    base = f"https://law.go.kr/영문법령/{_h(name)}"
    if pub_no and pub_date:
        return f"{base}/({_digits(pub_no)},{_yyyymmdd(pub_date)})"
    return base

# 3) 행정규칙

def make_admin_rule_url(name: str, doc_no: str = "", doc_date: str = "") -> str:
    base = f"https://law.go.kr/행정규칙/{_h(name)}"
    if doc_no and doc_date:
        return f"{base}/({_h(doc_no)},{_yyyymmdd(doc_date)})"
    return base

# 4) 자치법규

def make_local_reg_url(name: str, pub_no: str = "", pub_date: str = "") -> str:
    base = f"https://law.go.kr/자치법규/{_h(name)}"
    if pub_no and pub_date:
        return f"{base}/({_digits(pub_no)},{_yyyymmdd(pub_date)})"
    return base

# 5) 학칙공단

def make_institutional_rule_url(name: str, order_no: str = "", order_date: str = "") -> str:
    base = f"https://law.go.kr/학칙공단/{_h(name)}"
    if order_no and order_date:
        return f"{base}/({_h(order_no)},{_yyyymmdd(order_date)})"
    return base

# 6) 조약

def make_treaty_url(name: str = "", treaty_no: str = "", effective_date: str = "") -> str:
    if treaty_no and effective_date and not name:
        return f"https://law.go.kr/조약/({_digits(treaty_no)},{_yyyymmdd(effective_date)})"
    base = f"https://law.go.kr/조약/{_h(name)}" if name else "https://law.go.kr/조약"
    if treaty_no and effective_date:
        return f"{base}/({_digits(treaty_no)},{_yyyymmdd(effective_date)})"
    return base

# 7) 판례

def make_case_url(case_name: str = "", case_no: str = "", decision_date: str = "") -> str:
    base = f"https://law.go.kr/판례/{_h(case_name)}" if case_name else "https://law.go.kr/판례"
    if case_no and decision_date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(decision_date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 8) 헌재결정례

def make_constcourt_url(title: str = "", case_no: str = "", decision_date: str = "") -> str:
    base = f"https://law.go.kr/헌재결정례/{_h(title)}" if title else "https://law.go.kr/헌재결정례"
    if case_no and decision_date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(decision_date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 9) 법령해석례

def make_interpretation_url(title: str = "", case_no: str = "", opinion_date: str = "") -> str:
    base = f"https://law.go.kr/법령해석례/{_h(title)}" if title else "https://law.go.kr/법령해석례"
    if case_no and opinion_date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(opinion_date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 10) 행정심판례

def make_admin_appeal_url(title: str = "", claim_no: str = "", decision_date: str = "") -> str:
    base = f"https://law.go.kr/행정심판례/{_h(title)}" if title else "https://law.go.kr/행정심판례"
    if claim_no and decision_date:
        return f"{base}/({_h(claim_no)},{_yyyymmdd(decision_date)})"
    if claim_no:
        return f"{base}/({_h(claim_no)})"
    return base

# 11) 법령별표서식 / 12) 행정규칙별표서식 / 13) 자치법규별표서식

def make_forms_url(kind: str, name: str, a: str = "", b: str = "") -> str:
    base = f"https://law.go.kr/{_h(kind)}/({_h(name)}"
    if kind == "행정규칙별표서식" and a and b:
        return f"{base},{_h(a)},{_h(b)})"
    if kind == "자치법규별표서식" and a and b:
        return f"{base},{_digits(a)},{_h(b)})"
    if a:
        return f"{base},{_h(a)})"
    return base + ")"

# 14) 법령체계도

def make_system_map_url(domain: str, title: str = "", key: str = "", date: str = "") -> str:
    base = f"https://law.go.kr/법령체계도/{_h(domain)}"
    if title:
        base += f"/{_h(title)}"
    if key and date:
        return f"{base}/({_h(key)},{_yyyymmdd(date)})"
    if key:
        return f"{base}/({_h(key)})"
    return base

# 15) 법령 용어

def make_term_url(term: str) -> str:
    return f"https://law.go.kr/용어/{_h(term)}"

# 16) 개인정보보호위원회

def make_ppc_url(title: str, case_no: str = "") -> str:
    base = f"https://law.go.kr/개인정보보호위원회/{_h(title)}"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 17) 고용보험심사위원회

def make_ei_review_url(title: str, case_no: str = "") -> str:
    base = f"https://law.go.kr/고용보험심사위원회/{_h(title)}"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 18) 공정거래위원회

def make_kftc_url(title: str, case_no: str = "") -> str:
    base = f"https://law.go.kr/공정거래위원회/{_h(title)}"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 19) 국민권익위원회

def make_aco_url(title: str, case_no: str = "", date: str = "") -> str:
    base = f"https://law.go.kr/국민권익위원회/{_h(title)}"
    if case_no and date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 20) 금융위원회

def make_fsc_url(title: str, decision_no: str = "") -> str:
    base = f"https://law.go.kr/금융위원회/{_h(title)}"
    if decision_no:
        return f"{base}/({_h(decision_no)})"
    return base

# 21) 방송통신위원회

def make_kcc_url(title: str, agenda_no: str = "") -> str:
    base = f"https://law.go.kr/방송통신위원회/{_h(title)}"
    if agenda_no:
        return f"{base}/({_h(agenda_no)})"
    return base

# 22) 산업재해보상보험재심사위원회

def make_iac_review_url(title: str, case_no: str = "") -> str:
    base = f"https://law.go.kr/산업재해보상보험재심사위원회/{_h(title)}"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 23) 노동위원회

def make_nlrc_url(title: str, case_no: str = "") -> str:
    base = f"https://law.go.kr/노동위원회/{_h(title)}"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 24) 중앙토지수용위원회

def make_clac_url(title: str) -> str:
    return f"https://law.go.kr/중앙토지수용위원회/{_h(title)}"

# 25) 중앙환경분쟁조정위원회

def make_cedac_url(title: str, decision_no: str = "") -> str:
    base = f"https://law.go.kr/중앙환경분쟁조정위원회/{_h(title)}"
    if decision_no:
        return f"{base}/({_h(decision_no)})"
    return base

# 26) 국가인권위원회

def make_nhrck_url(title: str, case_no: str = "", date: str = "") -> str:
    base = f"https://law.go.kr/국가인권위원회/{_h(title)}"
    if case_no and date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 27~32) 중앙부처1차해석 (고용노동부/국토부/해수부/행안부/환경부/관세청)

def make_central_first_interp_url(title: str, case_no: str = "", date: str = "") -> str:
    base = f"https://law.go.kr/중앙부처1차해석/{_h(title)}"
    if case_no and date:
        return f"{base}/({_h(case_no)},{_yyyymmdd(date)})"
    if case_no:
        return f"{base}/({_h(case_no)})"
    return base

# 33) 조세심판재결례

def make_tax_appeal_url(title: str, claim_no: str = "", date: str = "") -> str:
    base = f"https://law.go.kr/조세심판재결례/{_h(title)}"
    if claim_no and date:
        return f"{base}/({_h(claim_no)},{_yyyymmdd(date)})"
    if claim_no:
        return f"{base}/({_h(claim_no)})"
    return base

# 34) 특허심판재결례

def make_ip_appeal_url(title: str, request_no: str = "") -> str:
    base = f"https://law.go.kr/특허심판재결례/{_h(title)}"
    if request_no:
        return f"{base}/({_h(request_no)})"
    return base

# 35) 해양안전심판재결례

def make_marine_appeal_url(title: str, decision_no: str = "", date: str = "") -> str:
    base = f"https://law.go.kr/해양안전심판재결례/{_h(title)}"
    if decision_no and date:
        return f"{base}/({_h(decision_no)},{_yyyymmdd(date)})"
    if decision_no:
        return f"{base}/({_h(decision_no)})"
    return base


# =====================================
# Master dispatcher (public entry point)
# =====================================

def make_pretty_resource_url(kind: str, title: str, **kw) -> str:
    kind = (kind or "").strip()
    title = title or ""
    name = _normalize_law_name(title)

    # 1) 법령
    if kind in ("법령", "법률", "시행령", "시행규칙"):
        art = kw.get("article_label") or ""
        if kw.get("mode") in ("부칙", "삼단비교"):
            return make_law_special_url(name, kw.get("mode"), kw.get("a", ""), kw.get("b", ""))
        return make_law_url(name, art)

    # 1-2) 제개정문/신구법비교
    if kind in ("제개정문", "신구법비교"):
        return make_law_revision_url(kind, name, kw.get("a", ""), kw.get("b", ""), kw.get("c", ""))

    # 2) 영문법령
    if kind == "영문법령":
        return make_english_law_url(name, kw.get("pub_no", ""), kw.get("pub_date", ""))

    # 3) 행정규칙
    if kind == "행정규칙":
        return make_admin_rule_url(name, kw.get("doc_no", ""), kw.get("doc_date", ""))

    # 4) 자치법규
    if kind == "자치법규":
        return make_local_reg_url(name, kw.get("pub_no", ""), kw.get("pub_date", ""))

    # 5) 학칙공단
    if kind == "학칙공단":
        return make_institutional_rule_url(name, kw.get("order_no", ""), kw.get("order_date", ""))

    # 6) 조약
    if kind == "조약":
        return make_treaty_url(name, kw.get("treaty_no", ""), kw.get("effective_date", ""))

    # 7) 판례
    if kind == "판례":
        if kw.get("case_no") or kw.get("decision_date"):
            return make_case_url(name, kw.get("case_no", ""), kw.get("decision_date", ""))
        return make_case_url(name)

    # 8) 헌재결정(례)
    if kind in ("헌재결정", "헌재결정례"):
        return make_constcourt_url(name, kw.get("case_no", ""), kw.get("decision_date", ""))

    # 9) 법령해석(례)
    if kind in ("법령해석", "법령해석례"):
        return make_interpretation_url(name, kw.get("case_no", ""), kw.get("opinion_date", ""))

    # 10) 행정심판(례)
    if kind in ("행정심판", "행정심판례"):
        return make_admin_appeal_url(name, kw.get("claim_no", ""), kw.get("decision_date", ""))

    # 11~13) 별표서식
    if kind in ("법령별표서식", "행정규칙별표서식", "자치법규별표서식"):
        return make_forms_url(kind, name, kw.get("a", ""), kw.get("b", ""))

    # 14) 법령체계도
    if kind == "법령체계도":
        return make_system_map_url(kw.get("domain", ""), name, kw.get("key", ""), kw.get("date", ""))

    # 15) 용어
    if kind == "용어":
        return make_term_url(name)

    # 16) 개인정보보호위원회
    if kind == "개인정보보호위원회":
        return make_ppc_url(name, kw.get("case_no", ""))

    # 17) 고용보험심사위원회
    if kind == "고용보험심사위원회":
        return make_ei_review_url(name, kw.get("case_no", ""))

    # 18) 공정거래위원회
    if kind == "공정거래위원회":
        return make_kftc_url(name, kw.get("case_no", ""))

    # 19) 국민권익위원회
    if kind == "국민권익위원회":
        return make_aco_url(name, kw.get("case_no", ""), kw.get("date", ""))

    # 20) 금융위원회
    if kind == "금융위원회":
        return make_fsc_url(name, kw.get("decision_no", ""))

    # 21) 방송통신위원회
    if kind == "방송통신위원회":
        return make_kcc_url(name, kw.get("agenda_no", ""))

    # 22) 산업재해보상보험재심사위원회
    if kind == "산업재해보상보험재심사위원회":
        return make_iac_review_url(name, kw.get("case_no", ""))

    # 23) 노동위원회
    if kind == "노동위원회":
        return make_nlrc_url(name, kw.get("case_no", ""))

    # 24) 중앙토지수용위원회
    if kind == "중앙토지수용위원회":
        return make_clac_url(name)

    # 25) 중앙환경분쟁조정위원회
    if kind == "중앙환경분쟁조정위원회":
        return make_cedac_url(name, kw.get("decision_no", ""))

    # 26) 국가인권위원회
    if kind == "국가인권위원회":
        return make_nhrck_url(name, kw.get("case_no", ""), kw.get("date", ""))

    # 27~32) 중앙부처1차해석 (고용노동부/국토교통부/해양수산부/행정안전부/환경부/관세청)
    if kind in ("고용노동부법령해석", "국토교통부법령해석", "해양수산부법령해석", "행정안전부법령해석", "환경부법령해석", "관세청법령해석", "중앙부처1차해석"):
        return make_central_first_interp_url(name, kw.get("case_no", ""), kw.get("date", ""))

    # 33) 조세심판재결례
    if kind == "조세심판재결례":
        return make_tax_appeal_url(name, kw.get("claim_no", ""), kw.get("date", ""))

    # 34) 특허심판재결례
    if kind == "특허심판재결례":
        return make_ip_appeal_url(name, kw.get("request_no", ""))

    # 35) 해양안전심판재결례
    if kind == "해양안전심판재결례":
        return make_marine_appeal_url(name, kw.get("decision_no", ""), kw.get("date", ""))

    # Fallback
    return "https://law.go.kr"


__all__ = [
    # primaries
    "make_pretty_resource_url",
    # law/article helpers
    "make_deep_article_url", "resolve_article_url", "extract_article_citations",
    # case helpers
    "resolve_case_url", "extract_case_citations",
]
