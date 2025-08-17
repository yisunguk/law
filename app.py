import os
import re
import difflib
import urllib.parse as up
import xml.etree.ElementTree as ET
import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────────
LAW_API_KEY = (
    st.secrets.get("LAW_API_KEY")
    if hasattr(st, "secrets") and "LAW_API_KEY" in st.secrets
    else os.getenv("LAW_API_KEY", "YOUR_API_KEY")
)

API_ENDPOINTS = (
    "https://apis.data.go.kr/1170000/law/lawSearchList.do",
    "http://apis.data.go.kr/1170000/law/lawSearchList.do",
)

MAX_ROWS_PER_CALL = 50
st.set_page_config(page_title="법제처 검색(Fuzzy 통합)", page_icon="⚖️", layout="centered")

# ──────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────
def _norm_kor(s: str) -> str:
    return re.sub(r"[\s\-\_·,./()\[\]{}:;!?\"'`~]", "", (s or "").strip()).lower()

def _extract_hangul_tokens(s: str) -> list[str]:
    return re.findall(r"[가-힣]{2,}", s or "")

def _parse_law_items(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for law in root.findall(".//law"):
        items.append({
            "법령명": law.findtext("법령명한글", default=""),
            "법령약칭명": law.findtext("법령약칭명", default=""),
            "소관부처명": law.findtext("소관부처명", default=""),
            "법령구분명": law.findtext("법령구분명", default=""),
            "시행일자": law.findtext("시행일자", default=""),
            "공포일자": law.findtext("공포일자", default=""),
            "법령상세링크": law.findtext("법령상세링크", default=""),
        })
    return items

# ──────────────────────────────────────────────────────────────
# API 검색
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=300)
def search_law_data(query: str, num_rows: int = 10):
    if not LAW_API_KEY or LAW_API_KEY == "YOUR_API_KEY":
        return [], None, "LAW_API_KEY 미설정 또는 기본값입니다. Secrets/환경변수를 확인하세요."

    params = {
        "serviceKey": up.quote_plus(LAW_API_KEY),
        "target": "law",
        "query": query,
        "numOfRows": max(1, min(MAX_ROWS_PER_CALL, int(num_rows))),
        "pageNo": 1,
    }

    last_err = None
    for url in API_ENDPOINTS:
        try:
            res = requests.get(url, params=params, timeout=15)
            res.raise_for_status()
            laws = _parse_law_items(res.text)
            return laws, url, None
        except Exception as e:
            last_err = e
    return [], None, f"법제처 API 연결 실패: {last_err}"

# ──────────────────────────────────────────────────────────────
# Fuzzy 매칭
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=180)
def gather_candidate_lawnames(user_query: str, max_tokens: int = 6) -> list[dict]:
    tokens = _extract_hangul_tokens(user_query)
    tokens = tokens[:max_tokens] if tokens else []
    q = re.sub(r"\\s+", "", user_query or "")
    extra = []
    if len(q) >= 3:
        extra.append(q[:3])
    if len(q) >= 4:
        extra.append(q[-4:])
    for t in extra:
        if t not in tokens:
            tokens.append(t)

    pool: dict[str, dict] = {}
    for t in tokens:
        laws, _, _ = search_law_data(t, num_rows=MAX_ROWS_PER_CALL)
        for it in laws:
            name = it.get("법령명", "")
            if name and name not in pool:
                pool[name] = it
            nick = it.get("법령약칭명") or ""
            if nick and nick not in pool:
                tmp = dict(it)
                tmp["법령명"] = nick
                pool[nick] = tmp
    return list(pool.values())

def fuzzy_pick_official_name(user_query: str, candidates: list[dict], threshold: float = 0.62) -> str | None:
    if not candidates:
        return None

    norm_q = _norm_kor(user_query)
    name_to_official: dict[str, str] = {}
    names: list[str] = []
    for c in candidates:
        official = c.get("법령명") or ""
        nick = c.get("법령약칭명") or ""
        if official:
            names.append(official)
            name_to_official[official] = official
        if nick:
            names.append(nick)
            name_to_official[nick] = official or nick

    close = difflib.get_close_matches(user_query, names, n=8, cutoff=0.0)

    scored = []
    for nm in set(names + close):
        ratio = difflib.SequenceMatcher(None, norm_q, _norm_kor(nm)).ratio()
        inc = 0.05 if (norm_q in _norm_kor(nm) or _norm_kor(nm) in norm_q) else 0.0
        scored.append((ratio + inc, nm))
    scored.sort(reverse=True)

    best_score, best_name = (scored[0] if scored else (0.0, None))
    if best_name and best_score >= threshold:
        return name_to_official.get(best_name, best_name)
    return None

def search_with_fuzzy(user_query: str, final_rows: int = 10):
    laws, endpoint, err = search_law_data(user_query, num_rows=final_rows)
    if laws:
        return laws, endpoint, err, {"mode": "primary", "used_query": user_query}

    pool = gather_candidate_lawnames(user_query)
    guess = fuzzy_pick_official_name(user_query, pool)
    if guess:
        laws2, endpoint2, err2 = search_law_data(guess, num_rows=final_rows)
        if laws2:
            return laws2, endpoint2, err2, {"mode": "fuzzy", "used_query": guess}

    return [], endpoint, err, {"mode": "none", "used_query": None}

# ──────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────
st.title("⚖️ 법제처 검색 (Fuzzy 통합)")
st.caption("정확한 법령명이 아니어도, 비슷한 명칭을 자동으로 찾아 재검색합니다.")

q = st.text_input("법령(또는 별칭/키워드)을 입력하세요", placeholder="예: 중대재해처벌법, 정당방위, 전세, 산안법…")

if q:
    with st.spinner("🔎 법제처에서 관련 법령 검색 중..."):
        items, used_ep, err, info = search_with_fuzzy(q, final_rows=10)

    if used_ep:
        print(f"[DEBUG] endpoint={used_ep}, mode={info.get('mode')}, used_query={info.get('used_query')}")

    if err and "미설정" in str(err):
        st.error(err)

    if items:
        if info.get("mode") == "fuzzy":
            st.info(f"입력값과 가장 가까운 정식 법령명으로 재검색했습니다 → **{info.get('used_query')}**")
        st.success(f"총 {len(items)}건의 관련 법령 검색 결과")
        for i, law in enumerate(items, 1):
            st.markdown(
                f"**{i}. {law['법령명']}**  \n"
                f"- 구분: {law['법령구분명']}  \n"
                f"- 소관부처: {law['소관부처명']}  \n"
                f"- 시행일자: {law['시행일자']} / 공포일자: {law['공포일자']}  \n"
                f"- 링크: {law['법령상세링크'] or '없음'}"
            )
    else:
        st.caption("※ 관련 법령명이 직접 검색되지 않았습니다. (API 2회 시도)")
