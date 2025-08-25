#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_patch_dedup.py
- Minimal, layout-safe patcher for your Streamlit app.py
- Fixes two issues:
  (1) Duplicate assistant answers rendered twice
  (2) NameError in _current_q_and_answer when dict checks are missing
- It only edits targeted blocks; everything else is untouched.
Usage:
  1) Place this file in the same folder as your app.py
  2) Run:  python auto_patch_dedup.py
  3) It creates app.backup.py and app.patched.py, and prints a unified diff.
"""
from __future__ import annotations
from pathlib import Path
import re, sys, difflib

ROOT = Path('.')
APP = ROOT / 'app.py'
if not APP.exists():
    print("ERROR: app.py not found in current directory.")
    sys.exit(1)

src = APP.read_text(encoding='utf-8', errors='ignore')
orig = src

# --- Patch A: _current_q_and_answer safe body ---
pat_current = re.compile(r'(def\s+_current_q_and_answer\s*\(\s*\)\s*:\s*)(.*?)(?=\n\s*def\s)', re.DOTALL)
safe_body = r"""
    msgs = st.session_state.get("messages", []) or []
    # get last non-empty user and assistant safely
    last_q = next((m for m in reversed(msgs) if isinstance(m, dict) and m.get("role")=="user" and (m.get("content") or "").strip()), None)
    last_a = next((m for m in reversed(msgs) if isinstance(m, dict) and m.get("role")=="assistant" and (m.get("content") or "").strip()), None)
    q_txt = last_q.get("content", "") if isinstance(last_q, dict) else ""
    a_txt = last_a.get("content", "") if isinstance(last_a, dict) else ""
    return q_txt, a_txt
"""
def repl_current(m):
    return m.group(1) + safe_body

if pat_current.search(src):
    src = pat_current.sub(repl_current, src, count=1)
else:
    # If not found, do nothing (safe).
    pass

# --- Patch B: _append_message dedup on last item ---
pat_append = re.compile(r'(def\s+_append_message\s*\(\s*role\s*:\s*str\s*,\s*content\s*:\s*str.*?\)\s*:\s*)(.*?)(?=\n\s*def\s)', re.DOTALL)
append_guard = r"""
    txt = (content or "").strip()
    is_code_only = (txt.startswith("```") and txt.endswith("```"))
    if not txt or is_code_only:
        return
    msgs = st.session_state.get("messages", [])
    if msgs and isinstance(msgs[-1], dict) and msgs[-1].get("role")==role and (msgs[-1].get("content") or "").strip()==txt:
        # skip exact duplicate of the last message (role+content)
        return
    st.session_state.messages.append({"role": role, "content": txt, **extra})
"""
def repl_append(m):
    # Replace function body with guarded version but keep the original def line
    return m.group(1) + append_guard

if pat_append.search(src):
    src = pat_append.sub(repl_append, src, count=1)

# --- Patch C: Render-loop guard (skip consecutive identical assistant bubbles) ---
# We try to find the main render-loop: "for i, m in enumerate(st.session_state.messages):"
loop_pat = re.compile(r'(\n[ \t]*for\s+i,\s*m\s+in\s+enumerate\(\s*st\.session_state\.messages\s*\)\s*:\s*\n)')
def add_dedup_guard(match):
    indent = ' ' * (len(match.group(1)) - len(match.group(1).lstrip('\n')))
    guard = indent + "    # --- UI dedup guard: skip if same assistant content as previous ---\n" + \
            indent + "    if isinstance(m, dict) and m.get('role')=='assistant':\n" + \
            indent + "        _t = (m.get('content') or '').strip()\n" + \
            indent + "        if '_prev_assistant_txt' not in st.session_state:\n" + \
            indent + "            st.session_state['_prev_assistant_txt'] = ''\n" + \
            indent + "        if _t and _t == st.session_state.get('_prev_assistant_txt',''):\n" + \
            indent + "            continue\n" + \
            indent + "        st.session_state['_prev_assistant_txt'] = _t\n"
    return match.group(1) + guard

src = loop_pat.sub(add_dedup_guard, src, count=1)

# Write outputs
backup = ROOT / 'app.backup.py'
patched = ROOT / 'app.patched.py'
backup.write_text(orig, encoding='utf-8')
patched.write_text(src, encoding='utf-8')

# Print unified diff for user visibility
diff = difflib.unified_diff(orig.splitlines(True), src.splitlines(True), fromfile='app.py', tofile='app.patched.py', n=2)
print(''.join(diff))
print("\\nDone. Created:", str(patched))
