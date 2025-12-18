from __future__ import annotations

from typing import Any, Dict, List, Set

from .paths import escape_path_segment, split_path


def build_tree_from_keys(keys: List[str]) -> Dict[str, Any]:
    """Convert dot-notation keys into a nested dictionary tree.

    Leaf nodes are strings (the full path).
    Branch nodes are dictionaries.
    If a node is both a leaf and a branch (e.g. 'a' and 'a.b'),
    the value for 'a' is stored in the dictionary under '__self__'.
    """
    tree: Dict[str, Any] = {}
    for key in sorted(keys):
        parts = split_path(key)
        if not parts:
            continue
        current = tree
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}

            # If we encounter a node that was previously a leaf, convert it to a dict
            if isinstance(current[part], str):
                current[part] = {'__self__': current[part]}

            current = current[part]

        last_part = parts[-1]
        if last_part in current:
            # If it's already a dict, add self
            if isinstance(current[last_part], dict):
                current[last_part]['__self__'] = key
        else:
            current[last_part] = key
    return tree


def extract_all_keys(data: Any, parent_key: str = '', sep: str = '.') -> Set[str]:
    """Recursively find all possible keys in a JSON structure (dict or list of dicts)."""
    keys: Set[str] = set()

    if isinstance(data, dict):
        for k, v in data.items():
            escaped_k = escape_path_segment(k)
            current_key = f"{parent_key}{sep}{escaped_k}" if parent_key else escaped_k
            if isinstance(v, (dict, list)):
                keys.update(extract_all_keys(v, current_key, sep))
            else:
                keys.add(current_key)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                keys.update(extract_all_keys(item, parent_key, sep))
            else:
                if parent_key:
                    keys.add(parent_key)
    else:
        if parent_key:
            keys.add(parent_key)

    return keys


def find_list_paths(data: Any, parent_key: str = '', sep: str = '.') -> List[str]:
    """Find all paths in the JSON that point to a list."""
    paths: List[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            escaped_k = escape_path_segment(k)
            current_key = f"{parent_key}{sep}{escaped_k}" if parent_key else escaped_k
            if isinstance(v, list):
                paths.append(current_key)
                if v and isinstance(v[0], dict):
                    paths.extend(find_list_paths(v[0], current_key, sep))
            elif isinstance(v, dict):
                paths.extend(find_list_paths(v, current_key, sep))
    elif isinstance(data, list):
        if not parent_key:
            paths.append("(root)")
            if data and isinstance(data[0], dict):
                paths.extend(find_list_paths(data[0], "", sep))
    return sorted(paths)
