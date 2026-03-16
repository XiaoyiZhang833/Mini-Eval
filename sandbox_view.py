import os
import csv
import io
import json
from datetime import datetime

import streamlit as st

from i18n import t


def _render_sandbox_style() -> None:
    """侧边栏沙盒样式优化。"""
    st.markdown(
        """
        <style>
        .sandbox-header {
            background: linear-gradient(135deg, #e8f2ff 0%, #f7fbff 100%);
            border: 1px solid #c6d8f2;
            border-radius: 10px;
            padding: 8px 10px;
            margin-bottom: 8px;
            color: #111111;
        }
        .sandbox-header .title {
            font-size: 0.95rem;
            font-weight: 700;
            line-height: 1.2;
            margin-bottom: 2px;
        }
        .sandbox-header .desc {
            font-size: 0.76rem;
            color: #243447;
            line-height: 1.25;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _call_openai(
    system_prompt: str, user_prompt: str, model_name: str, api_key: str, base_url: str
):
    """调用 OpenAI 兼容接口生成回复。"""
    try:
        from openai import OpenAI
    except ImportError:
        st.error("当前环境未安装 openai 库，请先执行：pip install openai")
        return None

    if base_url.strip():
        client = OpenAI(api_key=api_key, base_url=base_url.strip())
    else:
        client = OpenAI(api_key=api_key)
    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": user_prompt.strip()})

    response = client.chat.completions.create(
        model=model_name.strip(),
        messages=messages,
        temperature=0.2,
    )

    if not response.choices:
        return ""

    content = response.choices[0].message.content
    return content if content is not None else ""


def _init_batch_state() -> None:
    """初始化批量任务状态。"""
    defaults = {
        "sandbox_batch_running": False,
        "sandbox_batch_stop_requested": False,
        "sandbox_batch_queue": [],
        "sandbox_batch_total": 0,
        "sandbox_batch_processed": 0,
        "sandbox_batch_fail_indices": [],
        "sandbox_batch_status": "idle",  # idle/running/completed/interrupted
        "sandbox_batch_message": "",
        "sandbox_batch_model": "",
        "sandbox_batch_api_key": "",
        "sandbox_batch_base_url": "",
        "sandbox_batch_system_prompt": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _start_batch(
    queue_indices, system_prompt: str, model_name: str, api_key: str, base_url: str
) -> None:
    """启动批量任务。"""
    st.session_state.sandbox_batch_running = True
    st.session_state.sandbox_batch_stop_requested = False
    st.session_state.sandbox_batch_queue = list(queue_indices)
    st.session_state.sandbox_batch_total = len(queue_indices)
    st.session_state.sandbox_batch_processed = 0
    st.session_state.sandbox_batch_fail_indices = []
    st.session_state.sandbox_batch_status = "running"
    st.session_state.sandbox_batch_message = "批量任务已启动。"
    st.session_state.sandbox_batch_model = model_name
    st.session_state.sandbox_batch_api_key = api_key
    st.session_state.sandbox_batch_base_url = base_url
    st.session_state.sandbox_batch_system_prompt = system_prompt


def _process_batch_step() -> None:
    """单步执行批量任务，配合 rerun 实现可挂起执行。"""
    if not st.session_state.sandbox_batch_running:
        return

    if st.session_state.sandbox_batch_stop_requested:
        st.session_state.sandbox_batch_running = False
        st.session_state.sandbox_batch_status = "interrupted"
        st.session_state.sandbox_batch_message = "任务已中断。"
        return

    queue_indices = st.session_state.sandbox_batch_queue
    if not queue_indices:
        st.session_state.sandbox_batch_running = False
        st.session_state.sandbox_batch_status = "completed"
        fail_count = len(st.session_state.sandbox_batch_fail_indices)
        total = st.session_state.sandbox_batch_total
        st.session_state.sandbox_batch_message = (
            f"任务完成：共 {total} 条，失败 {fail_count} 条。"
        )
        return

    idx = queue_indices.pop(0)
    records = st.session_state.get("records", [])
    if idx >= len(records):
        st.session_state.sandbox_batch_fail_indices.append(idx)
        st.session_state.sandbox_batch_processed += 1
        return

    item = dict(records[idx])
    user_prompt = str(item.get("user_prompt", item.get("prompt", "")))
    try:
        result_text = _call_openai(
            system_prompt=st.session_state.sandbox_batch_system_prompt,
            user_prompt=user_prompt,
            model_name=st.session_state.sandbox_batch_model,
            api_key=st.session_state.sandbox_batch_api_key,
            base_url=st.session_state.sandbox_batch_base_url,
        )
        if result_text is not None:
            item["output"] = result_text
            records[idx] = item
            st.session_state.records = records
        else:
            st.session_state.sandbox_batch_fail_indices.append(idx)
    except Exception:
        st.session_state.sandbox_batch_fail_indices.append(idx)

    st.session_state.sandbox_batch_processed += 1

    if st.session_state.sandbox_batch_queue:
        st.rerun()
    else:
        st.session_state.sandbox_batch_running = False
        st.session_state.sandbox_batch_status = "completed"
        fail_count = len(st.session_state.sandbox_batch_fail_indices)
        total = st.session_state.sandbox_batch_total
        st.session_state.sandbox_batch_message = (
            f"任务完成：共 {total} 条，失败 {fail_count} 条。"
        )


def _build_batch_export_rows():
    """构建批量任务结果导出内容。"""
    records = st.session_state.get("records", [])
    fail_set = set(st.session_state.get("sandbox_batch_fail_indices", []))
    rows = []
    for idx, item in enumerate(records):
        rows.append(
            {
                "index": idx,
                "id": item.get("id", ""),
                "prompt": item.get("prompt", ""),
                "system_prompt": item.get("system_prompt", ""),
                "user_prompt": item.get("user_prompt", item.get("prompt", "")),
                "output": item.get("output", ""),
                "is_failed": "1" if idx in fail_set else "0",
            }
        )
    return rows


def _rows_to_csv(rows) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _render_batch_export() -> None:
    """任务完成后渲染导出按钮。"""
    rows = _build_batch_export_rows()
    if not rows:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"batch_rerun_{timestamp}"
    csv_content = _rows_to_csv(rows)
    json_content = json.dumps({"results": rows}, ensure_ascii=False, indent=2)

    excel_content = None
    try:
        import pandas as pd

        excel_buffer = io.BytesIO()
        pd.DataFrame(rows).to_excel(excel_buffer, index=False, sheet_name="results")
        excel_content = excel_buffer.getvalue()
    except Exception:
        excel_content = None

    st.markdown("#### 任务结果下载")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "导出 CSV",
            data=csv_content,
            file_name=f"{base_name}.csv",
            mime="text/csv",
            width="stretch",
        )
    with col2:
        st.download_button(
            "导出 JSON",
            data=json_content,
            file_name=f"{base_name}.json",
            mime="application/json",
            width="stretch",
        )
    with col3:
        if excel_content is None:
            st.button("导出 Excel", disabled=True, width="stretch")
        else:
            st.download_button(
                "导出 Excel",
                data=excel_content,
                file_name=f"{base_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )


def render_sandbox_panel(current_item: dict) -> None:
    """渲染右侧 Prompt 调试沙盒。"""
    _render_sandbox_style()
    title_text = t("Prompt 调试沙盒")
    desc_text = t(
        "适用于所有评测模式，可单条重生成，也可在 System Prompt 场景批量重跑。"
    )
    st.markdown(
        f"""
        <div class="sandbox-header">
            <div class="title">{title_text}</div>
            <div class="desc">{desc_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _init_batch_state()

    default_model = "deepseek-chat"
    model_name = st.text_input(
        "模型名称", value=default_model, key=f"model_name_{current_item['id']}"
    )
    api_key_input = st.text_input(
        "OpenAI API Key（可选，留空则使用环境变量 OPENAI_API_KEY）",
        type="password",
        key=f"api_key_{current_item['id']}",
    )
    base_url = st.text_input(
        "Base URL（可选，用于本地模型或兼容 OpenAI 的网关）",
        value="https://api.deepseek.com",
        placeholder="例如：https://api.openai.com/v1 或你的本地网关地址",
        key=f"base_url_{current_item['id']}",
    )

    default_system_prompt = current_item.get("system_prompt", "")
    default_user_prompt = current_item.get(
        "user_prompt", current_item.get("prompt", "")
    )

    if "sandbox_system_prompt" not in st.session_state:
        st.session_state.sandbox_system_prompt = default_system_prompt

    edited_system_prompt = st.text_area(
        "System Prompt",
        key="sandbox_system_prompt",
        height=90,
    )
    edited_user_prompt = st.text_area(
        "User Prompt",
        value=default_user_prompt,
        height=120,
        key=f"debug_user_prompt_{current_item['id']}",
    )
    edited_system_prompt_text = str(edited_system_prompt or "")
    edited_user_prompt_text = str(edited_user_prompt or "")

    if st.button("重新生成", type="primary", width="stretch"):
        if not edited_user_prompt_text.strip():
            st.error("User Prompt 不能为空，请输入后再重新生成。")
        else:
            api_key = api_key_input.strip() or os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                st.error(
                    "未检测到 API Key。请输入 OpenAI API Key 或设置环境变量 OPENAI_API_KEY。"
                )
            else:
                try:
                    with st.spinner(f"正在使用模型 {model_name} 重新生成中..."):
                        result_text = _call_openai(
                            system_prompt=edited_system_prompt_text,
                            user_prompt=edited_user_prompt_text,
                            model_name=model_name,
                            api_key=api_key,
                            base_url=base_url,
                        )
                    if result_text is not None:
                        st.session_state[f"sandbox_result_{current_item['id']}"] = (
                            result_text
                        )
                        st.success("生成完成")
                except Exception as exc:
                    st.error(f"调用模型失败：{exc}")

    last_result = st.session_state.get(f"sandbox_result_{current_item['id']}", "")
    if last_result:
        st.text_area(
            "模型返回结果",
            value=last_result,
            height=120,
            disabled=True,
            key=f"sandbox_result_view_{current_item['id']}",
        )

    # System Prompt 模式下支持批量重跑任务
    if current_item.get("system_prompt"):
        st.markdown("### 批量重跑")
        st.caption(
            "使用当前沙盒中的 System Prompt，与全部样本的 user prompt 组合后批量调用 API。"
        )

        fail_indices = st.session_state.sandbox_batch_fail_indices

        # 操作按钮
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        with btn_col1:
            start_clicked = st.button(
                "批量重跑全部样本",
                width="stretch",
                disabled=st.session_state.sandbox_batch_running,
            )
        with btn_col2:
            stop_clicked = st.button(
                "中断任务",
                width="stretch",
                disabled=not st.session_state.sandbox_batch_running,
            )
        with btn_col3:
            retry_clicked = st.button(
                "失败样本重试",
                width="stretch",
                disabled=st.session_state.sandbox_batch_running
                or len(fail_indices) == 0,
            )

        api_key = api_key_input.strip() or os.getenv("OPENAI_API_KEY", "")

        if start_clicked:
            if not api_key:
                st.error(
                    "未检测到 API Key。请输入 OpenAI API Key 或设置环境变量 OPENAI_API_KEY。"
                )
            elif not edited_system_prompt_text.strip():
                st.error("System Prompt 不能为空。")
            else:
                queue = list(range(len(st.session_state.get("records", []))))
                _start_batch(
                    queue_indices=queue,
                    system_prompt=edited_system_prompt_text,
                    model_name=model_name,
                    api_key=api_key,
                    base_url=base_url,
                )
                st.session_state.sandbox_batch_message = "任务已启动，正在处理中..."
                st.rerun()

        if stop_clicked:
            st.session_state.sandbox_batch_stop_requested = True
            st.session_state.sandbox_batch_message = (
                "已请求中断，当前样本处理完成后停止。"
            )
            st.rerun()

        if retry_clicked:
            if not api_key:
                st.error(
                    "未检测到 API Key。请输入 OpenAI API Key 或设置环境变量 OPENAI_API_KEY。"
                )
            elif not edited_system_prompt_text.strip():
                st.error("System Prompt 不能为空。")
            else:
                _start_batch(
                    queue_indices=fail_indices,
                    system_prompt=edited_system_prompt_text,
                    model_name=model_name,
                    api_key=api_key,
                    base_url=base_url,
                )
                st.session_state.sandbox_batch_message = "失败样本重试任务已启动。"
                st.rerun()

        # 执行任务（每次渲染处理一条，支持中断）
        _process_batch_step()

        # 状态展示（放在处理步骤之后，确保数量与实际一致）
        total = int(st.session_state.sandbox_batch_total or 0)
        processed = int(st.session_state.sandbox_batch_processed or 0)
        if total > 0:
            safe_processed = processed if processed <= total else total
            st.progress(
                safe_processed / total, text=f"任务进度：{safe_processed}/{total}"
            )

        updated_fail_indices = st.session_state.sandbox_batch_fail_indices
        if updated_fail_indices:
            st.caption(f"失败样本数：{len(updated_fail_indices)}")

        if st.session_state.sandbox_batch_message:
            if st.session_state.sandbox_batch_status == "completed":
                st.success(st.session_state.sandbox_batch_message)
            elif st.session_state.sandbox_batch_status == "interrupted":
                st.warning(st.session_state.sandbox_batch_message)
            else:
                st.info(st.session_state.sandbox_batch_message)

        # 任务结束后提供下载
        if st.session_state.sandbox_batch_status in ["completed", "interrupted"]:
            if st.session_state.sandbox_batch_status == "completed" and hasattr(
                st, "toast"
            ):
                st.toast("批量任务已完成")
            _render_batch_export()

    _ = edited_user_prompt_text
