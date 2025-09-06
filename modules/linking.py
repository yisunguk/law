# modules/linking.py — CLEAN
from __future__ import annotations
import re
from typing import Dict, List, Tuple

# 약칭/별칭 보정
ALIAS_MAP: Dict[str, str] = {
    "형소법": "형사소송법",
    "민소법": "민사소송법",
    "민집법": "민사집행법",
    "중대재해처벌법": "중대재해 처벌 등에 관한 법률",
    "중처법": "중대재해 처벌 등에 관한 법률",
}

# 텍스트에서 "법령명 제N조(의M)" 찾기
ARTICLE_PAT = re.compile(
    r'(?P<law>[가-힣A-Za-z0-9·()\s]{2,40})\s*제(?P<num>\d{1,4})조(?P<ui>(의\d{1,3}){0,2})'
)

def _normalize_law_name(name: str) -> str:
    return ALIAS_MAP.get((name or "").strip(), (name or "").strip())

def _norm_art(label: str) -> str:
    """
    공백/형태 변형을 표준 '제N조' 또는 '제N조의M' 형태로 정리.
    """
    s = (label or "").replace(" ", "")
    m = re.search(r'제?(\d{1,4})조(의\d{1,3})?', s)
    if not m:
        # 숫자만 온 경우도 허용: "83" → "제83조"
        m2 = re.search(r'(\d{1,4})(의\d{1,3})?', s)
        if not m2:
            return (label or "").strip()
        return f"제{m2.group(1)}조{m2.group(2) or ''}"
    return f"제{m.group(1)}조{m.group(2) or ''}"

def make_deep_article_url(law_name: str, article_label: str) -> str:
    """
    law.go.kr은 /법령/<법령명>/<제N조의M> 한글 경로를 지원.
    (절대 인코딩하지 말 것)
    """
    law = _normalize_law_name(law_name)
    art = _norm_art(article_label)
    return f"https://law.go.kr/법령/{law}/{art}"

# 공식 엔트리(과거 이름 하위호환 포함)
def deep_article_url(law: str, art_label: str) -> str:
    return make_deep_article_url(law, art_label)

# 과거 코드 하위호환
_deep_article_url = deep_article_url

def extract_article_citations(text: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for m in ARTICLE_PAT.finditer(text or ""):
        law = _normalize_law_name(m.group("law"))
        art = f"제{m.group('num')}조{m.group('ui') or ''}"
        found.append((law, art))
    # 유니크
    uniq = []
    seen = set()
    for law, art in found:
        key = (law.strip(), art.strip())
        if key in seen: continue
        seen.add(key); uniq.append(key)
    return uniq

def render_article_links(citations: List[Tuple[str, str]]) -> str:
    if not citations: return ""
    lines = ["", "### 참고 링크(조문)"]
    for law, art in sorted(citations):
        url = make_deep_article_url(law, art)
        lines.append(f"- [{law} {art}]({url})")
    return "\n".join(lines)

def merge_article_links_block(text: str) -> str:
    citations = extract_article_citations(text)
    block = render_article_links(citations)
    if not block: return text
    pat_block = re.compile(r'\n### 참고 링크\(조문\)[\s\S]*$', re.M)
    return pat_block.sub(block, text) if pat_block.search(text) else text.rstrip() + "\n" + block + "\n"

def make_pretty_article_url(law_name: str, article_label: str) -> str:
    # pretty 딥링크 = law.go.kr/법령/<법령명>/<제N조(의M)>
    return make_deep_article_url(law_name, article_label)

__all__ = [
    "deep_article_url", "_deep_article_url",
    "make_deep_article_url", "make_pretty_article_url",  # ← 추가
    "extract_article_citations", "render_article_links", "merge_article_links_block",
]
