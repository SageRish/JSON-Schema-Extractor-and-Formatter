from __future__ import annotations

import csv
import json
import os
import tempfile
from typing import Any, Dict, List

import gradio as gr

from .flattening import flatten_data_for_export, flatten_data_for_preview
from .io_utils import read_json_content
from .paths import split_path
from .records import resolve_groups_for_merge
from .schema_utils import extract_all_keys, find_list_paths


def prepare_dataset_payload(file_obj):
    if file_obj is None:
        return None, [], gr.update(choices=[]), "No file uploaded."

    try:
        data = read_json_content(file_obj)
    except Exception as e:
        return None, [], gr.update(choices=[]), f"Error parsing JSON: {str(e)}"

    all_keys = sorted(list(extract_all_keys(data)))
    list_paths = find_list_paths(data)
    if not list_paths:
        list_paths = ["(root)"]

    default_root = "(root)" if "(root)" in list_paths else (list_paths[0] if list_paths else "(root)")
    return data, all_keys, gr.update(choices=list_paths, value=default_root), f"Successfully loaded. Found {len(all_keys)} unique fields."


def load_and_parse_json(file_obj):
    data, _, root_dropdown, message = prepare_dataset_payload(file_obj)
    if data is None:
        return None, [], root_dropdown, message
    return data, [], root_dropdown, message


def compute_document_count_text(data: Any, root_path: str = '(root)') -> str:
    if data is None:
        return ""
    try:
        groups, grouped = resolve_groups_for_merge(data, root_path or '(root)')
        record_count = sum(len(g) for g in groups)
        if grouped:
            return f"Documents: {record_count} (groups: {len(groups)})"
        return f"Documents: {record_count}"
    except Exception:
        return ""


def load_and_parse_json_with_preview(file_obj):
    data, _, root_dropdown, message = prepare_dataset_payload(file_obj)
    if data is None:
        return None, [], root_dropdown, message, [], None, ""

    count_text = compute_document_count_text(
        data,
        root_dropdown.get("value") if isinstance(root_dropdown, dict) else "(root)",
    )
    return data, [], root_dropdown, message, [], None, count_text


def handle_root_change_single_dataset(data: Any, root_path: str, mapping_df):
    return compute_document_count_text(data, root_path or '(root)'), None


def update_mapping_table(selected_fields):
    if not selected_fields:
        return []
    def default_output_name(path: str) -> str:
        parts = split_path(path)
        return parts[-1] if parts else (path or "")

    return [[f, default_output_name(f)] for f in selected_fields]


def update_mapping_table_and_clear_preview(selected_fields):
    return update_mapping_table(selected_fields), None


def update_mapping_table_and_preview(selected_fields, data, root_path):
    table = update_mapping_table(selected_fields)
    if data is None or not table:
        return table, None
    mapping = {row[0]: row[1] for row in table}
    fields = [row[0] for row in table]
    preview_rows = flatten_data_for_preview(data, fields, mapping, root_path or '(root)', limit=3)
    return table, preview_rows if preview_rows else None


def export_data_handler(data, mapping_df, output_format, file_name, root_path=None):
    if data is None:
        return None, "No data loaded."

    if mapping_df is None or mapping_df.empty:
        return None, "No fields selected."

    if root_path is None:
        root_path = "(root)"

    try:
        mapping = dict(zip(mapping_df["Input Path"], mapping_df["Output Name"]))
        selected_fields = mapping_df["Input Path"].tolist()
    except Exception:
        mapping = {row[0]: row[1] for row in mapping_df}
        selected_fields = [row[0] for row in mapping_df]

    if not selected_fields:
        return None, "No fields selected."

    processed_rows = flatten_data_for_export(data, selected_fields, mapping, root_path)

    if not file_name or not file_name.strip():
        file_name = "output"

    ext = f".{output_format.lower()}"
    if not file_name.lower().endswith(ext):
        file_name += ext

    temp_dir = tempfile.gettempdir()
    path = os.path.join(temp_dir, file_name)

    try:
        if output_format == "CSV":
            headers = [mapping.get(f, f) for f in selected_fields]
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                if processed_rows:
                    writer.writerows(processed_rows)
        else:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(processed_rows, f, indent=2)

        return path, f"Export successful! Saved to {path}"
    except Exception as e:
        return None, f"Error during export: {str(e)}"


def preview_single_dataset_handler(data, mapping_df, root_path=None):
    if data is None or mapping_df is None:
        return None
    if root_path is None:
        root_path = "(root)"

    try:
        mapping = dict(zip(mapping_df["Input Path"], mapping_df["Output Name"]))
        selected_fields = mapping_df["Input Path"].tolist()
    except Exception:
        try:
            mapping = {row[0]: row[1] for row in mapping_df}
            selected_fields = [row[0] for row in mapping_df]
        except Exception:
            return None

    if not selected_fields:
        return None

    preview_rows = flatten_data_for_preview(data, selected_fields, mapping, root_path, limit=3)
    return preview_rows if preview_rows else None
