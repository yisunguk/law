# modules/linking.py — 한글 주소 유틸 (REPLACE)
from urllib.parse import quote
import os, contextlib, re, html

ALIAS_MAP = {"형소법":"형사소송법","민소법":"민사소송법","민집법":"민사집행법"}

def _normalize_law_name(name: str) -> str:
    return ALIAS_MAP.get((name or "").strip(), (name or "").strip())

def _normalize_article_label(s: str) -> str:
    s = (s or "").strip()
    if not s: return ""
    if s.isdigit(): return f"제{s}조"
    if s.startswith("제") and "조" in s: return s
    if s.endswith("조") and s[:-1].isdigit(): return "제"+s
    return s

def make_pretty_article_url(law_name: str, article_label: str) -> str:
    return f"https://law.go.kr/법령/{quote(_normalize_law_name(law_name))}/{quote(_normalize_article_label(article_label))}"

def make_pretty_law_main_url(law_name: str) -> str:
    return f"https://law.go.kr/법령/{quote(_normalize_law_name(law_name))}"

def resolve_article_url(law_name: str, article_label: str) -> str:
    return make_pretty_article_url(law_name, article_label)
