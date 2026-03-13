from pathlib import Path
from datetime import datetime
import csv
import html
import io
import json
import re

import streamlit as st
import streamlit.components.v1 as components

from excel_utils import build_records_from_mapping, read_excel_file
from i18n import decision_label, decision_to_bool, is_english, t
from metrics_utils import compute_direct_metrics, compute_manual_metrics
from session_state_utils import (
    apply_loaded_records,
    clear_loaded_data,
    go_next_item,
    go_previous_item,
    record_direct_decision,
    record_multi_output_annotation,
    record_multi_output_manual_annotation,
    record_manual_annotation,
    split_output_values,
    set_import_source,
)

ARCHIVE_DIR = Path(__file__).with_name("archives")


def _ensure_archive_dir() -> Path:
    """确保存档目录存在。"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    return ARCHIVE_DIR


def _list_archive_files() -> list:
    """列出可加载的存档文件（按时间倒序）。"""
    archive_dir = _ensure_archive_dir()
    files = [p for p in archive_dir.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _build_archive_display_options(archive_files: list) -> list:
    """构建存档展示选项，包含保存时间与进度信息。"""
    options = []
    for file_path in archive_files:
        label = file_path.name
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            state = payload.get("state", {}) if isinstance(payload, dict) else {}
            records = state.get("records", []) if isinstance(state, dict) else []
            total = len(records) if isinstance(records, list) else 0
            current = state.get("current_index", 0) if isinstance(state, dict) else 0
            try:
                current = int(current)
            except Exception:
                current = 0
            current = max(0, min(current, total))

            saved_at = payload.get("saved_at", "") if isinstance(payload, dict) else ""
            time_text = str(saved_at).replace("T", " ") if saved_at else t("未知时间")
            label = f"{file_path.name} | {time_text} | {t('进度')} {current}/{total}"
        except Exception:
            label = f"{file_path.name} | {t('解析失败')}"

        options.append({"file_name": file_path.name, "label": label})

    return options


def _build_archive_state_payload() -> dict:
    """构建可持久化的存档状态。"""
    keys_to_save = [
        "records",
        "current_index",
        "eval_mode",
        "direct_decisions",
        "manual_annotations",
        "multi_output_annotations",
        "multi_output_decisions",
        "multi_output_manual_annotations",
        "manual_option_pool",
        "manual_option_pool_by_output",
        "hide_llm_output",
        "use_system_prompt",
        "system_prompt_text",
        "system_prompt_draft",
        "sandbox_system_prompt",
        "browse_rows_override",
        "browse_rows_override_mode",
        "browse_rows_dirty",
        "browse_cell_overrides",
        "browse_undo_stack",
    ]

    state = {}
    for key in keys_to_save:
        state[key] = st.session_state.get(key)

    return {
        "schema_version": 1,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "state": state,
    }


def _save_archive_checkpoint(custom_name: str = "", overwrite: bool = False) -> tuple:
    """保存当前评测进度为存档文件。"""
    records = st.session_state.get("records", [])
    if not records:
        return False, "当前没有可保存的评测数据。"

    archive_dir = _ensure_archive_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    custom_name = str(custom_name or "").strip()

    if custom_name:
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", custom_name)
        safe_name = safe_name.strip(" .")
        if not safe_name:
            return False, "存档文件名无效，请重新输入。"
        if not safe_name.lower().endswith(".json"):
            safe_name = f"{safe_name}.json"
        file_path = archive_dir / safe_name
    else:
        file_path = archive_dir / f"archive_{timestamp}.json"

    if file_path.exists() and not overwrite:
        return "exists", f"存档文件已存在：{file_path.name}"
    payload = _build_archive_state_payload()

    try:
        file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        return "error", f"存档保存失败：{exc}"

    return "ok", f"存档已保存：{file_path.name}"


def _render_save_archive_dialog(key_suffix: str) -> None:
    """渲染保存存档弹窗（支持同名覆盖确认）。"""
    if hasattr(st, "dialog"):

        @st.dialog("保存存档")
        def _save_dialog() -> None:
            st.text_input(
                "存档文件名", placeholder="可选，不填自动生成", key="archive_file_name"
            )

            pending_overwrite = bool(
                st.session_state.get("archive_confirm_overwrite", False)
            )
            pending_name = str(st.session_state.get("archive_pending_name", "")).strip()

            if pending_overwrite:
                st.warning(
                    f"检测到同名存档：{pending_name or '自动生成名称'}，是否覆盖？"
                )
                cover_col, cancel_col = st.columns(2)
                with cover_col:
                    if st.button(
                        "覆盖保存",
                        width="stretch",
                        type="primary",
                        key=f"confirm_overwrite_archive{key_suffix}",
                    ):
                        status, msg = _save_archive_checkpoint(
                            custom_name=pending_name, overwrite=True
                        )
                        if status == "ok":
                            st.success(msg)
                            st.session_state.show_save_archive_dialog = False
                            st.session_state.archive_confirm_overwrite = False
                            st.session_state.archive_pending_name = ""
                            st.rerun()
                        else:
                            st.error(msg)
                with cancel_col:
                    if st.button(
                        "取消覆盖",
                        width="stretch",
                        key=f"cancel_overwrite_archive{key_suffix}",
                    ):
                        st.session_state.archive_confirm_overwrite = False
                        st.session_state.archive_pending_name = ""
                        st.rerun()

            action_col1, action_col2 = st.columns(2)
            with action_col1:
                if st.button(
                    "保存",
                    width="stretch",
                    type="primary",
                    key=f"save_archive_in_dialog{key_suffix}",
                ):
                    archive_name = str(
                        st.session_state.get("archive_file_name", "")
                    ).strip()
                    status, msg = _save_archive_checkpoint(
                        custom_name=archive_name, overwrite=False
                    )
                    if status == "ok":
                        st.success(msg)
                        st.session_state.show_save_archive_dialog = False
                        st.session_state.archive_confirm_overwrite = False
                        st.session_state.archive_pending_name = ""
                        st.rerun()
                    elif status == "exists":
                        st.session_state.archive_confirm_overwrite = True
                        st.session_state.archive_pending_name = archive_name
                        st.rerun()
                    else:
                        st.error(msg)
            with action_col2:
                if st.button(
                    "关闭",
                    width="stretch",
                    key=f"close_save_archive_dialog{key_suffix}",
                ):
                    st.session_state.show_save_archive_dialog = False
                    st.session_state.archive_confirm_overwrite = False
                    st.session_state.archive_pending_name = ""
                    st.rerun()

        _save_dialog()
        return

    st.warning("当前版本不支持弹窗，请升级 Streamlit。")


def _load_archive_checkpoint(file_name: str) -> tuple:
    """从存档文件恢复评测进度。"""
    archive_files = {p.name: p for p in _list_archive_files()}
    target = archive_files.get(file_name)
    if target is None:
        return False, "未找到指定存档文件。"

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"存档读取失败：{exc}"

    state = payload.get("state", {}) if isinstance(payload, dict) else {}
    records = state.get("records", [])
    if not isinstance(records, list) or len(records) == 0:
        return False, "存档无有效 records 数据。"

    for key, value in state.items():
        st.session_state[key] = value

    # 兼容旧存档：若缺少选择项集合，按当前 records 自动重建。
    eval_mode = str(st.session_state.get("eval_mode", ""))
    records = st.session_state.get("records", [])
    if eval_mode in ["manual", "multi_manual"]:
        option_pool = st.session_state.get("manual_option_pool")
        option_pool_by_output = st.session_state.get("manual_option_pool_by_output")

        need_rebuild_pool = not isinstance(option_pool, list)
        need_rebuild_pool_by_output = not isinstance(option_pool_by_output, dict)

        if need_rebuild_pool or need_rebuild_pool_by_output:
            option_pool = []
            option_pool_by_output = {}

        # JSON 反序列化后 dict 键会变成字符串，这里统一转为 int，避免取值 miss。
        normalized_pool_by_output = {}
        if isinstance(option_pool_by_output, dict):
            for key, value in option_pool_by_output.items():
                try:
                    out_idx = int(key)
                except Exception:
                    continue
                if isinstance(value, list):
                    cleaned = []
                    for item in value:
                        text = str(item).strip()
                        if text and text not in cleaned:
                            cleaned.append(text)
                    normalized_pool_by_output[out_idx] = cleaned
        option_pool_by_output = normalized_pool_by_output

        if eval_mode == "multi_manual":
            has_any_output_pool = any(
                isinstance(v, list) and len(v) > 0
                for v in option_pool_by_output.values()
            )
            if len(option_pool) == 0 or not has_any_output_pool:
                for item in records:
                    output_list = item.get("output_list")
                    if not isinstance(output_list, list) or len(output_list) == 0:
                        output_list = split_output_values(item.get("output", ""))
                    for out_idx, output_text in enumerate(output_list, start=1):
                        text = str(output_text).strip()
                        if not text:
                            continue
                        if text not in option_pool:
                            option_pool.append(text)
                        if out_idx not in option_pool_by_output:
                            option_pool_by_output[out_idx] = []
                        if text not in option_pool_by_output[out_idx]:
                            option_pool_by_output[out_idx].append(text)
        else:
            if len(option_pool) == 0:
                for item in records:
                    output_text = str(item.get("output", "")).strip()
                    if output_text and output_text not in option_pool:
                        option_pool.append(output_text)

        st.session_state.manual_option_pool = option_pool
        st.session_state.manual_option_pool_by_output = option_pool_by_output

    total = len(st.session_state.get("records", []))
    current_idx = int(st.session_state.get("current_index", 0) or 0)
    st.session_state.current_index = max(0, min(current_idx, total))

    # 恢复后清理入口态与临时导入态。
    st.session_state.pending_records = []
    st.session_state.import_dataframe = None
    st.session_state.import_source_name = ""
    st.session_state.show_mode_selector = False
    st.session_state.show_clear_confirm = False
    st.session_state.show_live_stats = False
    st.session_state.show_result_browser = False
    st.session_state.active_top_dialog = ""
    st.session_state.project_entry_state = "loaded_project"
    st.session_state.show_archive_loader = False
    st.session_state.archive_delete_target = ""

    return True, f"已加载存档：{target.name}"


def _delete_archive_checkpoint(file_name: str) -> tuple:
    """删除指定存档文件。"""
    archive_files = {p.name: p for p in _list_archive_files()}
    target = archive_files.get(file_name)
    if target is None:
        return False, "未找到指定存档文件。"

    try:
        target.unlink()
    except Exception as exc:
        return False, f"删除失败：{exc}"

    return True, f"已删除存档：{file_name}"


def _build_export_rows():
    """构建导出的逐条评测结果。"""
    records = st.session_state.records
    eval_mode = st.session_state.eval_mode
    rows = []

    if eval_mode == "direct":
        decisions = st.session_state.direct_decisions
        for idx, item in enumerate(records):
            decision = decisions[idx] if idx < len(decisions) else None
            rows.append(
                {
                    "id": item.get("id", ""),
                    "prompt": item.get("prompt", ""),
                    "system_prompt": item.get("system_prompt", ""),
                    "user_prompt": item.get("user_prompt", item.get("prompt", "")),
                    "llm_output": item.get("output", ""),
                    "decision": decision_label(decision),
                    "decision_bool": (
                        "1" if decision is True else "0" if decision is False else ""
                    ),
                }
            )
        return rows

    if eval_mode == "multi":
        annotations = st.session_state.multi_output_annotations
        for idx, item in enumerate(records):
            annotation = annotations[idx] if idx < len(annotations) else {}
            outputs = annotation.get(
                "outputs",
                item.get("output_list", split_output_values(item.get("output", ""))),
            )
            output_labels = item.get("output_labels", [])
            decisions = annotation.get("decisions", [])
            for out_idx, output_text in enumerate(outputs, start=1):
                decision = (
                    decisions[out_idx - 1] if out_idx - 1 < len(decisions) else None
                )
                output_field = (
                    str(output_labels[out_idx - 1]).strip()
                    if out_idx - 1 < len(output_labels)
                    and str(output_labels[out_idx - 1]).strip()
                    else f"output_{out_idx}"
                )
                rows.append(
                    {
                        "id": item.get("id", ""),
                        "prompt": item.get("prompt", ""),
                        "system_prompt": item.get("system_prompt", ""),
                        "user_prompt": item.get("user_prompt", item.get("prompt", "")),
                        "output_index": out_idx,
                        "output_field": output_field,
                        "llm_output": output_text,
                        "decision": decision_label(decision),
                        "decision_bool": (
                            "1"
                            if decision is True
                            else "0" if decision is False else ""
                        ),
                    }
                )
        return rows

    if eval_mode == "multi_manual":
        annotations = st.session_state.multi_output_manual_annotations
        for idx, item in enumerate(records):
            annotation = annotations[idx] if idx < len(annotations) else {}
            outputs = annotation.get(
                "outputs",
                item.get("output_list", split_output_values(item.get("output", ""))),
            )
            output_labels = item.get("output_labels", [])
            manual_results = annotation.get("manual_results", [])
            for out_idx, output_text in enumerate(outputs, start=1):
                manual_result = (
                    manual_results[out_idx - 1]
                    if out_idx - 1 < len(manual_results)
                    else ""
                )
                output_field = (
                    str(output_labels[out_idx - 1]).strip()
                    if out_idx - 1 < len(output_labels)
                    and str(output_labels[out_idx - 1]).strip()
                    else f"output_{out_idx}"
                )
                rows.append(
                    {
                        "id": item.get("id", ""),
                        "prompt": item.get("prompt", ""),
                        "system_prompt": item.get("system_prompt", ""),
                        "user_prompt": item.get("user_prompt", item.get("prompt", "")),
                        "output_index": out_idx,
                        "output_field": output_field,
                        "llm_output": output_text,
                        "manual_result": manual_result,
                        "is_match": (
                            "1"
                            if str(manual_result).strip() == str(output_text).strip()
                            else "0"
                        ),
                    }
                )
        return rows

    annotations = st.session_state.manual_annotations
    for idx, item in enumerate(records):
        annotation = annotations[idx] if idx < len(annotations) else {}
        manual_result = str(annotation.get("manual_result", ""))
        llm_output = str(annotation.get("llm_output", item.get("output", "")))
        rows.append(
            {
                "id": item.get("id", ""),
                "prompt": item.get("prompt", ""),
                "system_prompt": item.get("system_prompt", ""),
                "user_prompt": item.get("user_prompt", item.get("prompt", "")),
                "llm_output": llm_output,
                "manual_result": manual_result,
                "is_match": "1" if manual_result.strip() == llm_output.strip() else "0",
            }
        )
    return rows


def _has_multi_outputs(records) -> bool:
    """判断记录中是否存在多输出样本。"""
    for item in records or []:
        output_list = item.get("output_list")
        if isinstance(output_list, list) and len(output_list) >= 2:
            return True
        if len(split_output_values(item.get("output", ""))) >= 2:
            return True
    return False


def _flatten_multi_manual_annotations():
    """将多输出人工输入标注展开为通用 manual 指标结构。"""
    flat = []
    for item in st.session_state.multi_output_manual_annotations:
        outputs = item.get("outputs", [])
        manual_results = item.get("manual_results", [])
        for idx, llm_output in enumerate(outputs):
            manual_result = manual_results[idx] if idx < len(manual_results) else ""
            flat.append({"llm_output": llm_output, "manual_result": manual_result})
    return flat


def _collect_multi_direct_metrics_by_output():
    """汇总多输出直接判断模式下各 output 的统计。"""
    decisions_by_output = {}
    for item in st.session_state.multi_output_annotations:
        decisions = item.get("decisions", [])
        for out_idx, decision in enumerate(decisions, start=1):
            if out_idx not in decisions_by_output:
                decisions_by_output[out_idx] = []
            decisions_by_output[out_idx].append(bool(decision))

    output_indices = sorted(decisions_by_output.keys())
    metrics_by_output = {
        out_idx: compute_direct_metrics(decisions_by_output[out_idx])
        for out_idx in output_indices
    }
    return metrics_by_output


def _collect_multi_manual_metrics_by_output():
    """汇总多输出人工输入模式下各 output 的统计。"""
    annotations_by_output = {}
    for item in st.session_state.multi_output_manual_annotations:
        outputs = item.get("outputs", [])
        manual_results = item.get("manual_results", [])
        for out_idx, llm_output in enumerate(outputs, start=1):
            manual_result = (
                manual_results[out_idx - 1] if out_idx - 1 < len(manual_results) else ""
            )
            if out_idx not in annotations_by_output:
                annotations_by_output[out_idx] = []
            annotations_by_output[out_idx].append(
                {
                    "llm_output": str(llm_output),
                    "manual_result": str(manual_result),
                }
            )

    output_indices = sorted(annotations_by_output.keys())
    metrics_by_output = {
        out_idx: compute_manual_metrics(annotations_by_output[out_idx])
        for out_idx in output_indices
    }
    return metrics_by_output


def _render_output_metrics_table(
    metrics_by_output: dict, manual_mode: bool, title: str
) -> None:
    """用紧凑表格渲染各 output 指标，减少垂直空间占用。"""
    if not metrics_by_output:
        return

    st.markdown(f"#### {title}")
    rows = []
    for out_idx in sorted(metrics_by_output.keys()):
        metrics = metrics_by_output[out_idx]
        row = {
            t("Output"): out_idx,
            t("已标注数"): metrics.get("total", 0),
            "Accuracy": f"{metrics.get('accuracy', 0.0) * 100:.2f}%",
        }
        if manual_mode:
            row["Precision"] = f"{metrics.get('precision', 0.0) * 100:.2f}%"
            row["Recall"] = f"{metrics.get('recall', 0.0) * 100:.2f}%"
            row["F1"] = f"{metrics.get('f1', 0.0) * 100:.2f}%"
        rows.append(row)

    table_height = max(56, min(220, 34 + len(rows) * 30))
    st.dataframe(rows, hide_index=True, width="stretch", height=table_height)


def _render_compact_metric_style() -> None:
    """缩小指标数字，避免指标区显示不完整。"""
    st.markdown(
        """
        <style>
        div[data-testid="metric-container"] {
            padding: 0.12rem 0.22rem !important;
            min-height: 0 !important;
            margin-bottom: 0.06rem !important;
            border-radius: 0.35rem !important;
        }
        div[data-testid="metric-container"] label[data-testid="stMetricLabel"] {
            font-size: 0.66rem !important;
            margin-bottom: 0.04rem !important;
        }
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
            font-size: 0.82rem !important;
            line-height: 1 !important;
        }
        h3, h4 {
            margin-top: 0.26rem !important;
            margin-bottom: 0.12rem !important;
        }
        p {
            margin-bottom: 0.08rem !important;
        }
        div[data-testid="stAlert"] {
            padding-top: 0.3rem !important;
            padding-bottom: 0.3rem !important;
            margin-bottom: 0.25rem !important;
        }
        .compact-card {
            border-radius: 0.45rem;
            border: 1px solid #d5dae3;
            padding: 0.35rem 0.5rem;
            margin-bottom: 0.28rem;
            color: #111111;
        }
        .compact-card .compact-title {
            font-size: 0.78rem;
            font-weight: 600;
            color: #111111;
            margin-bottom: 0.2rem;
        }
        .compact-card .compact-content {
            font-size: 0.95rem;
            line-height: 1.6;
            color: #111111;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .compact-card.prompt-card {
            background: #eef5ff;
            border-color: #c9d9f2;
        }
        .compact-card.candidate-card {
            background: #fff4e6;
            border-color: #f2d3a5;
        }
        .annotation-hint {
            color: #1f2328;
            font-size: 0.78rem;
            line-height: 1.35;
            margin: 0.15rem 0 0.45rem 0;
        }
        .sticky-prompt-panel {
            position: sticky;
            top: 0.8rem;
        }
        @media (max-width: 900px) {
            .sticky-prompt-panel {
                position: static;
                top: auto;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_refresh_confirm_guard(enabled: bool) -> None:
    """在浏览器刷新/离开页面前提示确认，避免误丢标注数据。"""
    guard_enabled = "true" if enabled else "false"
    components.html(
        f"""
        <script>
        (function () {{
            const enableGuard = {guard_enabled};
            if (!enableGuard) {{
                window.onbeforeunload = null;
                return;
            }}

            window.onbeforeunload = function (event) {{
                const message = "{('All annotation data will be lost after refresh. Continue?' if is_english() else '刷新后所有标注数据会丢失，是否继续刷新？')}";
                event.preventDefault();
                event.returnValue = message;
                return message;
            }};
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _render_compact_text(
    title: str, text: str, key: str, variant: str = "candidate"
) -> None:
    """用紧凑彩色卡片展示文本内容。"""
    safe_title = html.escape(str(title or ""))
    safe_text = html.escape(str(text or ""))
    card_class = "prompt-card" if variant == "prompt" else "candidate-card"
    st.markdown(
        f"""
        <div id="{html.escape(str(key))}" class="compact-card {card_class}">
            <div class="compact-title">{safe_title}</div>
            <div class="compact-content">{safe_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _build_excel_rows_wide():
    """构建 Excel 专用导出行：多输出模式按列展开，不按行展开。"""
    records = st.session_state.records
    mode = st.session_state.eval_mode

    if mode not in ["multi", "multi_manual"]:
        return _build_export_rows()

    rows = []
    if mode == "multi":
        annotations = st.session_state.multi_output_annotations
        for idx, item in enumerate(records):
            annotation = annotations[idx] if idx < len(annotations) else {}
            outputs = annotation.get(
                "outputs",
                item.get("output_list", split_output_values(item.get("output", ""))),
            )
            output_labels = item.get("output_labels", [])
            decisions = annotation.get("decisions", [])

            row = {
                "id": item.get("id", ""),
                "prompt": item.get("prompt", ""),
                "system_prompt": item.get("system_prompt", ""),
                "user_prompt": item.get("user_prompt", item.get("prompt", "")),
            }
            for out_idx, output_text in enumerate(outputs, start=1):
                output_field = (
                    str(output_labels[out_idx - 1]).strip()
                    if out_idx - 1 < len(output_labels)
                    and str(output_labels[out_idx - 1]).strip()
                    else f"output_{out_idx}"
                )
                decision = (
                    decisions[out_idx - 1] if out_idx - 1 < len(decisions) else None
                )
                row[f"output_field_{out_idx}"] = output_field
                row[f"llm_output_{out_idx}"] = output_text
                row[f"decision_{out_idx}"] = decision_label(decision)
                row[f"decision_bool_{out_idx}"] = (
                    "1" if decision is True else "0" if decision is False else ""
                )
            rows.append(row)
        return rows

    annotations = st.session_state.multi_output_manual_annotations
    for idx, item in enumerate(records):
        annotation = annotations[idx] if idx < len(annotations) else {}
        outputs = annotation.get(
            "outputs",
            item.get("output_list", split_output_values(item.get("output", ""))),
        )
        output_labels = item.get("output_labels", [])
        manual_results = annotation.get("manual_results", [])

        row = {
            "id": item.get("id", ""),
            "prompt": item.get("prompt", ""),
            "system_prompt": item.get("system_prompt", ""),
            "user_prompt": item.get("user_prompt", item.get("prompt", "")),
        }
        for out_idx, output_text in enumerate(outputs, start=1):
            output_field = (
                str(output_labels[out_idx - 1]).strip()
                if out_idx - 1 < len(output_labels)
                and str(output_labels[out_idx - 1]).strip()
                else f"output_{out_idx}"
            )
            manual_result = (
                manual_results[out_idx - 1] if out_idx - 1 < len(manual_results) else ""
            )
            row[f"output_field_{out_idx}"] = output_field
            row[f"llm_output_{out_idx}"] = output_text
            row[f"manual_result_{out_idx}"] = manual_result
            row[f"is_match_{out_idx}"] = (
                "1" if str(manual_result).strip() == str(output_text).strip() else "0"
            )
        rows.append(row)
    return rows


def _get_effective_export_rows() -> list:
    """获取用于导出的结果行，基于最新结果叠加浏览编辑。"""

    def _is_derived_judgement_col(col_name: str) -> bool:
        name = str(col_name)
        return (
            name in ["decision_bool", "is_match"]
            or name.startswith("decision_bool_")
            or name.startswith("is_match_")
        )

    def _strip_derived_judgement_cols(rows: list) -> list:
        stripped = []
        for row in rows:
            clean_row = {}
            for key, value in dict(row).items():
                if not _is_derived_judgement_col(key):
                    clean_row[key] = value
            stripped.append(clean_row)
        return stripped

    def _with_auto_derived_judgement_cols(rows: list) -> list:
        mode = st.session_state.eval_mode
        rebuilt_rows = []
        index_pattern = re.compile(r"(\d+)$")

        for row in rows:
            current = dict(row)
            if mode in ["direct", "multi"]:
                if mode == "direct":
                    decision_text = str(current.get("decision", "")).strip()
                    decision_bool = decision_to_bool(decision_text)
                    if decision_bool is None:
                        current["decision_bool"] = ""
                    else:
                        current["decision_bool"] = "1" if decision_bool else "0"
                else:
                    out_indices = set()
                    for key in current.keys():
                        if str(key).startswith("decision_") and not str(key).startswith(
                            "decision_bool_"
                        ):
                            match = index_pattern.search(str(key))
                            if match:
                                out_indices.add(int(match.group(1)))
                    for out_idx in out_indices:
                        decision_text = str(
                            current.get(f"decision_{out_idx}", "")
                        ).strip()
                        decision_bool = decision_to_bool(decision_text)
                        if decision_bool is None:
                            current[f"decision_bool_{out_idx}"] = ""
                        else:
                            current[f"decision_bool_{out_idx}"] = (
                                "1" if decision_bool else "0"
                            )

            if mode in ["manual", "multi_manual"]:
                if mode == "manual":
                    manual_result = str(current.get("manual_result", "")).strip()
                    llm_output = str(current.get("llm_output", "")).strip()
                    current["is_match"] = (
                        "1"
                        if manual_result and manual_result == llm_output
                        else "0" if manual_result else ""
                    )
                else:
                    out_indices = set()
                    for key in current.keys():
                        if str(key).startswith("manual_result_") or str(key).startswith(
                            "llm_output_"
                        ):
                            match = index_pattern.search(str(key))
                            if match:
                                out_indices.add(int(match.group(1)))
                    for out_idx in out_indices:
                        manual_result = str(
                            current.get(f"manual_result_{out_idx}", "")
                        ).strip()
                        llm_output = str(
                            current.get(f"llm_output_{out_idx}", "")
                        ).strip()
                        current[f"is_match_{out_idx}"] = (
                            "1"
                            if manual_result and manual_result == llm_output
                            else "0" if manual_result else ""
                        )

            rebuilt_rows.append(current)

        return rebuilt_rows

    def _apply_browse_cell_overrides(rows: list) -> list:
        override_mode = st.session_state.get("browse_rows_override_mode", "")
        override_dirty = bool(st.session_state.get("browse_rows_dirty", False))
        cell_overrides = st.session_state.get("browse_cell_overrides", {})
        if not (
            override_dirty
            and override_mode == st.session_state.eval_mode
            and isinstance(cell_overrides, dict)
            and cell_overrides
        ):
            return rows

        merged_rows = []
        for row_idx, row in enumerate(rows):
            merged = dict(row)
            row_overrides = cell_overrides.get(str(row_idx), {})
            if isinstance(row_overrides, dict):
                for col_name, value in row_overrides.items():
                    merged[col_name] = value
            merged_rows.append(merged)
        return merged_rows

    base_rows = _build_excel_rows_wide()
    merged_rows = _apply_browse_cell_overrides(base_rows)
    return _with_auto_derived_judgement_cols(_strip_derived_judgement_cols(merged_rows))


def _has_active_browse_overrides() -> bool:
    """判断当前模式是否启用了浏览保存覆盖。"""
    return bool(
        st.session_state.get("browse_rows_dirty", False)
        and st.session_state.get("browse_rows_override_mode", "")
        == st.session_state.eval_mode
    )


def _collect_display_metrics_for_mode():
    """收集用于页面展示的指标；有浏览覆盖时按覆盖后的结果计算。"""
    mode = st.session_state.eval_mode
    if not _has_active_browse_overrides():
        if mode == "direct":
            return {
                "metrics": compute_direct_metrics(st.session_state.direct_decisions),
                "completed_samples": None,
                "labeled_outputs": None,
                "metrics_by_output": {},
            }
        if mode == "multi":
            return {
                "metrics": compute_direct_metrics(
                    st.session_state.multi_output_decisions
                ),
                "completed_samples": len(st.session_state.multi_output_annotations),
                "labeled_outputs": compute_direct_metrics(
                    st.session_state.multi_output_decisions
                ).get("total", 0),
                "metrics_by_output": _collect_multi_direct_metrics_by_output(),
            }
        if mode == "multi_manual":
            metrics = compute_manual_metrics(_flatten_multi_manual_annotations())
            return {
                "metrics": metrics,
                "completed_samples": len(
                    st.session_state.multi_output_manual_annotations
                ),
                "labeled_outputs": metrics.get("total", 0),
                "metrics_by_output": _collect_multi_manual_metrics_by_output(),
            }
        return {
            "metrics": compute_manual_metrics(st.session_state.manual_annotations),
            "completed_samples": None,
            "labeled_outputs": None,
            "metrics_by_output": {},
        }

    rows = _get_effective_export_rows()
    index_pattern = re.compile(r"(\d+)$")

    if mode == "direct":
        decisions = []
        for row in rows:
            raw_bool = str(row.get("decision_bool", "")).strip()
            raw_text = str(row.get("decision", "")).strip()
            if raw_bool in ["1", "0"]:
                decisions.append(raw_bool == "1")
            else:
                parsed = decision_to_bool(raw_text)
                if parsed is not None:
                    decisions.append(parsed)
        return {
            "metrics": compute_direct_metrics(decisions),
            "completed_samples": None,
            "labeled_outputs": None,
            "metrics_by_output": {},
        }

    if mode == "manual":
        annotations = []
        for row in rows:
            manual_result = str(row.get("manual_result", "")).strip()
            if not manual_result:
                continue
            annotations.append(
                {
                    "llm_output": str(row.get("llm_output", "")),
                    "manual_result": manual_result,
                }
            )
        return {
            "metrics": compute_manual_metrics(annotations),
            "completed_samples": None,
            "labeled_outputs": None,
            "metrics_by_output": {},
        }

    if mode == "multi":
        decisions_all = []
        decisions_by_output = {}
        completed_samples = 0

        for row in rows:
            out_indices = set()
            for key in row.keys():
                if str(key).startswith("decision_bool_") or str(key).startswith(
                    "decision_"
                ):
                    match = index_pattern.search(str(key))
                    if match:
                        out_indices.add(int(match.group(1)))

            present_count = 0
            for out_idx in sorted(out_indices):
                raw_bool = str(row.get(f"decision_bool_{out_idx}", "")).strip()
                raw_text = str(row.get(f"decision_{out_idx}", "")).strip()
                decision = None
                if raw_bool in ["1", "0"]:
                    decision = raw_bool == "1"
                else:
                    decision = decision_to_bool(raw_text)

                if decision is None:
                    continue

                present_count += 1
                decisions_all.append(decision)
                if out_idx not in decisions_by_output:
                    decisions_by_output[out_idx] = []
                decisions_by_output[out_idx].append(decision)

            if out_indices and present_count == len(out_indices):
                completed_samples += 1

        metrics_by_output = {
            out_idx: compute_direct_metrics(values)
            for out_idx, values in sorted(
                decisions_by_output.items(), key=lambda kv: kv[0]
            )
        }
        metrics = compute_direct_metrics(decisions_all)
        return {
            "metrics": metrics,
            "completed_samples": completed_samples,
            "labeled_outputs": metrics.get("total", 0),
            "metrics_by_output": metrics_by_output,
        }

    annotations_all = []
    annotations_by_output = {}
    completed_samples = 0

    for row in rows:
        out_indices = set()
        for key in row.keys():
            if str(key).startswith("llm_output_") or str(key).startswith(
                "manual_result_"
            ):
                match = index_pattern.search(str(key))
                if match:
                    out_indices.add(int(match.group(1)))

        present_count = 0
        for out_idx in sorted(out_indices):
            llm_output = str(row.get(f"llm_output_{out_idx}", "")).strip()
            manual_result = str(row.get(f"manual_result_{out_idx}", "")).strip()
            if not manual_result:
                continue

            present_count += 1
            item = {"llm_output": llm_output, "manual_result": manual_result}
            annotations_all.append(item)
            if out_idx not in annotations_by_output:
                annotations_by_output[out_idx] = []
            annotations_by_output[out_idx].append(item)

        if out_indices and present_count == len(out_indices):
            completed_samples += 1

    metrics = compute_manual_metrics(annotations_all)
    metrics_by_output = {
        out_idx: compute_manual_metrics(values)
        for out_idx, values in sorted(
            annotations_by_output.items(), key=lambda kv: kv[0]
        )
    }
    return {
        "metrics": metrics,
        "completed_samples": completed_samples,
        "labeled_outputs": metrics.get("total", 0),
        "metrics_by_output": metrics_by_output,
    }


def _normalize_editor_rows(editor_data) -> list:
    """将 data_editor 返回值统一转换为 list[dict]。"""
    if hasattr(editor_data, "to_dict"):
        return editor_data.to_dict(orient="records")
    if isinstance(editor_data, list):
        normalized = []
        for item in editor_data:
            normalized.append(dict(item) if isinstance(item, dict) else {"value": item})
        return normalized
    if isinstance(editor_data, dict):
        return [editor_data]
    return []


def _render_result_browser_table() -> None:
    """渲染结果浏览与可编辑表格。"""
    base_rows = _build_excel_rows_wide()

    def _is_derived_judgement_col(col_name: str) -> bool:
        name = str(col_name)
        return (
            name in ["decision_bool", "is_match"]
            or name.startswith("decision_bool_")
            or name.startswith("is_match_")
        )

    def _strip_derived_judgement_cols(rows: list) -> list:
        stripped = []
        for row in rows:
            clean_row = {}
            for key, value in dict(row).items():
                if not _is_derived_judgement_col(key):
                    clean_row[key] = value
            stripped.append(clean_row)
        return stripped

    override_mode = st.session_state.get("browse_rows_override_mode", "")
    if override_mode and override_mode != st.session_state.eval_mode:
        st.session_state.browse_rows_override_mode = st.session_state.eval_mode
        st.session_state.browse_rows_dirty = False
        st.session_state.browse_cell_overrides = {}
        st.session_state.browse_undo_stack = []

    editor_source = _strip_derived_judgement_cols(_get_effective_export_rows())
    base_editor_rows = _strip_derived_judgement_cols(base_rows)

    st.markdown("#### 结果浏览（可编辑）")
    st.caption("表格修改将自动保存；判断列由后台自动生成。")
    edited_data = st.data_editor(
        editor_source,
        width="stretch",
        num_rows="fixed",
        key=f"result_browser_editor_{st.session_state.eval_mode}",
    )

    edited_rows = _normalize_editor_rows(edited_data)
    new_cell_overrides = {}
    for row_idx in range(min(len(base_editor_rows), len(edited_rows))):
        base_row = (
            base_editor_rows[row_idx]
            if isinstance(base_editor_rows[row_idx], dict)
            else {}
        )
        edited_row = (
            edited_rows[row_idx] if isinstance(edited_rows[row_idx], dict) else {}
        )
        changed_cells = {}
        for col_name, edited_value in edited_row.items():
            if base_row.get(col_name) != edited_value:
                changed_cells[col_name] = edited_value
        if changed_cells:
            new_cell_overrides[str(row_idx)] = changed_cells

    current_overrides = st.session_state.get("browse_cell_overrides", {})
    if new_cell_overrides != current_overrides:
        undo_stack = st.session_state.get("browse_undo_stack", [])
        undo_stack.append(
            current_overrides if isinstance(current_overrides, dict) else {}
        )
        st.session_state.browse_undo_stack = undo_stack[-30:]
        st.session_state.browse_rows_override = edited_rows
        st.session_state.browse_rows_override_mode = st.session_state.eval_mode
        st.session_state.browse_cell_overrides = new_cell_overrides
        st.session_state.browse_rows_dirty = bool(new_cell_overrides)

    undo_stack = st.session_state.get("browse_undo_stack", [])
    undo_spacer_col, undo_button_col = st.columns([5, 1])
    with undo_button_col:
        if st.button(
            "返回上一个操作",
            width="stretch",
            key=f"undo_browser_edit_{st.session_state.eval_mode}",
            disabled=(len(undo_stack) == 0),
        ):
            previous_overrides = undo_stack.pop() if undo_stack else {}
            st.session_state.browse_undo_stack = undo_stack
            st.session_state.browse_rows_override_mode = st.session_state.eval_mode
            st.session_state.browse_cell_overrides = (
                previous_overrides if isinstance(previous_overrides, dict) else {}
            )
            st.session_state.browse_rows_dirty = bool(
                st.session_state.browse_cell_overrides
            )
            st.session_state.browse_rows_override = _strip_derived_judgement_cols(
                _get_effective_export_rows()
            )
            st.rerun()


def _collect_current_metrics_summary() -> dict:
    """按当前模式汇总指标，用于进行中导出。优先与当前展示/浏览覆盖保持一致。"""
    display = _collect_display_metrics_for_mode()
    metrics = dict(display.get("metrics", {}))

    metrics_by_output = display.get("metrics_by_output", {})
    if metrics_by_output:
        metrics["metrics_by_output"] = metrics_by_output

    if display.get("completed_samples") is not None:
        metrics["completed_samples"] = display.get("completed_samples")
    if display.get("labeled_outputs") is not None:
        metrics["labeled_outputs"] = display.get("labeled_outputs")

    return metrics


def _render_top_export_current_button(
    total_count: int, current_index: int, key_suffix: str = ""
) -> None:
    """在页面右上方渲染当前结果导出按钮。"""
    mode = st.session_state.eval_mode
    metrics = _collect_current_metrics_summary()
    rows = _get_effective_export_rows()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    export_payload = {
        "mode": mode,
        "progress": {
            "current_index": min(current_index, total_count),
            "total": total_count,
            "completed": bool(total_count and current_index >= total_count),
        },
        "metrics": metrics,
        "results": rows,
    }
    excel_content = None
    try:
        import pandas as pd

        excel_buffer = io.BytesIO()
        results_df = pd.DataFrame(rows)
        metrics_df = pd.DataFrame([metrics])
        progress_df = pd.DataFrame([export_payload["progress"]])

        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            results_df.to_excel(writer, sheet_name="results", index=False)
            metrics_df.to_excel(writer, sheet_name="metrics", index=False)
            progress_df.to_excel(writer, sheet_name="progress", index=False)

        excel_content = excel_buffer.getvalue()
    except Exception:
        excel_content = None

    if excel_content is None:
        st.button(
            "导出当前结果",
            width="stretch",
            disabled=True,
            key=f"top_export_current_button_disabled{key_suffix}",
        )
    else:
        st.download_button(
            "导出当前结果",
            data=excel_content,
            file_name=f"evaluation_{mode}_current_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key=f"top_export_current_button{key_suffix}",
        )


def _render_top_action_bar(
    total_count: int, current_index: int, is_completed: bool, key_suffix: str
) -> None:
    """渲染紧凑顶部操作栏与居中进度条。"""
    with st.container(border=True):
        prev_col, stats_col, browse_col, save_col, clear_col, export_col = st.columns(
            6, gap="small"
        )

        with prev_col:
            if st.button(
                "返回上一条",
                key=f"go_prev_top{key_suffix}",
                use_container_width=True,
                disabled=(not is_completed and current_index <= 0),
            ):
                if go_previous_item():
                    st.session_state.active_top_dialog = ""
                    st.session_state.show_save_archive_dialog = False
                    st.session_state.show_live_stats = False
                    st.session_state.show_result_browser = False
                    st.rerun()

        with stats_col:
            if st.button(
                "统计",
                key=f"open_stats_top{key_suffix}",
                use_container_width=True,
            ):
                st.session_state.show_live_stats = True
                st.session_state.show_result_browser = False
                st.session_state.active_top_dialog = "stats"
                st.session_state.show_save_archive_dialog = False

        with browse_col:
            if st.button(
                "浏览",
                key=f"open_browse_top{key_suffix}",
                use_container_width=True,
            ):
                st.session_state.show_result_browser = True
                st.session_state.show_live_stats = False
                st.session_state.active_top_dialog = "browse"
                st.session_state.show_save_archive_dialog = False

        with save_col:
            if st.button(
                "保存存档",
                key=f"save_archive_top{key_suffix}",
                use_container_width=True,
            ):
                st.session_state.show_save_archive_dialog = True
                st.session_state.active_top_dialog = ""
                st.session_state.show_live_stats = False
                st.session_state.show_result_browser = False

        with clear_col:
            if st.button(
                "清空文件",
                key=f"clear_file_top{key_suffix}",
                use_container_width=True,
            ):
                st.session_state.show_clear_confirm = True
                st.session_state.active_top_dialog = ""
                st.session_state.show_save_archive_dialog = False

        with export_col:
            _render_top_export_current_button(
                total_count=total_count,
                current_index=current_index,
                key_suffix=key_suffix,
            )

        progress_current = total_count if is_completed else min(current_index + 1, total_count)
        progress_ratio = (progress_current / total_count) if total_count else 0.0
        _, progress_center_col, _ = st.columns([1, 3, 1])
        with progress_center_col:
            st.markdown(
                f"<div style='text-align:center;font-weight:600;'>当前第 {progress_current} 条 / 共 {total_count} 条</div>",
                unsafe_allow_html=True,
            )
            try:
                st.progress(progress_ratio, text=f"进度 {progress_current}/{total_count}")
            except TypeError:
                st.progress(progress_ratio)


def _render_mode_selector() -> None:
    """在正式载入数据前，选择评测模式。"""
    if hasattr(st, "dialog"):

        @st.dialog("选择评测模式")
        def _mode_dialog() -> None:
            is_multi_dataset = _has_multi_outputs(st.session_state.pending_records)
            selected_mode = st.radio(
                "请选择评测模式",
                options=["直接判断LLM结果", "人工输入结果"],
                key="dialog_eval_mode",
            )
            if is_multi_dataset:
                st.caption("检测到多输出数据：将对每个 output 分别判断。")

            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                if st.button(
                    "确认进入评测",
                    type="primary",
                    width="stretch",
                    key="confirm_eval_mode",
                ):
                    if is_multi_dataset:
                        target_mode = (
                            "multi"
                            if selected_mode == "直接判断LLM结果"
                            else "multi_manual"
                        )
                    else:
                        target_mode = "manual"
                        if selected_mode == "直接判断LLM结果":
                            target_mode = "direct"
                    mode_mapping = {
                        "直接判断LLM结果": target_mode,
                        "人工输入结果": "manual",
                    }
                    if is_multi_dataset:
                        mode_mapping["人工输入结果"] = "multi_manual"
                    success = apply_loaded_records(
                        eval_mode=mode_mapping[selected_mode]
                    )
                    if success:
                        st.rerun()
            with cancel_col:
                if st.button("取消", width="stretch", key="cancel_eval_mode"):
                    st.session_state.pending_records = []
                    st.session_state.show_mode_selector = False
                    st.rerun()

        _mode_dialog()
        return

    st.warning("请选择评测模式后再进入评测。")
    is_multi_dataset = _has_multi_outputs(st.session_state.pending_records)
    selected_mode = st.radio(
        "请选择评测模式",
        options=["直接判断LLM结果", "人工输入结果"],
        key="fallback_eval_mode",
    )
    if is_multi_dataset:
        st.caption(
            "检测到多输出数据：将对每个 output 分别判断（各选各的），不使用集合总判断。"
        )
    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button(
            "确认进入评测",
            type="primary",
            width="stretch",
            key="fallback_confirm_eval_mode",
        ):
            if is_multi_dataset:
                target_mode = (
                    "multi" if selected_mode == "直接判断LLM结果" else "multi_manual"
                )
            else:
                target_mode = "manual"
                if selected_mode == "直接判断LLM结果":
                    target_mode = "direct"
            mode_mapping = {
                "直接判断LLM结果": target_mode,
                "人工输入结果": "manual",
            }
            if is_multi_dataset:
                mode_mapping["人工输入结果"] = "multi_manual"
            success = apply_loaded_records(eval_mode=mode_mapping[selected_mode])
            if success:
                st.rerun()
    with cancel_col:
        if st.button("取消", width="stretch", key="fallback_cancel_eval_mode"):
            st.session_state.pending_records = []
            st.session_state.show_mode_selector = False
            st.rerun()


def _render_clear_confirm() -> None:
    """渲染清空文件确认框。"""
    if hasattr(st, "dialog"):

        @st.dialog("是否清空文件")
        def _clear_dialog() -> None:
            st.write("清空后将回到初始页面，当前已加载的数据和评测进度不会保留。")
            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                if st.button("是", width="stretch", key="confirm_clear_records"):
                    clear_loaded_data()
                    st.rerun()
            with cancel_col:
                if st.button("否", width="stretch", key="cancel_clear_records"):
                    st.session_state.show_clear_confirm = False
                    st.rerun()

        _clear_dialog()
        return

    st.warning("是否清空文件？清空后将回到初始页面，当前评测进度不会保留。")
    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button("是", width="stretch", key="fallback_confirm_clear_records"):
            clear_loaded_data()
            st.rerun()
    with cancel_col:
        if st.button("否", width="stretch", key="fallback_cancel_clear_records"):
            st.session_state.show_clear_confirm = False
            st.rerun()


def _render_active_top_dialog(is_completed: bool, key_suffix: str) -> None:
    """统一渲染顶部弹窗（统计/浏览），确保每轮仅打开一个 dialog。"""
    active_dialog = st.session_state.get("active_top_dialog", "")
    if active_dialog not in ["stats", "browse"]:
        return

    if hasattr(st, "dialog"):

        def _render_dialog_body() -> None:
            if active_dialog == "stats":
                st.markdown("### 统计")
                if is_completed:
                    _render_completion_metrics()
                else:
                    _render_current_metrics()
            else:
                st.markdown("### 浏览")
                st.markdown(
                    """
                    <style>
                    div[data-testid="stDialog"] [role="dialog"] {
                        width: min(95vw, 1500px) !important;
                        max-width: 95vw !important;
                        min-width: 820px !important;
                        min-height: 460px !important;
                        max-height: 92vh !important;
                        resize: both !important;
                        overflow: auto !important;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                _render_result_browser_table()

            if st.button(
                "关闭", width="stretch", key=f"close_active_top_dialog{key_suffix}"
            ):
                st.session_state.show_live_stats = False
                st.session_state.show_result_browser = False
                st.session_state.active_top_dialog = ""
                st.rerun()

        try:

            @st.dialog("工具窗口", width="large", dismissible=False)
            def _active_top_dialog() -> None:
                _render_dialog_body()

        except TypeError:
            try:

                @st.dialog("工具窗口", dismissible=False)
                def _active_top_dialog() -> None:
                    _render_dialog_body()

            except TypeError:
                try:

                    @st.dialog("工具窗口", width="large")
                    def _active_top_dialog() -> None:
                        _render_dialog_body()

                except TypeError:

                    @st.dialog("工具窗口")
                    def _active_top_dialog() -> None:
                        _render_dialog_body()

        _active_top_dialog()
        return

    # 不支持 dialog 的环境回退为页面内展示
    if active_dialog == "stats":
        st.info("当前版本不支持弹窗，统计在页面内展示。")
        if is_completed:
            _render_completion_metrics()
        else:
            _render_current_metrics()
        if st.button(
            "关闭统计", width="stretch", key=f"close_fallback_stats{key_suffix}"
        ):
            st.session_state.show_live_stats = False
            st.session_state.active_top_dialog = ""
            st.rerun()
    else:
        st.info("当前版本不支持弹窗，浏览在页面内展示。")
        _render_result_browser_table()
        if st.button(
            "关闭浏览", width="stretch", key=f"close_fallback_browse{key_suffix}"
        ):
            st.session_state.show_result_browser = False
            st.session_state.active_top_dialog = ""
            st.rerun()


def _render_empty_state(example_file_path: Path) -> None:
    """渲染空数据状态的导入区。"""
    if "project_entry_state" not in st.session_state:
        st.session_state.project_entry_state = "entry"
    if "show_archive_loader" not in st.session_state:
        st.session_state.show_archive_loader = False
    if "archive_delete_target" not in st.session_state:
        st.session_state.archive_delete_target = ""

    if st.session_state.project_entry_state == "entry":
        entry_hint_text = t("请选择工作方式。")
        st.markdown(
            f"""
            <style>
            .entry-hint-box {{
                background: #dbe9f8;
                border-radius: 14px;
                min-height: 78px;
                display: flex;
                align-items: center;
                padding: 0 20px;
                margin-bottom: 14px;
                color: #0054a6;
                font-size: 1.05rem;
                font-weight: 500;
            }}
            </style>
            <div class="entry-hint-box">{entry_hint_text}</div>
            """,
            unsafe_allow_html=True,
        )
        entry_col1, entry_col2 = st.columns(2)
        with entry_col1:
            if st.button("加载存档", width="stretch", key="entry_load_archive"):
                st.session_state.show_archive_loader = True
        with entry_col2:
            if st.button(
                "开始新项目", type="primary", width="stretch", key="entry_start_new"
            ):
                st.session_state.project_entry_state = "new_project"
                st.session_state.show_archive_loader = False
                st.rerun()

        if st.session_state.show_archive_loader:
            archive_files = _list_archive_files()
            if not archive_files:
                st.warning("暂无存档文件，请先在评测页面点击“保存存档”。")
            else:
                archive_options = _build_archive_display_options(archive_files)
                default_name = archive_options[0]["file_name"]
                selected_name = st.selectbox(
                    "请选择存档",
                    options=archive_options,
                    index=0,
                    format_func=lambda item: item.get(
                        "label", item.get("file_name", "")
                    ),
                    key="entry_archive_selected",
                )
                target_name = (
                    selected_name.get("file_name", default_name)
                    if isinstance(selected_name, dict)
                    else default_name
                )

                load_col, delete_col, back_col = st.columns(3)
                with load_col:
                    if st.button(
                        "确认加载", width="stretch", key="entry_confirm_load_archive"
                    ):
                        ok, msg = _load_archive_checkpoint(target_name)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                with delete_col:
                    if st.button(
                        "删除存档", width="stretch", key="entry_delete_archive"
                    ):
                        st.session_state.archive_delete_target = target_name
                        st.rerun()
                with back_col:
                    if st.button(
                        "返回", width="stretch", key="entry_back_from_archive"
                    ):
                        st.session_state.show_archive_loader = False
                        st.session_state.archive_delete_target = ""
                        st.rerun()

                delete_target = str(
                    st.session_state.get("archive_delete_target", "")
                ).strip()
                if delete_target:
                    st.warning(f"确认删除存档：{delete_target}？删除后不可恢复。")
                    confirm_del_col, cancel_del_col = st.columns(2)
                    with confirm_del_col:
                        if st.button(
                            "确认删除",
                            type="primary",
                            width="stretch",
                            key="entry_confirm_delete_archive",
                        ):
                            ok, msg = _delete_archive_checkpoint(delete_target)
                            st.session_state.archive_delete_target = ""
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                    with cancel_del_col:
                        if st.button(
                            "取消删除",
                            width="stretch",
                            key="entry_cancel_delete_archive",
                        ):
                            st.session_state.archive_delete_target = ""
                            st.rerun()
        st.stop()

    if st.session_state.show_mode_selector and st.session_state.pending_records:
        pending_count = len(st.session_state.pending_records)
        st.success(f"数据已准备完成，共 {pending_count} 条，正在等待选择评测模式。")
        preview_data = st.session_state.pending_records[:5]
        st.dataframe(preview_data, width="stretch")
        _render_mode_selector()
        # 进入模式选择阶段后，不再继续执行下面的导入控件逻辑，避免状态被覆盖
        st.stop()

    st.info("评测区当前为空，请先加载数据。")

    uploaded_file = st.file_uploader(
        "从 Excel 导入",
        type=["xlsx", "xls"],
        help="请先上传 Excel，然后在下方映射 prompt 和 output 字段。首行为表头，每行一条评测数据，id 将自动生成。",
    )

    st.markdown("#### 可选项")
    st.checkbox("使用 System Prompt", key="use_system_prompt")
    if st.session_state.use_system_prompt:
        st.text_area(
            "System Prompt",
            placeholder="请输入固定的 System Prompt。启用后下一个页面将显示 system prompt 和 user prompt。",
            height=120,
            key="system_prompt_draft",
        )
        if st.button("应用 System Prompt", width="stretch", key="apply_system_prompt"):
            st.session_state.system_prompt_text = str(
                st.session_state.system_prompt_draft
            ).strip()
            if st.session_state.system_prompt_text:
                st.success("System Prompt 已应用。")
            else:
                st.warning("System Prompt 为空，应用后将不会生效。")

        if st.session_state.system_prompt_text:
            st.caption("当前已应用的 System Prompt：")
            st.code(st.session_state.system_prompt_text)

        if (
            str(st.session_state.system_prompt_draft).strip()
            != str(st.session_state.system_prompt_text).strip()
        ):
            st.info(
                "你修改了 System Prompt 草稿，请点击应用 System Prompt按钮使其生效。"
            )

    source_col1, source_col2 = st.columns(2)
    with source_col1:
        if st.button("使用示例数据", width="stretch"):
            if not example_file_path.exists():
                st.error("未找到示例文件 example.xlsx。")
            else:
                df = read_excel_file(example_file_path)
                if df is not None:
                    set_import_source(df, "example.xlsx")
                    st.rerun()
    with source_col2:
        st.button(
            "在线获取结果（暂未开放）",
            width="stretch",
            disabled=True,
            help="该功能将在后续版本提供，目前请使用 Excel 导入。",
        )

    if uploaded_file is not None:
        df = read_excel_file(uploaded_file)
        if df is not None:
            set_import_source(df, uploaded_file.name)

    active_df = st.session_state.import_dataframe
    if active_df is None:
        st.stop()

    all_columns = [str(col) for col in active_df.columns.tolist()]
    st.markdown("#### 字段映射")
    source_name = st.session_state.import_source_name or "当前数据"
    st.caption(
        f"数据源：{source_name}。请选择 Excel 中哪一列作为 Prompt，并可选择一个或多个 Output 列。"
    )
    st.dataframe(active_df.head(5), width="stretch")

    default_prompt_index = 0
    default_output_index = 1 if len(all_columns) > 1 else 0
    for idx, col_name in enumerate(all_columns):
        if col_name.lower() in ["prompt", "question", "input"]:
            default_prompt_index = idx
        if col_name.lower() in ["output", "answer", "response"]:
            default_output_index = idx

    prompt_column = st.selectbox(
        "请选择 Prompt 字段",
        options=all_columns,
        index=default_prompt_index,
        key="mapping_prompt_column",
    )

    # Prompt 列不应出现在 Output 选项中，且在 Prompt 切换后清理已选项。
    available_output_columns = [col for col in all_columns if col != prompt_column]
    current_selected_outputs = st.session_state.get("mapping_output_columns", [])
    filtered_selected_outputs = [
        col for col in current_selected_outputs if col in available_output_columns
    ]
    if filtered_selected_outputs != current_selected_outputs:
        st.session_state.mapping_output_columns = filtered_selected_outputs

    default_output_columns = filtered_selected_outputs
    if not default_output_columns and available_output_columns:
        preferred_output = all_columns[default_output_index] if all_columns else ""
        if preferred_output in available_output_columns:
            default_output_columns = [preferred_output]
        else:
            default_output_columns = [available_output_columns[0]]

    output_columns = st.multiselect(
        "请选择 Output 字段（可多选）",
        options=available_output_columns,
        default=default_output_columns,
        key="mapping_output_columns",
        help="可选择一个或多个 Output 列。",
    )

    mapping_action_col1, mapping_action_col2 = st.columns(2)
    with mapping_action_col1:
        if st.button("确认字段映射并加载", type="primary", width="stretch"):
            if (
                st.session_state.use_system_prompt
                and not str(st.session_state.system_prompt_text).strip()
            ):
                st.error("已启用 System Prompt，请先点击应用 System Prompt按钮。")
                st.stop()

            if st.session_state.use_system_prompt and (
                str(st.session_state.system_prompt_draft).strip()
                != str(st.session_state.system_prompt_text).strip()
            ):
                st.error("System Prompt 草稿尚未应用，请先点击应用 System Prompt按钮。")
                st.stop()

            parsed_records = build_records_from_mapping(
                active_df, prompt_column, output_columns
            )
            if parsed_records:
                st.session_state.pending_records = parsed_records
                st.session_state.show_mode_selector = True
                st.session_state.project_entry_state = "new_project"
                st.rerun()
    with mapping_action_col2:
        if st.button("取消当前数据源", width="stretch"):
            st.session_state.import_dataframe = None
            st.session_state.import_source_name = ""
            st.session_state.pending_records = []
            st.session_state.show_mode_selector = False
            st.rerun()

    st.stop()


def _render_manual_mode(current_item: dict) -> None:
    """渲染人工输入模式内容。"""

    def _render_manual_option_manager_dialog(item_id: str) -> None:
        dialog_flag_key = f"show_manual_option_manager_{item_id}"
        if not bool(st.session_state.get(dialog_flag_key, False)):
            return

        if hasattr(st, "dialog"):

            def _manual_option_manager_body() -> None:
                option_pool = st.session_state.get("manual_option_pool", [])

                header_spacer, header_close_col = st.columns([10, 1])
                with header_close_col:
                    if st.button(
                        "×",
                        width="stretch",
                        key=f"manual_close_option_dialog_x_{item_id}",
                    ):
                        st.session_state[dialog_flag_key] = False
                        st.rerun()

                new_option_text = st.text_input(
                    "新增选择项",
                    placeholder="输入要新增到集合中的结果文本",
                    key=f"manual_new_option_text_{item_id}",
                )
                if st.button(
                    "加入选择项",
                    width="stretch",
                    key=f"manual_add_option_btn_{item_id}",
                ):
                    new_option = str(new_option_text).strip()
                    if not new_option:
                        st.error("新增选择项不能为空。")
                    elif new_option in option_pool:
                        st.warning("该选择项已存在，无需重复添加。")
                    else:
                        option_pool.append(new_option)
                        st.session_state.manual_option_pool = option_pool
                        st.rerun()

                st.markdown("---")
                if option_pool:
                    st.selectbox(
                        "删除选择项",
                        options=option_pool,
                        key=f"manual_delete_option_{item_id}",
                    )
                    if st.button(
                        "删除选择项",
                        width="stretch",
                        key=f"manual_delete_option_btn_{item_id}",
                    ):
                        delete_option = st.session_state.get(
                            f"manual_delete_option_{item_id}"
                        )
                        if delete_option in option_pool:
                            option_pool.remove(delete_option)
                            st.session_state.manual_option_pool = option_pool
                            st.rerun()
                else:
                    st.caption("暂无可删除的选择项")

            try:

                @st.dialog("管理选择项", dismissible=False)
                def _manual_option_manager() -> None:
                    _manual_option_manager_body()

            except TypeError:

                @st.dialog("管理选择项")
                def _manual_option_manager() -> None:
                    _manual_option_manager_body()

            _manual_option_manager()
            return

        st.warning("当前版本不支持弹窗，请升级 Streamlit。")

    st.toggle(
        "显示 LLM 的结果",
        value=not st.session_state.hide_llm_output,
        key="manual_show_llm_output",
    )
    st.session_state.hide_llm_output = not st.session_state.manual_show_llm_output

    st.markdown(
        f'<div class="annotation-hint">{t("提示：上方 Output 区域是大模型输出；下方输入/选择区域是人工输出。")}</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.hide_llm_output:
        st.warning(f"Output：\n\n{current_item['output']}")
    else:
        st.caption("当前为人工输入结果模式，LLM 输出已隐藏。")

    input_mode = st.radio(
        "人工输入方式",
        options=["从结果集合选择", "手动打字输入"],
        horizontal=True,
        label_visibility="collapsed",
        key=f"manual_input_mode_{current_item['id']}",
    )

    if input_mode == "从结果集合选择":
        st.caption("可从已有结果集合中选择，也可手动新增或删除选择项。")
        option_pool = st.session_state.manual_option_pool

        if option_pool:
            st.selectbox(
                "从结果集合中选择",
                options=option_pool,
                label_visibility="collapsed",
                key=f"manual_result_select_{current_item['id']}",
            )
        else:
            st.warning("当前结果集合为空，请先新增选择项。")

        if st.button(
            "管理选择项",
            width="stretch",
            key=f"open_manual_option_manager_{current_item['id']}",
        ):
            st.session_state[
                f"show_manual_option_manager_{current_item['id']}"
            ] = True
            st.rerun()

        _render_manual_option_manager_dialog(str(current_item["id"]))
        return

    st.text_area(
        "人工输入结果",
        placeholder="请在这里输入当前样本的结果内容...",
        height=90,
        key=f"manual_result_text_{current_item['id']}",
    )


def _render_manual_save_action(current_item: dict) -> None:
    """渲染人工输入模式保存动作。"""
    if st.button("保存并下一条", type="primary", use_container_width=True):
        input_mode = st.session_state.get(
            f"manual_input_mode_{current_item['id']}", "手动打字输入"
        )
        if input_mode == "从结果集合选择":
            manual_result = st.session_state.get(
                f"manual_result_select_{current_item['id']}", ""
            )
        else:
            manual_result = st.session_state.get(
                f"manual_result_text_{current_item['id']}", ""
            )

        if not str(manual_result).strip():
            st.error("人工输入结果不能为空，请填写后再保存。")
        else:
            record_manual_annotation(
                llm_output=current_item.get("output", ""), manual_result=manual_result
            )
            go_next_item()
            st.rerun()


def _render_multi_mode(current_item: dict) -> None:
    """渲染多输出模式内容。"""
    output_list = current_item.get(
        "output_list", split_output_values(current_item.get("output", ""))
    )
    output_labels = current_item.get("output_labels", [])
    if len(output_list) < 2:
        st.error("当前数据不满足多输出模式（output 数量少于 2）。")
        return

    cols_per_row = 2 if len(output_list) == 2 else 3
    st.caption(
        f"当前样本包含 {len(output_list)} 个输出，请逐条标注（每行 {cols_per_row} 个）。"
    )
    for row_start in range(0, len(output_list), cols_per_row):
        row_cols = st.columns(cols_per_row)
        for col_offset in range(cols_per_row):
            item_pos = row_start + col_offset
            if item_pos >= len(output_list):
                continue

            idx = item_pos + 1
            output_text = output_list[item_pos]
            field_name = (
                str(output_labels[item_pos]).strip()
                if item_pos < len(output_labels)
                and str(output_labels[item_pos]).strip()
                else f"output_{idx}"
            )
            with row_cols[col_offset]:
                _render_compact_text(
                    title=field_name,
                    text=output_text,
                    key=f"multi_output_view_{current_item['id']}_{idx}",
                    variant="candidate",
                )
                st.radio(
                    f"{field_name} 标注",
                    options=["采纳", "拒绝"],
                    index=None,
                    horizontal=True,
                    key=f"multi_choice_{current_item['id']}_{idx}",
                )

    st.write("")
    st.divider()
    if st.button("保存并下一条", type="primary", use_container_width=True):
        decisions = []
        for idx in range(1, len(output_list) + 1):
            choice = st.session_state.get(f"multi_choice_{current_item['id']}_{idx}")
            if choice not in ["采纳", "拒绝"]:
                st.error("请先完成所有输出字段的标注。")
                return
            decisions.append(choice == "采纳")

        record_multi_output_annotation(
            item_id=current_item.get("id", ""),
            outputs=output_list,
            decisions=decisions,
        )
        go_next_item()
        st.rerun()


def _render_multi_manual_mode(current_item: dict) -> None:
    """渲染多输出下的人工输入模式（每个 output 单独选择或手输）。"""

    def _render_multi_manual_option_manager_dialog(current_item_id: str) -> None:
        target = st.session_state.get("multi_manual_option_dialog_target", {})
        if not isinstance(target, dict) or not target:
            return

        target_item_id = str(target.get("item_id", ""))
        if target_item_id != str(current_item_id):
            return

        out_idx = int(target.get("out_idx", 0) or 0)
        field_name = str(target.get("field_name", f"output_{out_idx or 1}"))
        if out_idx <= 0:
            st.session_state.multi_manual_option_dialog_target = {}
            return

        if hasattr(st, "dialog"):

            def _multi_manual_option_manager_body() -> None:
                option_pool_by_output = st.session_state.get(
                    "manual_option_pool_by_output", {}
                )
                option_pool = option_pool_by_output.get(out_idx, [])

                header_spacer, header_close_col = st.columns([10, 1])
                with header_close_col:
                    if st.button(
                        "×",
                        width="stretch",
                        key=f"multi_manual_close_option_dialog_x_{current_item_id}_{out_idx}",
                    ):
                        st.session_state.multi_manual_option_dialog_target = {}
                        st.rerun()

                new_option_text = st.text_input(
                    f"{field_name} 新增选择项",
                    placeholder="输入要新增到集合中的结果文本",
                    key=f"multi_manual_new_option_text_{current_item_id}_{out_idx}",
                )
                if st.button(
                    "加入选择项",
                    width="stretch",
                    key=f"multi_manual_add_option_btn_{current_item_id}_{out_idx}",
                ):
                    new_option = str(new_option_text).strip()
                    if not new_option:
                        st.error("新增选择项不能为空。")
                    elif new_option in option_pool:
                        st.warning("该选择项已存在，无需重复添加。")
                    else:
                        option_pool.append(new_option)
                        option_pool_by_output[out_idx] = option_pool
                        st.session_state.manual_option_pool_by_output = (
                            option_pool_by_output
                        )
                        st.rerun()

                st.markdown("---")
                if option_pool:
                    st.selectbox(
                        f"{field_name} 删除选择项",
                        options=option_pool,
                        key=f"multi_manual_delete_option_{current_item_id}_{out_idx}",
                    )
                    if st.button(
                        "删除选择项",
                        width="stretch",
                        key=f"multi_manual_del_option_btn_{current_item_id}_{out_idx}",
                    ):
                        delete_option = st.session_state.get(
                            f"multi_manual_delete_option_{current_item_id}_{out_idx}"
                        )
                        if delete_option in option_pool:
                            option_pool.remove(delete_option)
                            option_pool_by_output[out_idx] = option_pool
                            st.session_state.manual_option_pool_by_output = (
                                option_pool_by_output
                            )
                            st.rerun()
                else:
                    st.caption("暂无可删除的选择项")

            try:

                @st.dialog("管理选择项", dismissible=False)
                def _multi_manual_option_manager() -> None:
                    _multi_manual_option_manager_body()

            except TypeError:

                @st.dialog("管理选择项")
                def _multi_manual_option_manager() -> None:
                    _multi_manual_option_manager_body()

            _multi_manual_option_manager()
            return

        st.warning("当前版本不支持弹窗，请升级 Streamlit。")

    output_list = current_item.get(
        "output_list", split_output_values(current_item.get("output", ""))
    )
    output_labels = current_item.get("output_labels", [])
    if len(output_list) < 2:
        st.error("当前数据不满足多输出模式（output 数量少于 2）。")
        return

    st.markdown(
        f'<div class="annotation-hint">{t("提示：每个卡片展示的是大模型输出；卡片下方输入/选择区域是对应字段的人工输出。")}</div>',
        unsafe_allow_html=True,
    )

    cols_per_row = 2 if len(output_list) == 2 else 3
    st.caption(
        f"当前样本包含 {len(output_list)} 个输出，请对每个输出分别标注（每行 {cols_per_row} 个）。"
    )
    for row_start in range(0, len(output_list), cols_per_row):
        row_cols = st.columns(cols_per_row)
        for col_offset in range(cols_per_row):
            item_pos = row_start + col_offset
            if item_pos >= len(output_list):
                continue

            idx = item_pos + 1
            output_text = output_list[item_pos]
            field_name = (
                str(output_labels[item_pos]).strip()
                if item_pos < len(output_labels)
                and str(output_labels[item_pos]).strip()
                else f"output_{idx}"
            )
            with row_cols[col_offset]:
                _render_compact_text(
                    title=field_name,
                    text=output_text,
                    key=f"multi_manual_output_view_{current_item['id']}_{idx}",
                    variant="candidate",
                )

                input_mode = st.radio(
                    f"{field_name} 人工输入方式",
                    options=["从结果集合选择", "手动打字输入"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key=f"multi_manual_input_mode_{current_item['id']}_{idx}",
                )

                if input_mode == "从结果集合选择":
                    option_pool_by_output = st.session_state.get(
                        "manual_option_pool_by_output", {}
                    )
                    option_pool = option_pool_by_output.get(idx, [])
                    if option_pool:
                        st.selectbox(
                            f"{field_name} 从结果集合中选择",
                            options=option_pool,
                            label_visibility="collapsed",
                            key=f"multi_manual_select_{current_item['id']}_{idx}",
                        )
                    else:
                        st.warning(
                            f"{field_name} 的结果集合为空，请先为该字段新增选择项。"
                        )

                    if st.button(
                        "管理选择项",
                        width="stretch",
                        key=f"open_multi_manual_option_manager_{current_item['id']}_{idx}",
                    ):
                        st.session_state.multi_manual_option_dialog_target = {
                            "item_id": str(current_item["id"]),
                            "out_idx": idx,
                            "field_name": field_name,
                        }
                        st.rerun()
                else:
                    st.text_area(
                        f"{field_name} 人工输入结果",
                        placeholder="请在这里输入该字段对应的人工结果...",
                        height=80,
                        key=f"multi_manual_text_{current_item['id']}_{idx}",
                    )

    _render_multi_manual_option_manager_dialog(str(current_item["id"]))

    st.write("")
    st.divider()
    if st.button(
        "保存并下一条",
        type="primary",
        use_container_width=True,
        key=f"multi_manual_save_{current_item['id']}",
    ):
        manual_results = []
        for idx in range(1, len(output_list) + 1):
            input_mode = st.session_state.get(
                f"multi_manual_input_mode_{current_item['id']}_{idx}",
                "手动打字输入",
            )
            if input_mode == "从结果集合选择":
                manual_result = st.session_state.get(
                    f"multi_manual_select_{current_item['id']}_{idx}", ""
                )
            else:
                manual_result = st.session_state.get(
                    f"multi_manual_text_{current_item['id']}_{idx}", ""
                )

            if not str(manual_result).strip():
                field_name = (
                    str(output_labels[idx - 1]).strip()
                    if (idx - 1) < len(output_labels)
                    and str(output_labels[idx - 1]).strip()
                    else f"output_{idx}"
                )
                st.error(f"{field_name} 的人工输入结果不能为空。")
                return
            manual_results.append(str(manual_result).strip())

        record_multi_output_manual_annotation(
            item_id=current_item.get("id", ""),
            outputs=output_list,
            manual_results=manual_results,
        )
        for output_text, manual_result in zip(output_list, manual_results):
            record_manual_annotation(
                llm_output=output_text, manual_result=manual_result
            )
        go_next_item()
        st.rerun()


def _render_completion_metrics() -> None:
    """渲染评测完成后的指标汇总。"""
    display = _collect_display_metrics_for_mode()

    if st.session_state.eval_mode == "direct":
        metrics = display["metrics"]
        st.markdown("### 评测指标（直接判断模式）")
        metric_col1, metric_col2 = st.columns(2)
        with metric_col1:
            st.metric("完成总数", metrics["total"])
        with metric_col2:
            st.metric("Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
        return

    if st.session_state.eval_mode == "multi":
        metrics = display["metrics"]
        metrics_by_output = display["metrics_by_output"]
        st.markdown("### 评测指标（多输出模式）")
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        with metric_col1:
            st.metric("完成样本数", display["completed_samples"])
        with metric_col2:
            st.metric("已标注输出数", display["labeled_outputs"])
        with metric_col3:
            st.metric("Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
        _render_output_metrics_table(
            metrics_by_output, manual_mode=False, title="各 Output 指标"
        )
        return

    if st.session_state.eval_mode == "multi_manual":
        metrics = display["metrics"]
        metrics_by_output = display["metrics_by_output"]
        st.markdown("### 评测指标（多输出人工输入模式）")
        metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
        with metric_col1:
            st.metric("完成样本数", display["completed_samples"])
        with metric_col2:
            st.metric("已标注输出数", display["labeled_outputs"])
        with metric_col3:
            st.metric("Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
        with metric_col4:
            st.metric("Precision", f"{metrics['precision'] * 100:.2f}%")
        with metric_col5:
            st.metric("Recall", f"{metrics['recall'] * 100:.2f}%")
        metric_col6, _ = st.columns(2)
        with metric_col6:
            st.metric("F1", f"{metrics['f1'] * 100:.2f}%")

        _render_output_metrics_table(
            metrics_by_output, manual_mode=True, title="各 Output 指标"
        )
        return

    metrics = display["metrics"]
    st.markdown("### 评测指标（人工输入结果模式）")
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        st.metric("完成总数", metrics["total"])
    with metric_col2:
        st.metric("Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
    with metric_col3:
        st.metric("Precision", f"{metrics['precision'] * 100:.2f}%")
    metric_col4, metric_col5 = st.columns(2)
    with metric_col4:
        st.metric("Recall", f"{metrics['recall'] * 100:.2f}%")
    with metric_col5:
        st.metric("F1 Score", f"{metrics['f1'] * 100:.2f}%")


def _render_current_metrics() -> None:
    """渲染当前进行中的统计指标。"""
    display = _collect_display_metrics_for_mode()

    if st.session_state.eval_mode == "direct":
        metrics = display["metrics"]
        st.markdown("### 当前统计（直接判断模式）")
        metric_col1, metric_col2 = st.columns(2)
        with metric_col1:
            st.metric("已评测数", metrics["total"])
        with metric_col2:
            st.metric("当前 Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
        return

    if st.session_state.eval_mode == "multi":
        metrics = display["metrics"]
        metrics_by_output = display["metrics_by_output"]
        st.markdown("### 当前统计（多输出模式）")
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        with metric_col1:
            st.metric("已完成样本数", display["completed_samples"])
        with metric_col2:
            st.metric("已标注输出数", display["labeled_outputs"])
        with metric_col3:
            st.metric("当前 Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
        _render_output_metrics_table(
            metrics_by_output, manual_mode=False, title="各 Output 当前指标"
        )
        return

    if st.session_state.eval_mode == "multi_manual":
        metrics = display["metrics"]
        metrics_by_output = display["metrics_by_output"]
        st.markdown("### 当前统计（多输出人工输入模式）")
        metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
        with metric_col1:
            st.metric("已完成样本数", display["completed_samples"])
        with metric_col2:
            st.metric("已标注输出数", display["labeled_outputs"])
        with metric_col3:
            st.metric("当前 Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
        with metric_col4:
            st.metric("当前 Precision", f"{metrics['precision'] * 100:.2f}%")
        with metric_col5:
            st.metric("当前 Recall", f"{metrics['recall'] * 100:.2f}%")

        metric_col6, _ = st.columns(2)
        with metric_col6:
            st.metric("当前 F1", f"{metrics['f1'] * 100:.2f}%")

        _render_output_metrics_table(
            metrics_by_output, manual_mode=True, title="各 Output 当前指标"
        )
        return

    metrics = display["metrics"]
    st.markdown("### 当前统计（人工输入结果模式）")
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        st.metric("已评测数", metrics["total"])
    with metric_col2:
        st.metric("当前 Accuracy", f"{metrics['accuracy'] * 100:.2f}%")
    with metric_col3:
        st.metric("当前 Precision", f"{metrics['precision'] * 100:.2f}%")
    metric_col4, metric_col5 = st.columns(2)
    with metric_col4:
        st.metric("当前 Recall", f"{metrics['recall'] * 100:.2f}%")
    with metric_col5:
        st.metric("当前 F1 Score", f"{metrics['f1'] * 100:.2f}%")


def render_evaluation_panel(example_file_path: Path):
    """渲染左侧评测区，并返回当前样本。"""
    _render_compact_metric_style()

    records = st.session_state.records
    total_count = len(records)
    current_index = st.session_state.current_index

    # 有加载数据时，刷新前二次确认，避免误丢评测进度。
    has_loaded_data = bool(total_count > 0 or st.session_state.get("pending_records"))
    _inject_refresh_confirm_guard(enabled=has_loaded_data)

    if "show_result_browser" not in st.session_state:
        st.session_state.show_result_browser = False
    if "active_top_dialog" not in st.session_state:
        st.session_state.active_top_dialog = ""
    if "show_save_archive_dialog" not in st.session_state:
        st.session_state.show_save_archive_dialog = False

    if total_count == 0:
        _render_empty_state(example_file_path)

    if current_index >= total_count:
        _render_top_action_bar(
            total_count=total_count,
            current_index=current_index,
            is_completed=True,
            key_suffix="_completed",
        )

        if st.session_state.show_clear_confirm:
            _render_clear_confirm()

        elif st.session_state.show_save_archive_dialog:
            _render_save_archive_dialog(key_suffix="_completed")

        elif st.session_state.active_top_dialog in ["stats", "browse"]:
            _render_active_top_dialog(is_completed=True, key_suffix="_completed")

        st.success(" 恭喜，所有数据评测完成！")
        _render_completion_metrics()
        st.stop()

    current_item = records[current_index]
    _render_top_action_bar(
        total_count=total_count,
        current_index=current_index,
        is_completed=False,
        key_suffix="_running",
    )

    if st.session_state.show_clear_confirm:
        _render_clear_confirm()

    elif st.session_state.show_save_archive_dialog:
        _render_save_archive_dialog(key_suffix="_running")

    elif st.session_state.active_top_dialog in ["stats", "browse"]:
        _render_active_top_dialog(is_completed=False, key_suffix="_running")

    col_left, col_right = st.columns([6, 4], gap="large", vertical_alignment="top")

    with col_left:
        with st.container(border=True):
            st.markdown("##### 🎯 标注操作")
            if st.session_state.eval_mode == "manual":
                _render_manual_mode(current_item)
                st.write("")
                st.divider()
                _render_manual_save_action(current_item)
            elif st.session_state.eval_mode == "multi_manual":
                _render_multi_manual_mode(current_item)
            elif st.session_state.eval_mode == "multi":
                _render_multi_mode(current_item)
            else:
                st.warning(f"Output：\n\n{current_item['output']}")
                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    if st.button(" 采纳 (正确)", use_container_width=True):
                        record_direct_decision(is_accept=True)
                        go_next_item()
                        st.rerun()
                with action_col2:
                    if st.button(" 拒绝 (错误)", use_container_width=True):
                        record_direct_decision(is_accept=False)
                        go_next_item()
                        st.rerun()

    with col_right:
        with st.container(border=True):
            st.markdown("##### 📝 文本")
            def _build_prompt_card(
                title: str, content: str, variant: str = "user"
            ) -> str:
                safe_title = html.escape(str(title or ""))
                safe_content = html.escape(str(content or "")).replace(
                    "\n", "<br>"
                )
                if variant == "system":
                    bg_color = "#f6f7f9"
                    border_color = "#d8dee9"
                else:
                    bg_color = "#eef5ff"
                    border_color = "#c9d9f2"
                return (
                    f'<div style="border:1px solid {border_color};border-radius:10px;padding:12px 14px;background:{bg_color};margin-bottom:14px;">'
                    f'<div style="font-weight:600;color:#1f2937;margin-bottom:8px;">{safe_title}</div>'
                    f'<div style="line-height:1.6;color:#333333;word-break:break-word;">{safe_content}</div>'
                    "</div>"
                )

            prompt_cards = []
            if current_item.get("system_prompt"):
                prompt_cards.append(
                    _build_prompt_card(
                        "System Prompt",
                        current_item.get("system_prompt", ""),
                        variant="system",
                    )
                )
                prompt_cards.append(
                    _build_prompt_card(
                        "User Prompt",
                        current_item.get("user_prompt", current_item.get("prompt", "")),
                        variant="user",
                    )
                )
            else:
                prompt_cards.append(
                    _build_prompt_card(
                        "Prompt",
                        current_item.get("prompt", ""),
                        variant="user",
                    )
                )

            st.markdown(
                '<div style="max-height:500px;overflow-y:auto;padding-right:4px;">'
                + "".join(prompt_cards)
                + "</div>",
                unsafe_allow_html=True,
            )

    return current_item
