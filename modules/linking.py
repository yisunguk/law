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

# linking.py — 약칭/일상어 → law.go.kr 정식 법령명 매핑(확장판)
# 사용처: _normalize_law_name()에서 먼저 이 테이블을 조회해 정식명으로 교정
# 주의: 법령명은 공백·중점(·)·쉼표(,) 등 표기를 law.go.kr 기준으로 맞춤

from typing import Dict

_ABBR: Dict[str, str] = {
    # 민사·형사·상사 기본
    "민법전": "민법",
    "형법전": "형법",
    "상법전": "상법",
    "민소법": "민사소송법",
    "민집법": "민사집행법",
    "형소법": "형사소송법",
    "행소법": "행정소송법",
    "행절법": "행정절차법",
    "국배법": "국가배상법",
    "정보공개법": "공공기관의 정보공개에 관한 법률",
    "민사집행법": "민사집행법",  # 동일명 보정(사용자가 소문자 등으로 넣는 경우가 있어 둠)

    # 부동산·건설·도시정비
    "주임법": "주택임대차보호법",
    "주택임대차법": "주택임대차보호법",
    "상임법": "상가건물 임대차보호법",
    "상가임대차법": "상가건물 임대차보호법",
    "상가임대차보호법": "상가건물 임대차보호법",
    "부동산실명법": "부동산실명제에관한법률",
    "부동산실명제법": "부동산실명제에관한법률",
    "부동산거래신고법": "부동산 거래신고 등에 관한 법률",
    "집합건물법": "집합건물의 소유 및 관리에 관한 법률",
    "국토계획법": "국토의 계획 및 이용에 관한 법률",
    "건산법": "건설산업기본법",
    "건축물관리법": "건축물관리법",
    "건축사법": "건축사법",
    "도정법": "도시 및 주거환경정비법",
    "주거정비법": "도시 및 주거환경정비법",
    "도시정비법": "도시 및 주거환경정비법",
    "도시개발법": "도시개발법",
    "공공주택법": "공공주택 특별법",
    "개발제한구역법": "개발제한구역의 지정 및 관리에 관한 특별조치법",
    "국유재산법": "국유재산법",
    "공유재산법": "공유재산 및 물품 관리법",
    "부동산등기법": "부동산등기법",
    "중처법": "중대재해처벌법",

    # 교통·자동차
    "자배법": "자동차손해배상 보장법",
    "교특법": "교통사고처리 특례법",
    "자동차관리법": "자동차관리법",
    "여객운수법": "여객자동차 운수사업법",
    "화물운수법": "화물자동차 운수사업법",
    "도로교통법": "도로교통법",
    "도로법": "도로법",
    "철도사업법": "철도사업법",
    "철도안전법": "철도안전법",
    "항공안전법": "항공안전법",
    "항공사업법": "항공사업법",
    "공항시설법": "공항시설법",

    # 조세·재정
    "국기법": "국세기본법",
    "국징법": "국세징수법",
    "부가세법": "부가가치세법",
    "상증법": "상속세 및 증여세법",
    "상증세법": "상속세 및 증여세법",
    "지방세기본법": "지방세기본법",
    "지방세법": "지방세법",
    "조세범처벌법": "조세범 처벌법",
    "법인세법": "법인세법",
    "소득세법": "소득세법",

    # 노동·산재·고용
    "근기법": "근로기준법",
    "퇴직급여법": "근로자퇴직급여 보장법",
    "기간제법": "기간제 및 단시간근로자 보호 등에 관한 법률",
    "파견법": "파견근로자보호 등에 관한 법률",
    "남녀고용평등법": "남녀고용평등과 일·가정 양립 지원에 관한 법률",
    "노조법": "노동조합 및 노동관계조정법",
    "산안법": "산업안전보건법",
    "산재보험법": "산업재해보상보험법",
    "최저임금법": "최저임금법",
    "직업안정법": "직업안정법",
    "근로자참여법": "근로자참여 및 협력증진에 관한 법률",

    # 공정거래·소비자·상거래
    "공정거래법": "독점규제 및 공정거래에 관한 법률",
    "하도급법": "하도급거래 공정화에 관한 법률",
    "가맹사업법": "가맹사업거래의 공정화에 관한 법률",
    "대규모유통업법": "대규모유통업에서의 거래 공정화에 관한 법률",
    "전자상거래법": "전자상거래 등에서의 소비자보호에 관한 법률",
    "소비자기본법": "소비자기본법",
    "약관규제법": "약관의 규제에 관한 법률",
    "표시광고법": "표시·광고의 공정화에 관한 법률",
    "부정경쟁방지법": "부정경쟁방지 및 영업비밀보호에 관한 법률",
    "영업비밀보호법": "부정경쟁방지 및 영업비밀보호에 관한 법률",
    "제조물책임법": "제조물책임법",
    "PL법": "제조물책임법",
    "콘진법": "콘텐츠산업 진흥법",

    # 금융·IT·지식재산
    "자본시장법": "자본시장과 금융투자업에 관한 법률",
    "여신전문금융법": "여신전문금융업법",
    "전자금융거래법": "전자금융거래법",
    "보험업법": "보험업법",
    "은행법": "은행법",
    "상호저축은행법": "상호저축은행법",
    "금융실명법": "금융실명거래 및 비밀보장에 관한 법률",
    "특금법": "특정 금융거래정보의 보고 및 이용 등에 관한 법률",
    "신용정보법": "신용정보의 이용 및 보호에 관한 법률",
    "개보법": "개인정보 보호법",
    "개인정보보호법": "개인정보 보호법",
    "정보통신망법": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "전자서명법": "전자서명법",
    "전자문서법": "전자문서 및 전자거래 기본법",
    "정보통신기반보호법": "정보통신기반 보호법",
    "전기통신사업법": "전기통신사업법",
    "전파법": "전파법",
    "위치정보법": "위치정보의 보호 및 이용 등에 관한 법률",
    "저작권법": "저작권법",
    "특허법": "특허법",
    "실용신안법": "실용신안법",
    "디자인보호법": "디자인보호법",
    "상표법": "상표법",
    "영화및비디오법": "영화 및 비디오물의 진흥에 관한 법률",  # 사용자 일상어 대비

    # 가사·가족·등록
    "가족관계등록법": "가족관계의 등록 등에 관한 법률",
    "주민등록법": "주민등록법",
    "출입국관리법": "출입국관리법",
    "국적법": "국적법",
    "가사소송법": "가사소송법",
    "양육비이행법": "양육비 이행확보 및 지원에 관한 법률",

    # 보건·의료·사회보장
    "국민건강보험법": "국민건강보험법",
    "건강보험법": "국민건강보험법",
    "국민연금법": "국민연금법",
    "노인장기요양보험법": "노인장기요양보험법",
    "의료법": "의료법",
    "약사법": "약사법",
    "감염병예방법": "감염병의 예방 및 관리에 관한 법률",
    "마약류관리법": "마약류 관리에 관한 법률",
    "정신건강복지법": "정신건강증진 및 정신질환자 복지서비스 지원에 관한 법률",
    "국민기초생활보장법": "국민기초생활 보장법",

    # 여성·아동·성범죄·가정폭력
    "아청법": "아동·청소년의 성보호에 관한 법률",
    "성폭력처벌법": "성폭력범죄의 처벌 등에 관한 특례법",
    "아동학대처벌법": "아동학대범죄의 처벌 등에 관한 특례법",
    "가정폭력처벌법": "가정폭력범죄의 처벌 등에 관한 특례법",
    "가정폭력방지법": "가정폭력방지 및 피해자보호 등에 관한 법률",
    "성매매처벌법": "성매매알선 등 행위의 처벌에 관한 법률",
    "스토킹처벌법": "스토킹범죄의 처벌 등에 관한 법률",
    "청보법": "청소년 보호법",
    "아동복지법": "아동복지법",

    # 소방·안전·재난
    "소방법": "소방기본법",
    "소방시설법": "화재예방, 소방시설 설치·유지 및 안전관리에 관한 법률",
    "위험물안전관리법": "위험물안전관리법",
    "재난안전법": "재난 및 안전관리 기본법",

    # 환경
    "환경정책기본법": "환경정책기본법",
    "대기환경보전법": "대기환경보전법",
    "물환경보전법": "물환경보전법",
    "소음진동법": "소음·진동관리법",
    "악취방지법": "악취방지법",
    "폐기물관리법": "폐기물관리법",
    "자연환경보전법": "자연환경보전법",
    "야생생물보호법": "야생생물 보호 및 관리에 관한 법률",
    "수도법": "수도법",
    "하수도법": "하수도법",

    # 공직·선거·부패방지
    "청탁금지법": "부정청탁 및 금품등 수수의 금지에 관한 법률",
    "공직자윤리법": "공직자윤리법",
    "공직선거법": "공직선거법",
    "정치자금법": "정치자금법",
    "공익신고자보호법": "공익신고자 보호법",
    "부패방지법": "부패방지 및 국민권익위원회의 설치와 운영에 관한 법률",

    # 국방·치안·형사특별
    "군형법": "군형법",
    "군사기밀보호법": "군사기밀 보호법",
    "병역법": "병역법",
    "통비법": "통신비밀보호법",
    "통신비밀보호법": "통신비밀보호법",
    "범죄피해자보호법": "범죄피해자 보호법",

    # 교육·문화
    "초중등교육법": "초·중등교육법",
    "고등교육법": "고등교육법",
    "유아교육법": "유아교육법",
    "사립학교법": "사립학교법",
    "학원법": "학원의 설립·운영 및 과외교습에 관한 법률",
    "문화재보호법": "문화재보호법",

    # 부동산 중개·전문직
    "공인중개사법": "공인중개사법",
    "변호사법": "변호사법",
    "공증인법": "공증인법",
    "세무사법": "세무사법",
    "관세사법": "관세사법",
    "법무사법": "법무사법",

    # 기타 행정일반
    "민원처리법": "민원 처리에 관한 법률",
    "전자정부법": "전자정부법",
    "행정대집행법": "행정대집행법",
    "질서위반법": "질서위반행위규제법",
    "국가계약법": "국가를 당사자로 하는 계약에 관한 법률",
    "지방계약법": "지방자치단체를 당사자로 하는 계약에 관한 법률",
    "지방자치법": "지방자치법",
    "행정조사기본법": "행정조사기본법",

    # 토목·수자원
    "하천법": "하천법",
    "공유수면매립법": "공유수면관리 및 매립에 관한 법률",

    # 관광·체육
    "관광진흥법": "관광진흥법",
    "체육진흥법": "국민체육진흥법",

    # 전기·에너지
    "전기사업법": "전기사업법",
    "전기안전법": "전기용품 및 생활용품 안전관리법",
    "전력거래법": "전력시장운영에 관한 규칙",  # 사용자 혼동 대비(실제 법률은 아님, 내부 보정용)

    # 기타 흔한 표기 보정(공백·붙임)
    "개인정보보호": "개인정보 보호법",
    "상가건물임대차보호법": "상가건물 임대차보호법",
    "부동산 거래신고법": "부동산 거래신고 등에 관한 법률",
    "초중등교육": "초·중등교육법",
}

def _normalize_law_name(name: str) -> str:
    """
    약칭/일상어/오탈자 섞인 입력을 law.go.kr 정식 법령명으로 보정.
    - 완전 일치 우선(_ABBR lookup)
    - 앞뒤 공백 제거 및 풀와이드/하이픈/점 등 흔한 변형 보정(여기서는 최소화)
    """
    key = (name or "").strip()
    return _ABBR.get(key, key)


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

# --- Article citation (strict & correct) ---
# '...법(시행령|시행규칙)?' 토큰만 잡고, 문장 앞 단어/조사는 무시
_LAW_TOKEN   = r'[가-힣A-Za-z0-9·()]+법(?:시행령|시행규칙)?'
_LEFT_BOUND  = r'(?:(?<=^)|(?<=[\s"\'“”‘’\(\[\{<「『]))'
_LAW_PICK    = re.compile(_LEFT_BOUND + rf'(?P<law>{_LAW_TOKEN})')
_ART_PICK    = re.compile(
    r'(제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*제\s*\d+\s*항)?|'   # 제N조[의M][제K항]
    r'부칙(?:\(\s*\d+\s*,\s*\d{8}\s*\))?)'                    # 부칙 또는 부칙(번호,YYYYMMDD)
)

def _pick_rightmost_law(raw: str) -> str:
    # 혹시 공백 섞였어도 최우측 '...법' 토큰만 사용
    m = re.findall(_LAW_TOKEN, raw or '')
    return m[-1] if m else (raw or '').strip()

def extract_article_citations(text: str) -> List[Tuple[str, str]]:
    """텍스트에서 (법령명, 조문라벨) 추출 — 중복 제거/순서 유지."""
    if not text:
        return []
    seen = set()
    out: List[Tuple[str, str]] = []
    for m in _LAW_PICK.finditer(text):
        law = _pick_rightmost_law(m.group('law'))
        tail = text[m.end(): m.end() + 100]      # 법령명 바로 뒤에서만 조문 탐색
        am = _ART_PICK.search(tail)
        if not am:
            continue
        art = _norm_art(am.group(0))
        key = (law, art)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
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
