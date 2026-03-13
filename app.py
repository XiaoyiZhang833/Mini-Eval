from pathlib import Path

import streamlit as st
from evaluation_view import render_evaluation_panel
from i18n import init_i18n_state, patch_streamlit_i18n, set_language
from sandbox_view import render_sandbox_panel
from session_state_utils import init_session_state

# 页面基础配置：宽屏布局
st.set_page_config(page_title="Mini Eval", layout="wide")

st.markdown(
    """
	<style>
	/* 减少页面顶部留白，让内容整体上移 */
	.block-container {
		padding-top: 1.0rem !important;
	}
    /* 侧边栏展开时固定为可用范围上限，避免每次手动拉宽 */
    section[data-testid="stSidebar"][aria-expanded="true"] {
        width: 420px !important;
        min-width: 420px !important;
        max-width: 420px !important;
    }
	/* 压缩主标题上下间距 */
	h1 {
		margin-top: 0 !important;
		margin-bottom: 0.4rem !important;
	}
	</style>
	""",
    unsafe_allow_html=True,
)

# 顶部标题仅在初始页显示
if not st.session_state.get("records"):
    st.title("Mini Eval")


EXAMPLE_FILE_PATH = Path(__file__).with_name("example.xlsx")

init_session_state()
init_i18n_state()
patch_streamlit_i18n()

with st.sidebar:
    lang_choice = st.selectbox(
        "Language / 语言",
        options=["中文", "English"],
        index=0 if st.session_state.get("ui_language", "zh") == "zh" else 1,
        key="ui_language_selector",
    )
    set_language("en" if lang_choice == "English" else "zh")

# 主评测区
current_item = render_evaluation_panel(EXAMPLE_FILE_PATH)

# 侧边栏沙盒：默认收起，按需展开
with st.sidebar:
    st.markdown("### 工具面板")
    st.caption("Prompt 调试沙盒默认隐藏，展开后可进行单条调试与批量重跑。")
    with st.expander("Prompt 调试沙盒", expanded=False):
        render_sandbox_panel(current_item)
