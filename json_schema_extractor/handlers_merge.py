from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from typing import Any, Dict, List
from uuid import uuid4

import gradio as gr

from .accessors import get_value_by_path
from .accessors import set_value_by_path
from .io_utils import read_json_content
from .records import extract_record_keys, resolve_groups_for_merge
from .schema_utils import find_list_paths


def update_join_key_dropdown(primary_keys, secondary_keys, current_selection):
    primary_keys = primary_keys or []
    secondary_keys = secondary_keys or []
    common = sorted(list(set(primary_keys) & set(secondary_keys)))

    if not common:
        return gr.update(choices=[], value=[], interactive=False)

    if current_selection is None:
        current_selection = []
    if isinstance(current_selection, str):
        current_selection = [current_selection]

    retained = [k for k in current_selection if k in common]
    value = retained if retained else [common[0]]
    return gr.update(choices=common, value=value, interactive=True)


def normalize_key_component(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, sort_keys=True)
        except TypeError:
            return str(value)
    return value


def build_join_key_tuple(item, join_paths):
    return tuple(normalize_key_component(get_value_by_path(item, path)) for path in join_paths)


def build_merged_record(primary_record, secondary_record):
    merged: Dict[str, Any] = {}
    if primary_record is not None and isinstance(primary_record, dict):
        merged = deepcopy(primary_record)
    elif secondary_record is not None and isinstance(secondary_record, dict):
        merged = deepcopy(secondary_record)

    if secondary_record is not None and isinstance(secondary_record, dict):
        for key, value in secondary_record.items():
            if key not in merged or merged.get(key) is None:
                merged[key] = deepcopy(value)

    return merged


def perform_dataset_merge(primary_data, secondary_data, primary_root, secondary_root, join_keys):
    if primary_data is None or secondary_data is None:
        raise ValueError("Upload both datasets before merging.")

    if not join_keys:
        raise ValueError("Select at least one join key.")

    join_keys = [k for k in join_keys if k]
    if not join_keys:
        raise ValueError("Select valid join keys.")

    primary_groups, primary_grouped = resolve_groups_for_merge(primary_data, primary_root)
    secondary_groups, _ = resolve_groups_for_merge(secondary_data, secondary_root)
    primary_records = [rec for group in primary_groups for rec in group]
    secondary_records = [rec for group in secondary_groups for rec in group]

    if not primary_records:
        raise ValueError("Primary dataset has no iterable items for the selected root path.")
    if not secondary_records:
        raise ValueError("Secondary dataset has no iterable items for the selected root path.")

    secondary_index = {}
    for idx, item in enumerate(secondary_records):
        key = build_join_key_tuple(item, join_keys)
        secondary_index.setdefault(key, []).append(idx)

    merged_rows: List[Dict[str, Any]] = []
    merged_groups: List[List[Dict[str, Any]]] = [[] for _ in range(len(primary_groups))] if primary_grouped else []
    matched_secondary = set()
    match_pairs = 0
    primary_only = 0

    for group_idx, group in enumerate(primary_groups):
        for item in group:
            key = build_join_key_tuple(item, join_keys)
            matches = secondary_index.get(key, [])
            if matches:
                for idx in matches:
                    merged = build_merged_record(item, secondary_records[idx])
                    if primary_grouped:
                        merged_groups[group_idx].append(merged)
                    else:
                        merged_rows.append(merged)
                    matched_secondary.add(idx)
                    match_pairs += 1
            else:
                primary_only += 1

    stats = {
        'primary_total': len(primary_records),
        'secondary_total': len(secondary_records),
        'match_pairs': match_pairs,
        'primary_only': primary_only,
        'secondary_only': len(secondary_records) - len(matched_secondary),
    }
    merged_payload = merged_groups if primary_grouped else merged_rows
    return merged_payload, stats


def build_merged_output_container(primary_data, primary_root, merged_items):
    if primary_root in (None, '', '(root)'):
        return merged_items

    if isinstance(primary_data, dict):
        output = deepcopy(primary_data)
        return set_value_by_path(output, primary_root, merged_items)

    return merged_items


def merge_datasets_handler(primary_data, secondary_data, primary_root, secondary_root, join_keys, file_name):
    join_keys = join_keys or []
    if isinstance(join_keys, str):
        join_keys = [join_keys]

    try:
        merged_payload, stats = perform_dataset_merge(
            primary_data,
            secondary_data,
            primary_root or '(root)',
            secondary_root or '(root)',
            join_keys,
        )
    except ValueError as exc:
        return None, str(exc), None

    if not merged_payload:
        return None, "Merge produced no rows.", None

    merged_output = build_merged_output_container(primary_data, primary_root or '(root)', merged_payload)

    output_name = (file_name or f"merged_{uuid4().hex}").strip()
    if not output_name.lower().endswith('.json'):
        output_name += '.json'

    temp_dir = tempfile.gettempdir()
    path = os.path.join(temp_dir, output_name)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(merged_output, f, indent=2)
    except Exception as exc:
        return None, f"Error writing merged file: {str(exc)}", None

    if isinstance(merged_payload, list) and merged_payload and isinstance(merged_payload[0], list):
        flat_preview = [rec for group in merged_payload for rec in group][:3]
    elif isinstance(merged_payload, list):
        flat_preview = merged_payload[:3]
    else:
        flat_preview = None

    summary = (
        f"Matches: {stats['match_pairs']} | "
        f"Primary rows: {stats['primary_total']} (unmatched {stats['primary_only']}) | "
        f"Secondary rows: {stats['secondary_total']} (unmatched {stats['secondary_only']})."
    )

    return path, summary, flat_preview


def handle_merge_dataset_upload(file_obj, other_keys, current_selection, label_prefix):
    if file_obj is None:
        return None, [], gr.update(choices=["(root)"], value="(root)"), f"{label_prefix}: No file uploaded.", gr.update(choices=[], value=[], interactive=False)

    try:
        data = read_json_content(file_obj)
    except Exception as e:
        return None, [], gr.update(choices=["(root)"], value="(root)"), f"{label_prefix}: Error parsing JSON: {str(e)}", gr.update(choices=[], value=[], interactive=False)

    list_paths = find_list_paths(data)
    if not list_paths:
        list_paths = ["(root)"]
    default_root = "(root)" if "(root)" in list_paths else list_paths[0]
    root_dropdown = gr.update(choices=list_paths, value=default_root)

    keys = extract_record_keys(data, default_root)
    status_message = f"{label_prefix}: Successfully loaded. Found {len(keys)} record fields."
    join_update = update_join_key_dropdown(keys, other_keys, current_selection)
    return data, keys, root_dropdown, status_message, join_update


def handle_primary_dataset_upload(file_obj, secondary_keys, current_selection):
    secondary_keys = secondary_keys or []
    return handle_merge_dataset_upload(file_obj, secondary_keys, current_selection, "Primary dataset")


def handle_secondary_dataset_upload(file_obj, primary_keys, current_selection):
    primary_keys = primary_keys or []
    return handle_merge_dataset_upload(file_obj, primary_keys, current_selection, "Secondary dataset")


def handle_primary_root_change(primary_data, primary_root, secondary_keys, current_selection):
    keys = extract_record_keys(primary_data, primary_root)
    return keys, update_join_key_dropdown(keys, secondary_keys, current_selection)


def handle_secondary_root_change(secondary_data, secondary_root, primary_keys, current_selection):
    keys = extract_record_keys(secondary_data, secondary_root)
    return keys, update_join_key_dropdown(primary_keys, keys, current_selection)
