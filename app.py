# -*- coding: utf-8 -*-
"""
app.py — 법제처 국가법령정보 공유서비스(OpenAPI) 검색 앱 (Streamlit)
- data.go.kr 발급 serviceKey 사용 (XML 응답)
- 법령 검색(law target) 기본 구현 + 링크 절대경로 보정
- 키 마스킹/오류코드 매핑/캐싱/간단한 진단 포함

환경변수:
  - LAW_API_KEY: 공공데이터포털 인증키(Decoding 전 원문 그대로)
실행:
  streamlit run app.py
"""

from __future__ import annotations
import os
import sys
import time
import traceback
from typing import List, Tuple, Optional, Dict, Any

import requests
import xml.etree.ElementTree as ET
import streamlit as st

# ---------------------------------------------
# 설정값
# ---------------------------------------------
LAW_API_KEY = os.getenv("LAW_API_KEY", "").strip()
LAW_SEARCH_URLS = (
    "https://apis.data.go.kr/1170000/law/lawSearchList.do",
    "http://apis.data.go.kr/1170000/law/lawSearchList.do",
)
DEFAULT_NUM_ROWS = 10
TIMEOUT_SEC = 15
CACHE_TTL = 300  # seconds

# ---------------------------------------------
# 유틸
# ---------------------------------------------

def mask_key(k: str, show: int = 6) -> str:
    """민감한 키를 UI/로그에서 마스킹."""
    k = (k or "").strip()
    return k[:show] + "…" + k[-4:] if len(k) > show + 4 else ("*" * len(k))


def to_abs_law_url(link: str) -> str:
    """법제처 응답의 상대경로('/DRF/...', '/LSW/...')를 절대 URL로 변환."""
    if not link:
        return ""
    link = link.strip()
    if link.startswith("/"):
        return f"https://www.law.go.kr{link}"
    if link.startswith("http://") or link.startswith("https://"):
        return link
    # 그 외도 절대경로로 가정(예외적 케이스)
    return f"https://www.law.go.kr/{link.lstrip('/')}"


ERROR_MAP = {
    "00": "성공",
    "01": "잘못된 요청 파라미터입니다.",
    "02": "인증실패: 인증키 오류입니다. data.go.kr에서 발급받은 키를 확인하세요.",
    "03": "인증실패: 필수 파라미터 누락입니다.",
    "09": "시스템 오류: 일시적 오류입니다. 잠시 후 다시 시도하세요.",
    "99": "시스템 오류: 정의되지 않은 오류입니다.",
}


# ---------------------------------------------
# API 호출
# ---------------------------------------------
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def search_law_data(query: str, num_rows: int = DEFAULT_NUM_ROWS) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    법령검색 API 호출(target=law). 결과(list), 사용 URL, 오류메시지를 반환.
    - serviceKey는 원문 그대로 params에 전달(이중 인코딩 방지)
    - XML resultCode 체크 후 매핑
    """
    if not LAW_API_KEY:
        return [], None, "LAW_API_KEY 환경변수가 설정되지 않았습니다."

    params = {
        "serviceKey": LAW_API_KEY,  # 원문 그대로 전달
        "target": "law",
        "query": query if (query or "").strip() else "*",
        "numOfRows": max(1, min(100, int(num_rows or 1))),
        "pageNo": 1,
    }

    last_err: Optional[Exception] = None

    for url in LAW_SEARCH_URLS:
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT_SEC)
            resp.raise_for_status()

            # XML 파싱
            root = ET.fromstring(resp.text)

            # 결과코드 확인
            result_code = root.findtext(".//resultCode")
            result_msg = root.findtext(".//resultMsg")
            if result_code and result_code != "00":
                msg = ERROR_MAP.get(result_code, f"API 오류 코드 {result_code}")
                if result_msg and result_msg.lower() != "success":
                    msg = f"{msg} / 상세: {result_msg}"
                return [], url, msg

            rows: List[Dict[str, Any]] = []
            for law in root.findall(".//law"):
                name = (law.findtext("법령명한글", default="") or "").strip()
                nick = (law.findtext("법령약칭명", default="") or "").strip()
                dept = (law.findtext("소관부처명", default="") or "").strip()
                kind = (law.findtext("법령구분명", default="") or "").strip()
                eff  = (law.findtext("시행일자", default="") or "").strip()
                pub  = (law.findtext("공포일자", default="") or "").strip()
                link_rel = (law.findtext("법령상세링크", default="") or "").strip()
                link_abs = to_abs_law_url(link_rel)

                rows.append({
                    "법령명": name,
                    "법령약칭명": nick,
                    "소관부처명": dept,
                    "법령구분명": kind,
                    "시행일자": eff,
                    "공포일자": pub,
                    "법령상세링크": link_abs,
                })
            return rows, url, None

        except Exception as e:
            last_err = e
            continue

    return [], None, f"법제처 API 연결 실패: {last_err}"


# ---------------------------------------------
# UI
# ---------------------------------------------
st.set_page_config(page_title="국가법령정보 검색", page_icon="⚖️", layout="wide")
st.title("⚖️ 국가법령정보 공유서비스 – 법령 검색")

with st.sidebar:
    st.header("설정")
    safe_log = st.toggle("디버그 로그(키 마스킹)", value=False, help="요청/응답 일부를 출력합니다. 운영환경에서는 끄세요.")
    st.caption(f"인증키 상태: {'OK' if LAW_API_KEY else '미설정'}")

query = st.text_input("검색어", value="*", help="미입력 시 전체(*) 검색")
num_rows = st.number_input("한 페이지 결과 수(numOfRows)", min_value=1, max_value=100, value=DEFAULT_NUM_ROWS, step=1)

col_run, col_diag = st.columns([1, 1])
run = col_run.button("검색 실행", type="primary")

if run:
    with st.spinner("법령을 검색 중…"):
        rows, used_url, err = search_law_data(query, int(num_rows))

    if safe_log and used_url:
        st.caption(f"요청 URL: {used_url}")
        st.caption(f"serviceKey: {mask_key(LAW_API_KEY)} / query='{query}' / numOfRows={num_rows}")

    if err:
        st.error(err)
    else:
        st.success(f"{len(rows)}건 수신")
        if rows:
            # 표 렌더링
            import pandas as pd
            df = pd.DataFrame(rows)
            # 링크 컬럼을 클릭 가능하게 렌더
            def _mk_link(u: str) -> str:
                if not u:
                    return ""
                return f"<a href='{u}' target='_blank'>상세보기</a>"

            df_display = df.copy()
            df_display["상세"] = df_display["법령상세링크"].map(_mk_link)
            df_display = df_display.drop(columns=["법령상세링크"])  # 원본 링크 컬럼은 숨김

            st.write("검색 결과")
            st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
        else:
            st.info("검색 결과가 없습니다. 검색어를 변경해 보세요.")

# ---------------------------------------------
# 하단 도움말
# ---------------------------------------------
with st.expander("도움말/주의사항"):
    st.markdown(
        """
        - 이 앱은 **data.go.kr**에서 발급받은 **인증키(ServiceKey)**를 사용합니다.
        - 법제처 응답의 `법령상세링크`는 상대경로인 경우가 많아, 자동으로 `https://www.law.go.kr`을 붙여 절대경로로 변환합니다.
        - 오류코드 예시: 02(인증실패-키오류), 03(필수 파라미터 누락), 09/99(일시적 시스템 오류)
        - 캐시 TTL은 {CACHE_TTL}s 입니다. 잦은 질의 시 서버 부하/쿼터를 고려하세요.
        """
    )

# ---------------------------------------------
# 진단 도구(선택)
# ---------------------------------------------
with col_diag:
    with st.expander("간단 진단"):
        if st.button("엔드포인트 상태 점검"):
            lines = []
            for u in LAW_SEARCH_URLS:
                ok = False
                t0 = time.time()
                try:
                    # HEAD 먼저
                    r = requests.head(u, timeout=5)
                    if r.status_code < 400:
                        ok = True
                    else:
                        # 폴백 GET
                        r = requests.get(u, timeout=5)
                        ok = r.status_code < 400
                except Exception:
                    ok = False
                dt = (time.time() - t0) * 1000
                lines.append(f"{u} -> {'OK' if ok else 'FAIL'} ({dt:.0f} ms)")
            st.code("\n".join(lines))

# 끝
