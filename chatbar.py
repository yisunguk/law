# chatbar.py — Enter-to-send (ChatGPT-style) + optional file upload
# - Enter      → 전송
# - Shift+Enter→ 줄바꿈
# - IME(한글 조합) 중 Enter는 자동 처리 (st.chat_input 기본 동작)
import streamlit as st
from typing import List, Optional
import html

DEFAULT_ACCEPT = ["pdf", "docx", "txt"]

def chatbar(
    placeholder: str = "메시지를 입력하세요…",
    button_label: str = "보내기",
    accept: Optional[List[str]] = None,
    key_prefix: str = "chatbar",
    max_files: int = 5,
    max_size_mb: int = 15,
):
    if accept is None:
        accept = DEFAULT_ACCEPT

    # ===== 하단 고정 + 본문 가림 방지 + 기본 스타일 =====
    st.markdown(f"""
<style>
.block-container{{ padding-bottom:120px !important; }}
.cb2-wrap{{
  position:fixed; left:0; right:0; bottom:0;
  border-top:1px solid rgba(255,255,255,.12);
  background:rgba(20,20,20,.95);
  backdrop-filter:blur(6px);
  z-index:1000;
}}
[data-theme="light"] .cb2-wrap{{
  background:rgba(255,255,255,.95);
  border-top:1px solid #e5e5e5;
}}
.cb2-wrap .stForm, .cb2-wrap .stForm>div{{ max-width:1020px; margin:0 auto; width:100%; }}
.cb2-row{{ display:grid; grid-template-columns:0.22fr 1fr 0.18fr; gap:8px; padding:8px 12px; }}
@media (max-width: 900px){{ .cb2-row{{ grid-template-columns:1fr; }} }}
/* 업로더 드롭존 */
div[data-testid="stFileUploader"]{{background:transparent;border:none;padding:0;margin:0;}}
div[data-testid="stFileUploader"] section{{padding:0;border:none;background:transparent;}}
div[data-testid="stFileUploader"] section>div{{padding:0;margin:0;}}
div[data-testid="stFileUploader"] label{{display:none;}}
div[data-testid="stFileUploaderDropzone"]{{
  border:2px dashed #888 !important; border-radius:8px !important;
  background:transparent !important; padding:10px !important; margin:0 !important; text-align:center;
}}
div[data-testid="stFileUploaderDropzone"] *{{ display:none !important; }}
div[data-testid="stFileUploaderDropzone"] small{{
  display:block !important; font-size:0.9rem !important; color:#777 !important; margin:5px 0;
}}
div[data-testid="stFileUploaderDropzone"] button{{ display:none !important; visibility:hidden !important; }}
/* 텍스트 영역 높이(한 줄 느낌) */
.cb2-text textarea{{ min-height:40px !important; height:40px !important; }}
</style>

<script>
// 엔터=전송 / Shift+Enter=줄바꿈 + 힌트 숨김
(function(){{
  const formIdPrefix = "{html.escape(key_prefix)}-form";
  function getForm(){{
    return window.parent.document.querySelector(`form[id^="${{formIdPrefix}}"]`);
  }}
  function getTextarea(form){{
    // aria-label은 st.text_area의 label 텍스트가 들어갑니다("메시지")
    return form ? form.querySelector('textarea[aria-label="메시지"]') : null;
  }}
  function getSubmitBtn(form){{
    if(!form) return null;
    // 폼 내부 버튼 중 표시 텍스트가 button_label과 일치하는 버튼 탐색
    const btns = Array.from(form.querySelectorAll('button'));
    const target = btns.find(b => (b.textContent || '').trim() === "{html.escape(button_label)}");
    return target || btns.pop() || null;
  }}
  function hideCtrlEnterHint(){{
    // "Press Ctrl+Enter to submit form" 문구가 있으면 숨김
    const all = window.parent.document.querySelectorAll('div, span, small');
    for(const el of all){{
      const t = (el.textContent || '').trim();
      if(t === "Press Ctrl+Enter to submit form"){{
        el.style.display = 'none';
      }}
    }}
  }}

  function bind(){{
    const form = getForm();
    const ta = getTextarea(form);
    const btn = getSubmitBtn(form);
    if(!form || !ta || !btn) return;

    // 중복 바인딩 방지
    if(ta.dataset._enterBind === "1") return;
    ta.dataset._enterBind = "1";

    ta.addEventListener('keydown', function(e){{
      if(e.key === 'Enter' && !e.shiftKey){{
        e.preventDefault();
        // 버튼 클릭으로 제출
        btn.click();
        // 제출 후 포커스 복귀(UX)
        setTimeout(()=>ta.focus(), 50);
      }}
    }});

    hideCtrlEnterHint();
  }}

  // DOM 변화를 계속 보며 폼이 재랜더링돼도 바인딩 유지
  const obs = new MutationObserver(() => bind());
  obs.observe(window.parent.document.body, {{ childList: true, subtree: true }});
  // 초기 1회
  document.addEventListener('DOMContentLoaded', bind);
  bind();
}})();
</script>
""", unsafe_allow_html=True)

    submitted = False
    text_val = ""
    files = []

    # 하단 고정 래퍼
    st.markdown('<div class="cb2-wrap">', unsafe_allow_html=True)
    with st.form(key=f"{key_prefix}-form", clear_on_submit=True):
        st.markdown('<div class="cb2-row">', unsafe_allow_html=True)

        files = st.file_uploader(
            "첨부", type=accept, accept_multiple_files=True,
            key=f"{key_prefix}-uploader", label_visibility="collapsed",
            help=f"최대 {max_files}개, 파일당 {max_size_mb}MB",
        )

        # label="메시지" → aria-label로 노출되며 JS가 이걸 사용합니다.
        text_val = st.text_area(
            "메시지",
            placeholder=placeholder,
            key=f"{key_prefix}-text",
            label_visibility="collapsed",
            height=40,
        )

        submitted = st.form_submit_button(button_label, use_container_width=True, type="primary")

        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    return submitted, (text_val or '').strip(), files
