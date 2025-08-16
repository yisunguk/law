st.markdown("""
<style>
/* 업로더 기본 정리 */
div[data-testid="stFileUploader"]{background:transparent;border:none;padding:0;margin:0;}
div[data-testid="stFileUploader"] section{padding:0;border:none;background:transparent;}
div[data-testid="stFileUploader"] section>div{padding:0;margin:0;}
div[data-testid="stFileUploader"] label{display:none;}  /* 라벨 숨김 */

/* 드롭존 테두리/배경 제거 */
div[data-testid="stFileUploaderDropzone"]{
  border:none !important; background:transparent !important;
  padding:0 !important; margin:0 !important;
}

/* ✅ 드롭존 안의 모든 요소를 일단 숨기고 */
div[data-testid="stFileUploaderDropzone"] *{
  display:none !important;
}
/* ✅ 안내 문구(small)와 Browse files 버튼만 다시 보이게 */
div[data-testid="stFileUploaderDropzone"] small{
  display:inline !important;
}
div[data-testid="stFileUploaderDropzone"] button{
  display:inline-flex !important;
}
</style>
""", unsafe_allow_html=True)
