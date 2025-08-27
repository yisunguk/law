# modules/linking.py
from __future__ import annotations
import re
from urllib.parse import quote
from typing import Dict, List, Tuple

# 자주 쓰는 약칭 보정(원하는 대로 추가/수정)
ALIAS_MAP: Dict[str, str] = {
    "형소법": "형사소송법",
    "민소법": "민사소송법",
    "민집법": "민사집행법",
    # "형법": "형법",  # 동일명은 생략 가능
}

# "민법 제839조의2" 같은 패턴 추출(중복 허용되므로 나중에 set으로 유니크 처리)
ARTICLE_PAT = re.compile(
    r'(?P<law>[가-힣A-Za-z0-9·()\s]{2,40})\s*제(?P<num>\d{1,4})조(?P<ui>(의\d{1,3}){0,2})'
)

def _normalize_law_name(name: str) -> str:
    name = name.strip()
    return ALIAS_MAP.get(name, name)

# modules/linking.py
from __future__ import annotations
import re
# from urllib.parse import quote  # <- 삭제
from typing import Dict, List, Tuple

# ... (중략)

def make_deep_article_url(law_name: str, article_label: str) -> str:
    """
    law.go.kr은 /법령/<법령명>/<제N조의M> 한글 경로를 지원합니다.
    예) /법령/민법/제839조의2, /법령/민사소송법/제163조
    """
    # 🚫 인코딩(quote) 금지: 한글 그대로 사용
    law = (law_name or "").strip()
    art = (article_label or "").strip()
    return f"https://law.go.kr/법령/{law}/{art}"


def extract_article_citations(text: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for m in ARTICLE_PAT.finditer(text or ""):
        law = _normalize_law_name(m.group("law"))
        art = f"제{m.group('num')}조{m.group('ui') or ''}"
        found.append((law, art))
    # 유니크 보장(동일 (법령, 조문) 1회만)
    return list({(l, a) for (l, a) in found})

def render_article_links(citations: List[Tuple[str, str]]) -> str:
    if not citations:
        return ""
    lines = ["", "### 참고 링크(조문)",]
    for law, art in sorted(citations):
        url = make_deep_article_url(law, art)
        lines.append(f"- [{law} {art}]({url})")
    return "\n".join(lines)

def merge_article_links_block(text: str) -> str:
    """
    본문 어디에서든 발견한 '법령명 제N조(의M)'를 모아
    문서 맨 끝에 '참고 링크(조문)' 블록을 추가(또는 갱신)합니다.
    """
    citations = extract_article_citations(text)
    block = render_article_links(citations)
    if not block:
        return text

    # 기존 '참고 링크(조문)' 블록이 있으면 교체, 없으면 맨 끝에 추가
    pat_block = re.compile(r'\n### 참고 링크\(조문\)[\s\S]*$', re.M)
    if pat_block.search(text):
        return pat_block.sub(block, text)
    return text.rstrip() + "\n" + block + "\n"
