import re
from typing import Any

import streamlit as st

_SUPPORTED_LANGS = {"zh", "en"}
_PATCHED = False


_TRANSLATIONS = {
    "工具面板": "Tools",
    "### 工具面板": "### Tools",
    "Prompt 调试沙盒默认隐藏，展开后可进行单条调试与批量重跑。": "The Prompt debug sandbox is hidden by default. Expand to run single-item debugging and batch reruns.",
    "Prompt 调试沙盒": "Prompt Debug Sandbox",
    "当前环境未安装 openai 库，请先执行：pip install openai": "The openai package is not installed. Run: pip install openai",
    "批量任务已启动。": "Batch task started.",
    "任务已中断。": "Task interrupted.",
    "#### 任务结果下载": "#### Download Task Results",
    "导出 CSV": "Export CSV",
    "导出 JSON": "Export JSON",
    "导出 Excel": "Export Excel",
    "适用于所有评测模式，可单条重生成，也可在 System Prompt 场景批量重跑。": "Works in all evaluation modes. Supports single-item regeneration and batch reruns with System Prompt.",
    "模型名称": "Model Name",
    "OpenAI API Key（可选，留空则使用环境变量 OPENAI_API_KEY）": "OpenAI API Key (optional, leave empty to use OPENAI_API_KEY)",
    "Base URL（可选，用于本地模型或兼容 OpenAI 的网关）": "Base URL (optional, for local models or OpenAI-compatible gateways)",
    "例如：https://api.openai.com/v1 或你的本地网关地址": "Example: https://api.openai.com/v1 or your local gateway URL",
    "重新生成": "Regenerate",
    "User Prompt 不能为空，请输入后再重新生成。": "User Prompt cannot be empty.",
    "未检测到 API Key。请输入 OpenAI API Key 或设置环境变量 OPENAI_API_KEY。": "API key not found. Please enter OpenAI API Key or set OPENAI_API_KEY.",
    "生成完成": "Generation completed.",
    "模型返回结果": "Model Output",
    "### 批量重跑": "### Batch Rerun",
    "使用当前沙盒中的 System Prompt，与全部样本的 user prompt 组合后批量调用 API。": "Use current sandbox System Prompt with all sample user prompts for batch API calls.",
    "批量重跑全部样本": "Rerun All Samples",
    "中断任务": "Stop Task",
    "失败样本重试": "Retry Failed Samples",
    "System Prompt 不能为空。": "System Prompt cannot be empty.",
    "任务已启动，正在处理中...": "Task started, running...",
    "已请求中断，当前样本处理完成后停止。": "Stop requested. Task will stop after current item.",
    "失败样本重试任务已启动。": "Retry task for failed samples started.",
    "批量任务已完成": "Batch task completed",
    "字段映射无效，请重新选择。": "Invalid field mapping. Please select again.",
    "Prompt 字段不能同时作为 Output 字段，请重新选择。": "Prompt field cannot also be an Output field.",
    "导入后没有可用数据，请检查 prompt/output 是否为空。": "No valid rows after import. Check whether prompt/output fields are empty.",
    "请选择评测模式后再进入评测。": "Please select an evaluation mode first.",
    "请选择评测模式": "Please select evaluation mode",
    "直接判断LLM结果": "Directly judge LLM output",
    "人工输入结果": "Manual input result",
    "确认进入评测": "Enter Evaluation",
    "取消": "Cancel",
    "是否清空文件": "Clear current data?",
    "清空后将回到初始页面，当前已加载的数据和评测进度不会保留。": "Clearing will return to the entry page and discard current loaded data and progress.",
    "是否清空文件？清空后将回到初始页面，当前评测进度不会保留。": "Clear current data? This will return to the entry page and discard current progress.",
    "是": "Yes",
    "否": "No",
    "### 统计": "### Statistics",
    "### 浏览": "### Browse",
    "关闭": "Close",
    "关闭统计": "Close Statistics",
    "关闭浏览": "Close Browse",
    "请选择工作方式。": "Please choose how to start.",
    "加载存档": "Load Archive",
    "开始新项目": "Start New Project",
    "暂无存档文件，请先在评测页面点击“保存存档”。": "No archive files found. Please save one from the evaluation page first.",
    "请选择存档": "Select an archive",
    "确认加载": "Load",
    "删除存档": "Delete Archive",
    "返回": "Back",
    "确认删除": "Confirm Delete",
    "取消删除": "Cancel Delete",
    "评测区当前为空，请先加载数据。": "Evaluation area is empty. Please load data first.",
    "从 Excel 导入": "Import from Excel",
    "请先上传 Excel，然后在下方映射 prompt 和 output 字段。首行为表头，每行一条评测数据，id 将自动生成。": "Upload an Excel file, then map prompt and output columns below. First row is header; one row per sample; id will be generated automatically.",
    "#### 可选项": "#### Options",
    "使用 System Prompt": "Use System Prompt",
    "请输入固定的 System Prompt。启用后下一个页面将显示 system prompt 和 user prompt。": "Enter a fixed System Prompt. When enabled, the next page will show system prompt and user prompt.",
    "应用 System Prompt": "Apply System Prompt",
    "System Prompt 已应用。": "System Prompt applied.",
    "System Prompt 为空，应用后将不会生效。": "System Prompt is empty and will not take effect.",
    "当前已应用的 System Prompt：": "Currently applied System Prompt:",
    "你修改了 System Prompt 草稿，请点击应用 System Prompt按钮使其生效。": "System Prompt draft changed. Click Apply System Prompt to activate it.",
    "使用示例数据": "Use Example Data",
    "未找到示例文件 example.xlsx。": "Example file example.xlsx not found.",
    "在线获取结果（暂未开放）": "Fetch Results Online (Coming Soon)",
    "该功能将在后续版本提供，目前请使用 Excel 导入。": "This feature will be available in a future version. Please use Excel import for now.",
    "#### 字段映射": "#### Field Mapping",
    "当前数据": "Current Data",
    "请选择 Prompt 或文本字段": "Select Prompt or text field",
    "请选择 Prompt 字段": "Select Prompt field",
    "请选择 Output 字段（可多选）": "Select Output field(s)",
    "可选择一个或多个 Output 列。": "You can select one or more Output columns.",
    "确认字段映射并加载": "Confirm Mapping and Load",
    "已启用 System Prompt，请先点击应用 System Prompt按钮。": "System Prompt is enabled. Please click Apply System Prompt first.",
    "System Prompt 草稿尚未应用，请先点击应用 System Prompt按钮。": "System Prompt draft is not applied yet. Please click Apply System Prompt first.",
    "取消当前数据源": "Cancel Current Data Source",
    "显示 LLM 的结果": "Show LLM output",
    "当前为人工输入结果模式，LLM 输出已隐藏。": "Manual input mode is active. LLM output is hidden.",
    "人工输入方式": "Manual input mode",
    "选择": "Select",
    "手动输入": "Type manually",
    "从结果集合选择": "Select from result pool",
    "手动打字输入": "Type manually",
    "可从已有结果集合中选择，也可手动新增或删除选择项。": "Choose from existing result pool, or add/remove options manually.",
    "从结果集合中选择": "Select from result pool",
    "当前结果集合为空，请先新增选择项。": "Result pool is empty. Please add an option first.",
    "新增选择项": "Add option",
    "输入要新增到集合中的结果文本": "Enter text to add to result pool",
    "加入选择项": "Add to pool",
    "新增选择项不能为空。": "New option cannot be empty.",
    "该选择项已存在，无需重复添加。": "Option already exists.",
    "删除选择项": "Delete option",
    "暂无可删除的选择项": "No option to delete.",
    "人工输入结果": "Manual result",
    "请在这里输入当前样本的结果内容...": "Enter manual result for this sample...",
    " 保存并下一条": " Save and Next",
    "保存并下一条": "Save and Next",
    "人工输入结果不能为空，请填写后再保存。": "Manual result cannot be empty.",
    "当前数据不满足多输出模式（output 数量少于 2）。": "Current sample does not satisfy multi-output mode (less than 2 outputs).",
    "请先完成所有输出字段的标注。": "Please annotate all output fields first.",
    "采纳": "Accept",
    "拒绝": "Reject",
    " 采纳 (正确)": " Accept (Correct)",
    " 拒绝 (错误)": " Reject (Incorrect)",
    "未知时间": "Unknown time",
    "进度": "Progress",
    "解析失败": "Parse failed",
    "自动生成名称": "auto-generated name",
    "Excel 读取失败，请检查文件格式是否正确：": "Excel read failed. Please check file format: ",
    "调用模型失败：": "Model call failed: ",
    "正在使用模型 ": "Using model ",
    " 重新生成中...": " to regenerate...",
    "Excel 中没有可用数据或表头，请检查文件内容。": "No usable data or headers found in Excel. Please check the file content.",
    "当前环境未安装 pandas，无法读取 Excel。请先执行：pip install pandas openpyxl": "pandas is not installed. Cannot read Excel. Run: pip install pandas openpyxl",
    "检测到多输出数据：将对每个 output 分别判断。": "Detected multi-output data: each output will be judged separately.",
    "检测到多输出数据：将对每个 output 分别判断（各选各的），不使用集合总判断。": "Detected multi-output data: each output will be judged separately (independent choices; no set-level judgement).",
    "恭喜，所有数据评测完成！": "All data has been evaluated.",
    "统计": "Stats",
    "清空文件": "Clear",
    "浏览": "Browse",
    "保存存档": "Save Archive",
    "返回上一条": "Previous",
    "管理选择项": "Manage Options",
    "提示：上方 Output 区域是大模型输出；下方输入/选择区域是人工输出。": "Tip: The Output area above is the model output; the input/selection area below is the manual output.",
    "提示：每个卡片展示的是大模型输出；卡片下方输入/选择区域是对应字段的人工输出。": "Tip: Each card shows model output; the input/selection area below each card is the manual output for that field.",
    "LLM 输出已隐藏。请根据每个输入框上方的 Output 标签填写对应结果。": "LLM output is hidden. Please fill each input based on the Output label shown above it.",
    "可从已有结果集合中选择；新增/删除请在工具面板点击“管理选择项”。": "Choose from the existing result pool; to add or delete options, click Manage Options in the tools panel.",
    "当前结果集合为空，请在工具面板先新增选择项。": "Result pool is empty. Please add options first from the tools panel.",
    "请先完成标注。": "Please complete the annotation first.",
    "单输出标注": "Single-output annotation",
    "导出文件生成失败，请稍后重试。": "Failed to generate export file. Please try again later.",
    "当前没有可管理的数据。": "There is no data to manage right now.",
    "##### 🎯 标注操作": "##### 🎯 Annotation",
    "##### 📝 文本": "##### 📝 Text",
    "导出当前结果": "Export Results",
    "工具窗口": "Tool Window",
    "结果浏览（可编辑）": "Result Browser (Editable)",
    "表格修改将自动保存；判断列由后台自动生成。": "Table edits are auto-saved; judgement columns are generated automatically.",
    "返回上一个操作": "Undo Last Action",
    "完成总数": "Total Completed",
    "已评测数": "Evaluated",
    "当前 Accuracy": "Current Accuracy",
    "当前 Precision": "Current Precision",
    "当前 Recall": "Current Recall",
    "当前 F1": "Current F1",
    "F1 Score": "F1 Score",
    "完成样本数": "Completed Samples",
    "已标注输出数": "Labeled Outputs",
    "已完成样本数": "Completed Samples",
    "各 Output 指标": "Per-output Metrics",
    "各 Output 当前指标": "Current Per-output Metrics",
    "Output": "Output",
    "已标注数": "Labeled",
    "评测指标（直接判断模式）": "Evaluation Metrics (Direct Mode)",
    "评测指标（多输出模式）": "Evaluation Metrics (Multi-output Mode)",
    "评测指标（多输出人工输入模式）": "Evaluation Metrics (Multi-output Manual Mode)",
    "评测指标（人工输入结果模式）": "Evaluation Metrics (Manual Mode)",
    "当前统计（直接判断模式）": "Current Stats (Direct Mode)",
    "当前统计（多输出模式）": "Current Stats (Multi-output Mode)",
    "当前统计（多输出人工输入模式）": "Current Stats (Multi-output Manual Mode)",
    "当前统计（人工输入结果模式）": "Current Stats (Manual Mode)",
    "当前版本不支持弹窗，请升级 Streamlit。": "Current Streamlit version does not support dialogs. Please upgrade Streamlit.",
    "当前版本不支持弹窗，统计在页面内展示。": "Current Streamlit version does not support dialogs. Statistics are shown inline.",
    "当前版本不支持弹窗，浏览在页面内展示。": "Current Streamlit version does not support dialogs. Browser is shown inline.",
    "存档文件名": "Archive filename",
    "可选，不填自动生成": "Optional, auto-generated if empty",
    "覆盖保存": "Overwrite and Save",
    "取消覆盖": "Cancel Overwrite",
    "保存": "Save",
    "存档文件名无效，请重新输入。": "Invalid archive filename. Please try again.",
    "当前没有可保存的评测数据。": "No evaluation data to save.",
    "未找到指定存档文件。": "Specified archive not found.",
    "存档无有效 records 数据。": "Archive has no valid records data.",
    "多输出模式要求每条数据至少 2 个 output，当前样本 id=": "Multi-output mode requires at least 2 outputs per sample. Current sample id=",
    "不满足。": " does not meet the requirement.",
}

_PATTERN_TRANSLATIONS = [
    (
        re.compile(r"^当前第\s*(\d+)\s*条\s*/\s*共\s*(\d+)\s*条$"),
        lambda m: f"Item {m.group(1)} / {m.group(2)}",
    ),
    (
        re.compile(r"^数据已准备完成，共\s*(\d+)\s*条，正在等待选择评测模式。$"),
        lambda m: f"Data is ready: {m.group(1)} rows. Waiting for evaluation mode selection.",
    ),
    (
        re.compile(r"^确认删除存档：(.+)？删除后不可恢复。$"),
        lambda m: f"Confirm deleting archive: {m.group(1)}? This action cannot be undone.",
    ),
    (
        re.compile(r"^当前样本包含\s*(\d+)\s*个输出，请逐条标注（每行\s*(\d+)\s*个）。$"),
        lambda m: f"Current sample has {m.group(1)} outputs. Annotate each ({m.group(2)} per row).",
    ),
    (
        re.compile(r"^当前样本包含\s*(\d+)\s*个输出，请对每个输出分别标注（每行\s*(\d+)\s*个）。$"),
        lambda m: f"Current sample has {m.group(1)} outputs. Annotate each output separately ({m.group(2)} per row).",
    ),
    (
        re.compile(r"^任务完成：共\s*(\d+)\s*条，失败\s*(\d+)\s*条。$"),
        lambda m: f"Task completed: total {m.group(1)}, failed {m.group(2)}.",
    ),
    (
        re.compile(r"^任务进度：(\d+)/(\d+)$"),
        lambda m: f"Progress: {m.group(1)}/{m.group(2)}",
    ),
    (
        re.compile(r"^失败样本数：(\d+)$"),
        lambda m: f"Failed samples: {m.group(1)}",
    ),
    (
        re.compile(r"^当前管理：(.+)$"),
        lambda m: f"Currently managing: {m.group(1)}",
    ),
    (
        re.compile(r"^存档文件已存在：(.+)$"),
        lambda m: f"Archive file already exists: {m.group(1)}",
    ),
    (
        re.compile(r"^存档保存失败：(.+)$"),
        lambda m: f"Failed to save archive: {m.group(1)}",
    ),
    (
        re.compile(r"^存档已保存：(.+)$"),
        lambda m: f"Archive saved: {m.group(1)}",
    ),
    (
        re.compile(r"^检测到同名存档：(.+)，是否覆盖？$"),
        lambda m: f"Same archive name detected: {m.group(1)}. Overwrite?",
    ),
    (
        re.compile(r"^存档读取失败：(.+)$"),
        lambda m: f"Failed to read archive: {m.group(1)}",
    ),
    (
        re.compile(r"^已加载存档：(.+)$"),
        lambda m: f"Archive loaded: {m.group(1)}",
    ),
    (
        re.compile(r"^删除失败：(.+)$"),
        lambda m: f"Delete failed: {m.group(1)}",
    ),
    (
        re.compile(r"^已删除存档：(.+)$"),
        lambda m: f"Archive deleted: {m.group(1)}",
    ),
    (
        re.compile(r"^数据源：(.+)。请选择 Excel 中哪一列作为 Prompt，并可选择一个或多个 Output 列。$"),
        lambda m: f"Data source: {m.group(1)}. Select which column is Prompt, and one or more Output columns.",
    ),
    (
        re.compile(r"^Output：\n\n([\s\S]+)$"),
        lambda m: f"Output:\n\n{m.group(1)}",
    ),
    (
        re.compile(r"^(.+) 标注$"),
        lambda m: f"{m.group(1)} Annotation",
    ),
    (
        re.compile(r"^(.+) 人工输入方式$"),
        lambda m: f"{m.group(1)} Manual Input Mode",
    ),
    (
        re.compile(r"^(.+) 从结果集合中选择$"),
        lambda m: f"Select from pool: {m.group(1)}",
    ),
    (
        re.compile(r"^(.+) 的结果集合为空，请先为该字段新增选择项。$"),
        lambda m: f"Result pool for {m.group(1)} is empty. Please add options first.",
    ),
    (
        re.compile(r"^(.+) 新增选择项$"),
        lambda m: f"Add option for {m.group(1)}",
    ),
    (
        re.compile(r"^(.+) 删除选择项$"),
        lambda m: f"Delete option for {m.group(1)}",
    ),
    (
        re.compile(r"^(.+) 人工输入结果$"),
        lambda m: f"Manual result for {m.group(1)}",
    ),
    (
        re.compile(r"^(.+) 的人工输入结果不能为空。$"),
        lambda m: f"Manual result for {m.group(1)} cannot be empty.",
    ),
    (
        re.compile(r"^Excel 读取失败，请检查文件格式是否正确：(.+)$"),
        lambda m: f"Excel read failed. Please check file format: {m.group(1)}",
    ),
    (
        re.compile(r"^调用模型失败：(.+)$"),
        lambda m: f"Model call failed: {m.group(1)}",
    ),
    (
        re.compile(r"^正在使用模型\s+(.+)\s+重新生成中\.\.\.$"),
        lambda m: f"Regenerating with model {m.group(1)}...",
    ),
]


def init_i18n_state() -> None:
    if "ui_language" not in st.session_state:
        st.session_state.ui_language = "zh"


def get_language() -> str:
    lang = str(st.session_state.get("ui_language", "zh"))
    return lang if lang in _SUPPORTED_LANGS else "zh"


def set_language(lang: str) -> None:
    target = str(lang).lower()
    st.session_state.ui_language = target if target in _SUPPORTED_LANGS else "zh"


def is_english() -> bool:
    return get_language() == "en"


def decision_label(value: bool | None) -> str:
    if value is True:
        return "Accept" if is_english() else "采纳"
    if value is False:
        return "Reject" if is_english() else "拒绝"
    return ""


def decision_to_bool(text: str) -> bool | None:
    normalized = str(text or "").strip().lower()
    if normalized in {"采纳", "accept"}:
        return True
    if normalized in {"拒绝", "reject"}:
        return False
    return None


def t(value: Any) -> Any:
    if not is_english() or not isinstance(value, str):
        return value

    text = value
    if not text:
        return text

    if "<" in text and ">" in text:
        return text

    translated = _TRANSLATIONS.get(text, text)
    for pattern, repl in _PATTERN_TRANSLATIONS:
        if pattern.search(translated):
            translated = pattern.sub(repl, translated)
            break
    return translated


def _wrap_text_first_arg(func):
    def _wrapped(*args, **kwargs):
        if args and isinstance(args[0], str):
            args = (t(args[0]), *args[1:])
        return func(*args, **kwargs)

    return _wrapped


def _wrap_option_widget(func):
    def _wrapped(label, options, *args, **kwargs):
        label = t(label)
        if not is_english() or kwargs.get("format_func") is not None:
            return func(label, options, *args, **kwargs)

        if isinstance(options, (list, tuple)) and all(
            isinstance(item, str) for item in options
        ):
            display_options = [t(item) for item in options]
            display_to_raw = {disp: raw for disp, raw in zip(display_options, options)}
            result = func(label, display_options, *args, **kwargs)
            if isinstance(result, list):
                return [display_to_raw.get(item, item) for item in result]
            return display_to_raw.get(result, result)

        return func(label, options, *args, **kwargs)

    return _wrapped


def patch_streamlit_i18n() -> None:
    global _PATCHED
    if _PATCHED:
        return

    for attr in [
        "title",
        "header",
        "subheader",
        "caption",
        "info",
        "warning",
        "error",
        "success",
        "code",
        "toast",
    ]:
        if hasattr(st, attr):
            setattr(st, attr, _wrap_text_first_arg(getattr(st, attr)))

    if hasattr(st, "markdown"):
        original_markdown = st.markdown

        def _markdown(body, *args, **kwargs):
            return original_markdown(t(body), *args, **kwargs)

        st.markdown = _markdown

    if hasattr(st, "write"):
        original_write = st.write

        def _write(*args, **kwargs):
            converted = [t(arg) if isinstance(arg, str) else arg for arg in args]
            return original_write(*converted, **kwargs)

        st.write = _write

    if hasattr(st, "button"):
        st.button = _wrap_text_first_arg(st.button)

    if hasattr(st, "download_button"):
        st.download_button = _wrap_text_first_arg(st.download_button)

    if hasattr(st, "file_uploader"):
        original_file_uploader = st.file_uploader

        def _file_uploader(label, *args, **kwargs):
            if "help" in kwargs and isinstance(kwargs["help"], str):
                kwargs["help"] = t(kwargs["help"])
            return original_file_uploader(t(label), *args, **kwargs)

        st.file_uploader = _file_uploader

    if hasattr(st, "expander"):
        st.expander = _wrap_text_first_arg(st.expander)

    if hasattr(st, "text_input"):
        original_text_input = st.text_input

        def _text_input(label, *args, **kwargs):
            if "placeholder" in kwargs and isinstance(kwargs["placeholder"], str):
                kwargs["placeholder"] = t(kwargs["placeholder"])
            if "help" in kwargs and isinstance(kwargs["help"], str):
                kwargs["help"] = t(kwargs["help"])
            return original_text_input(t(label), *args, **kwargs)

        st.text_input = _text_input

    if hasattr(st, "text_area"):
        original_text_area = st.text_area

        def _text_area(label, *args, **kwargs):
            if "placeholder" in kwargs and isinstance(kwargs["placeholder"], str):
                kwargs["placeholder"] = t(kwargs["placeholder"])
            if "help" in kwargs and isinstance(kwargs["help"], str):
                kwargs["help"] = t(kwargs["help"])
            return original_text_area(t(label), *args, **kwargs)

        st.text_area = _text_area

    if hasattr(st, "checkbox"):
        st.checkbox = _wrap_text_first_arg(st.checkbox)

    if hasattr(st, "toggle"):
        st.toggle = _wrap_text_first_arg(st.toggle)

    if hasattr(st, "radio"):
        st.radio = _wrap_option_widget(st.radio)

    if hasattr(st, "selectbox"):
        st.selectbox = _wrap_option_widget(st.selectbox)

    if hasattr(st, "multiselect"):
        st.multiselect = _wrap_option_widget(st.multiselect)

    if hasattr(st, "metric"):
        original_metric = st.metric

        def _metric(label, *args, **kwargs):
            return original_metric(t(label), *args, **kwargs)

        st.metric = _metric

    if hasattr(st, "progress"):
        original_progress = st.progress

        def _progress(value, *args, **kwargs):
            if "text" in kwargs and isinstance(kwargs["text"], str):
                kwargs["text"] = t(kwargs["text"])
            return original_progress(value, *args, **kwargs)

        st.progress = _progress

    if hasattr(st, "spinner"):
        original_spinner = st.spinner

        def _spinner(text="", *args, **kwargs):
            return original_spinner(t(text), *args, **kwargs)

        st.spinner = _spinner

    if hasattr(st, "dialog"):
        original_dialog = st.dialog

        def _dialog(title, *args, **kwargs):
            return original_dialog(t(title), *args, **kwargs)

        st.dialog = _dialog

    _PATCHED = True
