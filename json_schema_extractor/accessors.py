from __future__ import annotations

from typing import Any

from .paths import split_path


def get_value_by_path(data: Any, path: str, sep: str = '.') -> Any:
    """Retrieve value from nested data using a dot-notation path.

    Handles nested lists by collecting all matching values.
    """
    keys = split_path(path)
    val = data

    def collect_values(container, key):
        results = []
        if isinstance(container, dict):
            v = container.get(key, None)
            if v is not None:
                results.append(v)
        elif isinstance(container, list):
            for item in container:
                results.extend(collect_values(item, key))
        return results

    try:
        i = 0
        while i < len(keys):
            key = keys[i]

            if isinstance(val, dict):
                if key in val:
                    val = val.get(key)
                    i += 1
                else:
                    # Fallback for unescaped dotted dict keys (e.g. 'gpt-3.5-turbo')
                    # when the incoming path is 'responses.gpt-3.5-turbo.response'.
                    matched = False
                    if i + 1 < len(keys):
                        candidate = key
                        for j in range(i + 1, len(keys)):
                            candidate = candidate + '.' + keys[j]
                            if candidate in val:
                                val = val.get(candidate)
                                i = j + 1
                                matched = True
                                break
                    if not matched:
                        return None

            elif isinstance(val, list):
                # If we are at a list, we "broadcast" the key access and collect.
                val = collect_values(val, key)
                i += 1
                if not val:
                    return None
            else:
                return None

            if val is None:
                return None

        return val
    except Exception:
        return None


def set_value_by_path(data: Any, path: str, value: Any, sep: str = '.'):
    """Set a value in a nested dict by dot path (dict-only traversal)."""
    if path in (None, '', '(root)'):
        return value

    if not isinstance(data, dict):
        return value

    parts = split_path(path)
    current = data
    for part in parts[:-1]:
        nxt = current.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            current[part] = nxt
        current = nxt
    current[parts[-1]] = value
    return data
