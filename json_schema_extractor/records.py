from __future__ import annotations

from typing import Any, Dict, List, Set

from .accessors import get_value_by_path
from .schema_utils import extract_all_keys


def resolve_items_by_root(data: Any, root_path: str = '(root)') -> List[Any]:
    if data is None:
        return []

    if root_path in (None, '', '(root)'):
        if isinstance(data, list):
            return data
        return [data]

    target = get_value_by_path(data, root_path)
    if isinstance(target, list):
        return target
    if target is not None:
        return [target]
    return []


def resolve_groups_for_merge(data: Any, root_path: str = '(root)'):
    """Resolve selected root into a list of record-groups.

    Supports datasets where the root points to:
    - list[dict] (not grouped)  -> one group containing all dicts
    - list[list[dict]] (grouped) -> one group per inner list
    - dict (single record) -> one group with one record
    """
    items = resolve_items_by_root(data, root_path)
    grouped = False
    groups: List[List[Dict[str, Any]]] = []

    for entry in items:
        if isinstance(entry, list):
            grouped = True
            group = [x for x in entry if isinstance(x, dict)]
            groups.append(group)
        elif isinstance(entry, dict):
            groups.append([entry])
        else:
            continue

    # If root itself is a list[dict], the loop above creates one group per dict.
    # Collapse that into a single group to preserve the original list shape.
    if not grouped and groups:
        flat: List[Dict[str, Any]] = [rec for g in groups for rec in g]
        groups = [flat]

    return groups, grouped


def resolve_field_value(data: Any, item: Any, field_path: str, root_path: str):
    if root_path in (None, '', '(root)'):
        return get_value_by_path(item, field_path)

    prefix = f"{root_path}."
    if field_path == root_path:
        return item
    if field_path.startswith(prefix):
        rel_path = field_path[len(prefix):]
        return get_value_by_path(item, rel_path)
    return get_value_by_path(data, field_path)


def extract_record_keys(data: Any, root_path: str, sample_size: int = 50) -> List[str]:
    """Extract dot-path keys relative to items under the selected root."""
    groups, _ = resolve_groups_for_merge(data, root_path)
    keys: Set[str] = set()
    remaining = max(0, int(sample_size))
    for group in groups:
        for record in group:
            keys.update(extract_all_keys(record))
            remaining -= 1
            if remaining <= 0:
                return sorted(keys)
    return sorted(keys)
