import streamlit as st
import json


def init_session_state() -> None:
    """初始化应用所需的全部会话状态。"""
    defaults = {
        "current_index": 0,
        "show_correction": False,
        "records": [],
        "show_clear_confirm": False,
        "pending_records": [],
        "show_mode_selector": False,
        "project_entry_state": "entry",
        "show_archive_loader": False,
        "archive_delete_target": "",
        "archive_file_name": "",
        "show_save_archive_dialog": False,
        "archive_confirm_overwrite": False,
        "archive_pending_name": "",
        "eval_mode": "direct",
        "hide_llm_output": False,
        "import_dataframe": None,
        "import_source_name": "",
        "manual_option_pool": [],
        "manual_option_pool_by_output": {},
        "direct_decisions": [],
        "manual_annotations": [],
        "use_system_prompt": False,
        "system_prompt_text": "",
        "system_prompt_draft": "",
        "sandbox_system_prompt": "",
        "show_live_stats": False,
        "active_top_dialog": "",
        "show_result_browser": False,
        "browse_rows_override": [],
        "browse_rows_override_mode": "",
        "browse_rows_dirty": False,
        "browse_cell_overrides": {},
        "browse_undo_stack": [],
        "multi_output_annotations": [],
        "multi_output_decisions": [],
        "multi_output_manual_annotations": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_loaded_data() -> None:
    """清空当前导入的数据，并回到初始页面。"""
    st.session_state.records = []
    st.session_state.pending_records = []
    st.session_state.manual_option_pool = []
    st.session_state.manual_option_pool_by_output = {}
    st.session_state.project_entry_state = "entry"
    st.session_state.show_archive_loader = False
    st.session_state.archive_delete_target = ""
    st.session_state.archive_file_name = ""
    st.session_state.show_save_archive_dialog = False
    st.session_state.archive_confirm_overwrite = False
    st.session_state.archive_pending_name = ""
    st.session_state.import_dataframe = None
    st.session_state.import_source_name = ""
    st.session_state.current_index = 0
    st.session_state.show_correction = False
    st.session_state.show_clear_confirm = False
    st.session_state.show_mode_selector = False
    st.session_state.eval_mode = "direct"
    st.session_state.hide_llm_output = False
    st.session_state.direct_decisions = []
    st.session_state.manual_annotations = []
    st.session_state.use_system_prompt = False
    st.session_state.system_prompt_text = ""
    st.session_state.system_prompt_draft = ""
    st.session_state.sandbox_system_prompt = ""
    st.session_state.show_live_stats = False
    st.session_state.active_top_dialog = ""
    st.session_state.show_result_browser = False
    st.session_state.browse_rows_override = []
    st.session_state.browse_rows_override_mode = ""
    st.session_state.browse_rows_dirty = False
    st.session_state.browse_cell_overrides = {}
    st.session_state.browse_undo_stack = []
    st.session_state.multi_output_annotations = []
    st.session_state.multi_output_decisions = []
    st.session_state.multi_output_manual_annotations = []


def go_next_item() -> None:
    """进入下一条数据，并重置修正框显示状态。"""
    st.session_state.current_index += 1
    st.session_state.show_correction = False


def go_previous_item() -> bool:
    """回到上一条数据，并撤销上一条已记录的标注。"""
    records = st.session_state.get("records", [])
    total = len(records)
    if total == 0:
        return False

    current_index = int(st.session_state.get("current_index", 0) or 0)
    current_index = max(0, min(current_index, total))
    if current_index <= 0:
        return False

    rollback_target_index = current_index - 1
    eval_mode = str(st.session_state.get("eval_mode", "direct"))

    def _restore_manual_widget_state(target_record: dict, manual_result: str) -> None:
        item_id = str(target_record.get("id", ""))
        option_pool = st.session_state.get("manual_option_pool", [])
        if manual_result in option_pool:
            st.session_state[f"manual_input_mode_{item_id}"] = "从结果集合选择"
            st.session_state[f"manual_result_select_{item_id}"] = manual_result
        else:
            st.session_state[f"manual_input_mode_{item_id}"] = "手动打字输入"
            st.session_state[f"manual_result_text_{item_id}"] = manual_result

    def _restore_multi_manual_widget_state(
        target_record: dict, manual_results: list[str]
    ) -> None:
        item_id = str(target_record.get("id", ""))
        option_pool_by_output = st.session_state.get("manual_option_pool_by_output", {})
        for out_idx, manual_result in enumerate(manual_results, start=1):
            pool = option_pool_by_output.get(out_idx, [])
            if manual_result in pool:
                st.session_state[f"multi_manual_input_mode_{item_id}_{out_idx}"] = (
                    "从结果集合选择"
                )
                st.session_state[f"multi_manual_select_{item_id}_{out_idx}"] = (
                    manual_result
                )
            else:
                st.session_state[f"multi_manual_input_mode_{item_id}_{out_idx}"] = (
                    "手动打字输入"
                )
                st.session_state[f"multi_manual_text_{item_id}_{out_idx}"] = (
                    manual_result
                )

    if eval_mode == "direct":
        decisions = st.session_state.get("direct_decisions", [])
        if isinstance(decisions, list) and decisions:
            decisions.pop()
            st.session_state.direct_decisions = decisions

    elif eval_mode == "manual":
        annotations = st.session_state.get("manual_annotations", [])
        if isinstance(annotations, list) and annotations:
            last_item = annotations.pop()
            st.session_state.manual_annotations = annotations
            if rollback_target_index < total:
                target_record = records[rollback_target_index]
                restore_value = str(last_item.get("manual_result", "")).strip()
                _restore_manual_widget_state(target_record, restore_value)

    elif eval_mode == "multi":
        annotations = st.session_state.get("multi_output_annotations", [])
        removed_output_count = 0
        if isinstance(annotations, list) and annotations:
            last_item = annotations.pop()
            removed_output_count = len(last_item.get("decisions", []))
            st.session_state.multi_output_annotations = annotations
            if rollback_target_index < total:
                target_record = records[rollback_target_index]
                item_id = str(target_record.get("id", ""))
                decisions = last_item.get("decisions", [])
                for out_idx, decision in enumerate(decisions, start=1):
                    st.session_state[f"multi_choice_{item_id}_{out_idx}"] = (
                        "采纳" if bool(decision) else "拒绝"
                    )

        if removed_output_count <= 0 and rollback_target_index < total:
            fallback_outputs = records[rollback_target_index].get(
                "output_list",
                split_output_values(records[rollback_target_index].get("output", "")),
            )
            removed_output_count = len(fallback_outputs)

        all_decisions = st.session_state.get("multi_output_decisions", [])
        if isinstance(all_decisions, list) and all_decisions:
            if removed_output_count > 0:
                del all_decisions[-min(removed_output_count, len(all_decisions)) :]
            else:
                all_decisions.pop()
            st.session_state.multi_output_decisions = all_decisions

    elif eval_mode == "multi_manual":
        multi_annotations = st.session_state.get("multi_output_manual_annotations", [])
        removed_output_count = 0
        if isinstance(multi_annotations, list) and multi_annotations:
            last_item = multi_annotations.pop()
            removed_output_count = len(last_item.get("manual_results", []))
            st.session_state.multi_output_manual_annotations = multi_annotations
            if rollback_target_index < total:
                target_record = records[rollback_target_index]
                restore_values = [
                    str(v).strip() for v in last_item.get("manual_results", [])
                ]
                _restore_multi_manual_widget_state(target_record, restore_values)

        if removed_output_count <= 0 and rollback_target_index < total:
            fallback_outputs = records[rollback_target_index].get(
                "output_list",
                split_output_values(records[rollback_target_index].get("output", "")),
            )
            removed_output_count = len(fallback_outputs)

        flat_annotations = st.session_state.get("manual_annotations", [])
        if isinstance(flat_annotations, list) and flat_annotations:
            if removed_output_count > 0:
                del flat_annotations[-min(removed_output_count, len(flat_annotations)) :]
            else:
                flat_annotations.pop()
            st.session_state.manual_annotations = flat_annotations

    st.session_state.current_index = rollback_target_index
    st.session_state.show_correction = False

    # 回退后清理浏览态覆盖，避免旧覆盖与当前结果不一致。
    st.session_state.browse_rows_override = []
    st.session_state.browse_rows_override_mode = ""
    st.session_state.browse_rows_dirty = False
    st.session_state.browse_cell_overrides = {}
    st.session_state.browse_undo_stack = []

    return True


def apply_loaded_records(eval_mode: str) -> bool:
    """应用已解析的数据与评测模式，正式进入评测阶段。"""
    system_prompt = str(st.session_state.system_prompt_text).strip()
    use_system_prompt = bool(st.session_state.use_system_prompt and system_prompt)

    def split_user_prompt(prompt_text: str, sys_prompt: str) -> str:
        """从完整 prompt 中尽量稳健地剥离 system prompt 前缀。"""
        if not sys_prompt:
            return prompt_text

        # 1) 最常见：原文直接以前缀形式包含 system prompt
        if prompt_text.startswith(sys_prompt):
            return prompt_text[len(sys_prompt) :].lstrip("\n\r \t")

        # 2) 忽略首尾空白后再比较，兼容上传数据里的换行/空格差异
        prompt_trimmed = prompt_text.strip()
        sys_trimmed = sys_prompt.strip()
        if prompt_trimmed.startswith(sys_trimmed):
            return prompt_trimmed[len(sys_trimmed) :].lstrip("\n\r \t")

        # 3) 回退：删除首个出现的 system prompt（若存在）
        idx = prompt_text.find(sys_prompt)
        if idx >= 0:
            prefix = prompt_text[:idx]
            suffix = prompt_text[idx + len(sys_prompt) :]
            return f"{prefix}{suffix}".strip()

        return prompt_text

    processed_records = []
    for item in st.session_state.pending_records:
        prompt_text = str(item.get("prompt", ""))
        record = dict(item)
        if use_system_prompt:
            user_prompt = split_user_prompt(prompt_text, system_prompt)
            record["system_prompt"] = system_prompt
            record["user_prompt"] = user_prompt
        else:
            record["user_prompt"] = prompt_text

        if eval_mode in ["multi", "multi_manual"]:
            output_list = record.get("output_list")
            if not isinstance(output_list, list) or len(output_list) == 0:
                output_list = split_output_values(record.get("output", ""))
            output_labels = record.get("output_labels")
            if not isinstance(output_labels, list):
                output_labels = []

            clean_outputs = []
            clean_labels = []
            for idx, output_value in enumerate(output_list):
                text = str(output_value).strip()
                if not text:
                    continue
                clean_outputs.append(text)
                if idx < len(output_labels) and str(output_labels[idx]).strip():
                    clean_labels.append(str(output_labels[idx]).strip())
                else:
                    clean_labels.append(f"output_{idx + 1}")

            output_list = clean_outputs
            output_labels = clean_labels
            if len(output_list) < 2:
                item_id = record.get("id", "未知")
                st.error(
                    f"多输出模式要求每条数据至少 2 个 output，当前样本 id={item_id} 不满足。"
                )
                return False
            record["output_list"] = output_list
            record["output_labels"] = output_labels
        processed_records.append(record)

    st.session_state.records = processed_records
    st.session_state.pending_records = []
    st.session_state.import_dataframe = None
    st.session_state.import_source_name = ""
    st.session_state.current_index = 0
    st.session_state.show_correction = False
    st.session_state.show_mode_selector = False
    st.session_state.project_entry_state = "new_project"
    st.session_state.show_archive_loader = False
    st.session_state.archive_delete_target = ""
    st.session_state.archive_file_name = ""
    st.session_state.show_save_archive_dialog = False
    st.session_state.archive_confirm_overwrite = False
    st.session_state.archive_pending_name = ""
    st.session_state.eval_mode = eval_mode
    st.session_state.hide_llm_output = False
    st.session_state.direct_decisions = []
    st.session_state.manual_annotations = []
    st.session_state.sandbox_system_prompt = system_prompt if use_system_prompt else ""
    st.session_state.show_live_stats = False
    st.session_state.active_top_dialog = ""
    st.session_state.show_result_browser = False
    st.session_state.browse_rows_override = []
    st.session_state.browse_rows_override_mode = ""
    st.session_state.browse_rows_dirty = False
    st.session_state.browse_cell_overrides = {}
    st.session_state.browse_undo_stack = []
    st.session_state.multi_output_annotations = []
    st.session_state.multi_output_decisions = []
    st.session_state.multi_output_manual_annotations = []

    if eval_mode in ["manual", "multi_manual"]:
        option_pool = []
        option_pool_by_output = {}
        for item in st.session_state.records:
            if eval_mode == "multi_manual":
                for out_idx, output_text in enumerate(
                    item.get("output_list", []), start=1
                ):
                    text = str(output_text).strip()
                    if text and text not in option_pool:
                        option_pool.append(text)
                    if out_idx not in option_pool_by_output:
                        option_pool_by_output[out_idx] = []
                    if text and text not in option_pool_by_output[out_idx]:
                        option_pool_by_output[out_idx].append(text)
            else:
                output_text = str(item.get("output", "")).strip()
                if output_text and output_text not in option_pool:
                    option_pool.append(output_text)
        st.session_state.manual_option_pool = option_pool
        st.session_state.manual_option_pool_by_output = option_pool_by_output
    else:
        st.session_state.manual_option_pool = []
        st.session_state.manual_option_pool_by_output = {}

    return True


def set_import_source(df, source_name: str) -> None:
    """设置当前待映射的数据源。"""
    st.session_state.import_dataframe = df
    st.session_state.import_source_name = source_name
    st.session_state.pending_records = []
    st.session_state.show_mode_selector = False


def record_direct_decision(is_accept: bool) -> None:
    """记录直接判断模式下的采纳/拒绝结果。"""
    st.session_state.direct_decisions.append(bool(is_accept))


def record_manual_annotation(llm_output: str, manual_result: str) -> None:
    """记录人工输入模式下的标注结果。"""
    st.session_state.manual_annotations.append(
        {
            "llm_output": str(llm_output).strip(),
            "manual_result": str(manual_result).strip(),
        }
    )


def split_output_values(output_value):
    """将 output 字段解析为多个候选结果。"""
    if isinstance(output_value, list):
        return [str(v).strip() for v in output_value if str(v).strip()]

    text = str(output_value or "")
    if not text.strip():
        return []

    # 优先尝试 JSON 数组格式
    stripped = text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                items = [str(v).strip() for v in parsed if str(v).strip()]
                if len(items) > 0:
                    return items
        except Exception:
            pass

    # 再尝试常见分隔符
    for sep in ["||", "\n", "；", ";", "|"]:
        parts = [p.strip() for p in text.split(sep) if p.strip()]
        if len(parts) >= 2:
            return parts

    return [text.strip()]


def record_multi_output_annotation(item_id, outputs, decisions):
    """记录多输出模式下单条样本的标注结果。"""
    st.session_state.multi_output_annotations.append(
        {
            "id": str(item_id),
            "outputs": [str(v) for v in outputs],
            "decisions": [bool(v) for v in decisions],
        }
    )
    st.session_state.multi_output_decisions.extend([bool(v) for v in decisions])


def record_multi_output_manual_annotation(item_id, outputs, manual_results):
    """记录多输出人工输入模式下单条样本的标注结果。"""
    st.session_state.multi_output_manual_annotations.append(
        {
            "id": str(item_id),
            "outputs": [str(v) for v in outputs],
            "manual_results": [str(v).strip() for v in manual_results],
        }
    )
