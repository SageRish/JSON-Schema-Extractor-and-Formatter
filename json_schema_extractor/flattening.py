from __future__ import annotations

import json
from typing import Any, Dict, List

from .records import resolve_field_value, resolve_groups_for_merge


def flatten_data_for_export(
    data: Any,
    selected_fields: List[str],
    mapping: Dict[str, str],
    root_path: str = '(root)',
) -> List[Dict[str, Any]]:
    """Flatten data into list[dict] for export."""
    rows: List[Dict[str, Any]] = []

    # Iterate records (not groups) even for list[list[dict]] roots.
    groups, _ = resolve_groups_for_merge(data, root_path)
    records = [rec for group in groups for rec in group]

    for record in records:
        row: Dict[str, Any] = {}
        for field in selected_fields:
            val = resolve_field_value(data, record, field, root_path)

            if isinstance(val, list):
                if all(isinstance(v, (str, int, float, bool)) or v is None for v in val):
                    val = ", ".join(["" if v is None else str(v) for v in val])
                else:
                    try:
                        val = json.dumps(val, ensure_ascii=False)
                    except TypeError:
                        val = str(val)

            out_name = mapping.get(field, field)
            row[out_name] = val
        rows.append(row)

    return rows


def flatten_data_for_preview(
    data: Any,
    selected_fields: List[str],
    mapping: Dict[str, str],
    root_path: str = '(root)',
    limit: int = 3,
) -> List[Dict[str, Any]]:
    if data is None or not selected_fields:
        return []

    rows: List[Dict[str, Any]] = []
    groups, _ = resolve_groups_for_merge(data, root_path)
    for group in groups:
        for record in group:
            row: Dict[str, Any] = {}
            for field in selected_fields:
                val = resolve_field_value(data, record, field, root_path)
                if isinstance(val, list):
                    if all(isinstance(v, (str, int, float, bool)) or v is None for v in val):
                        val = ", ".join(["" if v is None else str(v) for v in val])
                    else:
                        try:
                            val = json.dumps(val, ensure_ascii=False)
                        except TypeError:
                            val = str(val)
                out_name = mapping.get(field, field)
                row[out_name] = val
            rows.append(row)
            if len(rows) >= max(1, int(limit)):
                return rows
    return rows
