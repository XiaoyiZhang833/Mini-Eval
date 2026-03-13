import streamlit as st


def read_excel_file(uploaded_file):
    """读取 Excel 为 DataFrame。"""
    try:
        import pandas as pd
    except ImportError:
        st.error(
            "当前环境未安装 pandas，无法读取 Excel。请先执行：pip install pandas openpyxl"
        )
        return None

    try:
        df = pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"Excel 读取失败，请检查文件格式是否正确：{exc}")
        return None

    if df is None or df.empty or len(df.columns) == 0:
        st.error("Excel 中没有可用数据或表头，请检查文件内容。")
        return None

    return df


def build_records_from_mapping(df, prompt_column, output_columns):
    """根据用户选择的字段映射构建评测记录。支持多个 Output 列。"""
    if isinstance(output_columns, str):
        output_columns = [output_columns]

    output_columns = [col for col in output_columns if col in df.columns]
    if prompt_column not in df.columns or not output_columns:
        st.error("字段映射无效，请重新选择。")
        return None

    if prompt_column in output_columns:
        st.error("Prompt 字段不能同时作为 Output 字段，请重新选择。")
        return None

    mapped_df = df[[prompt_column] + output_columns].rename(
        columns={prompt_column: "prompt"}
    )

    def _is_empty(value) -> bool:
        text = str(value).strip()
        return value is None or text == "" or text.lower() == "nan"

    records = []
    for _, row in mapped_df.iterrows():
        prompt_text = str(row.get("prompt", "")).strip()
        if _is_empty(prompt_text):
            continue

        outputs = []
        output_labels = []
        for col in output_columns:
            value = row.get(col, "")
            if not _is_empty(value):
                outputs.append(str(value).strip())
                output_labels.append(str(col))

        if not outputs:
            continue

        if len(outputs) == 1:
            output_text = outputs[0]
        else:
            output_text = " || ".join(outputs)

        records.append(
            {
                "prompt": prompt_text,
                "output": output_text,
                "output_list": outputs,
                "output_labels": output_labels,
            }
        )

    if not records:
        st.warning("导入后没有可用数据，请检查 prompt/output 是否为空。")
        return None

    for idx, item in enumerate(records, start=1):
        item["id"] = str(idx)

    return records
