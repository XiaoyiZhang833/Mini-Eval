from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from evaluation_view import render_evaluation_panel, render_option_pool_manager_tool
from i18n import init_i18n_state, patch_streamlit_i18n, set_language
from sandbox_view import render_sandbox_panel
from session_state_utils import init_session_state

# 页面基础配置：宽屏布局，侧边栏默认展开
st.set_page_config(page_title="Mini Eval", layout="wide", initial_sidebar_state="expanded")


def _get_page_stage() -> str:
    if (
        not st.session_state.get("records")
        and not st.session_state.get("pending_records")
        and st.session_state.get("project_entry_state", "entry") == "entry"
    ):
        return "entry"
    return "workspace"


def _sync_sidebar_action() -> None:
    current_stage = _get_page_stage()
    previous_stage = st.session_state.get("_sidebar_stage")
    current_epoch = int(st.session_state.get("_sidebar_action_epoch", 0) or 0)

    if previous_stage is None:
        st.session_state._sidebar_stage = current_stage
        if current_stage != "entry":
            st.session_state._sidebar_action = "close"
            st.session_state._sidebar_action_epoch = current_epoch + 1
        return

    if previous_stage == current_stage:
        return

    st.session_state._sidebar_stage = current_stage
    st.session_state._sidebar_action = "open" if current_stage == "entry" else "close"
    st.session_state._sidebar_action_epoch = current_epoch + 1


def _apply_sidebar_action() -> None:
    action = str(st.session_state.get("_sidebar_action", "")).strip()
    epoch = int(st.session_state.get("_sidebar_action_epoch", 0) or 0)
    if not action or epoch <= 0:
        return

    components.html(
        f"""
        <script>
        (function() {{
            const action = {action!r};
            const epoch = {epoch};
            const token = `${{action}}:${{epoch}}`;
            const storageKey = 'mini-eval-sidebar-action';

            function applyAction() {{
                const lastApplied = window.sessionStorage.getItem(storageKey);
                if (lastApplied === token) {{
                    return true;
                }}

                const doc = window.parent.document;
                const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                if (!sidebar) {{
                    return false;
                }}

                const expanded = sidebar.getAttribute('aria-expanded') === 'true';
                const shouldToggle =
                    (action === 'close' && expanded) ||
                    (action === 'open' && !expanded);

                if (shouldToggle) {{
                    const toggleButton = doc.querySelector(
                        'button[aria-label="Close sidebar"], button[aria-label="Open sidebar"], [data-testid="collapsedControl"]'
                    );
                    if (!toggleButton) {{
                        return false;
                    }}
                    toggleButton.click();
                }}

                window.sessionStorage.setItem(storageKey, token);
                return true;
            }}

            let attempts = 0;
            const timer = window.setInterval(() => {{
                attempts += 1;
                if (applyAction() || attempts >= 20) {{
                    window.clearInterval(timer);
                }}
            }}, 150);
        }})();
        </script>
        """,
        height=0,
        width=0,
    )

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
_sync_sidebar_action()
_apply_sidebar_action()

with st.sidebar:
    can_switch_language = (
        not st.session_state.get("records")
        and not st.session_state.get("pending_records")
        and st.session_state.get("project_entry_state", "entry") == "entry"
    )

    if can_switch_language:
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
    render_option_pool_manager_tool(current_item)
    st.caption("Prompt 调试沙盒默认隐藏，展开后可进行单条调试与批量重跑。")
    with st.expander("Prompt 调试沙盒", expanded=False):
        render_sandbox_panel(current_item)
