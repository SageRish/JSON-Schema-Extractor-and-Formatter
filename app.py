import gradio as gr
import json
import csv
import os
import tempfile
from typing import List, Dict, Any, Set
from functools import partial
from copy import deepcopy
from uuid import uuid4


def escape_path_segment(segment: str) -> str:
    """Escape a single key segment for dot-path representation.

    - Dots are escaped as '\\.' so keys like 'gpt-3.5-turbo' remain one segment.
    - Backslashes are escaped as '\\\\' to preserve round-tripping.
    """
    if not isinstance(segment, str):
        segment = str(segment)
    return segment.replace('\\', '\\\\').replace('.', '\\.')


def unescape_path_segment(segment: str) -> str:
    if segment is None:
        return ''
    out: List[str] = []
    i = 0
    while i < len(segment):
        ch = segment[i]
        if ch == '\\' and i + 1 < len(segment):
            out.append(segment[i + 1])
            i += 2
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def split_path(path: str) -> List[str]:
    """Split a dot path on unescaped '.' and unescape each segment."""
    if path is None:
        return []
    if not isinstance(path, str):
        path = str(path)

    parts: List[str] = []
    buf: List[str] = []
    escaping = False

    for ch in path:
        if escaping:
            # Keep the escape pair so unescape_path_segment can process it.
            buf.append('\\')
            buf.append(ch)
            escaping = False
            continue

        if ch == '\\':
            escaping = True
            continue
        if ch == '.':
            parts.append(unescape_path_segment(''.join(buf)))
            buf = []
            continue
        buf.append(ch)

    if escaping:
        # Trailing backslash; treat as literal.
        buf.append('\\')

    parts.append(unescape_path_segment(''.join(buf)))
    return [p for p in parts if p != '']


def read_json_content(file_obj):
    """Read JSON content from an uploaded file or file path."""
    if file_obj is None:
        raise ValueError("No file uploaded.")

    if hasattr(file_obj, 'read'):
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        content = file_obj.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        return json.loads(content)

    path = file_obj.name if hasattr(file_obj, 'name') else file_obj
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def build_tree_from_keys(keys: List[str]) -> Dict[str, Any]:
    """
    Convert a list of dot-notation keys into a nested dictionary tree.
    Leaf nodes are strings (the full path).
    Branch nodes are dictionaries.
    If a node is both a leaf and a branch (e.g. 'a' and 'a.b'), 
    the value for 'a' is stored in the dictionary under '__self__'.
    """
    tree = {}
    for key in sorted(keys):
        parts = split_path(key)
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

def flatten_json(y: Any, parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """
    Flatten a nested json object.
    """
    out = {}

    def _flatten(x: Any, name: str = ''):
        if isinstance(x, dict):
            for a in x:
                _flatten(x[a], name + escape_path_segment(a) + sep)
        elif isinstance(x, list):
            # For lists, we can either index them or just treat them as a value if they are primitives.
            # If it's a list of objects, we might want to explore the first one or all of them.
            # For this generic tool, let's treat list indices as keys.
            for i, a in enumerate(x):
                _flatten(a, name + str(i) + sep)
        else:
            out[name[:-1]] = x

    _flatten(y, parent_key)
    return out

def extract_all_keys(data: Any, parent_key: str = '', sep: str = '.') -> Set[str]:
    """
    Recursively find all possible keys in a JSON structure (dict or list of dicts).
    """
    keys = set()

    if isinstance(data, dict):
        for k, v in data.items():
            escaped_k = escape_path_segment(k)
            current_key = f"{parent_key}{sep}{escaped_k}" if parent_key else escaped_k
            if isinstance(v, (dict, list)):
                keys.update(extract_all_keys(v, current_key, sep))
            else:
                keys.add(current_key)
    elif isinstance(data, list):
        # If it's a list, we assume it might be a list of records.
        # We want to find unique keys across items if they are dicts.
        # Or if it's a list of primitives, we might not want to index every single one.
        # Strategy: If list of dicts, union of keys. If list of primitives, ignore or treat as parent.
        for item in data:
            if isinstance(item, (dict, list)):
                keys.update(extract_all_keys(item, parent_key, sep))
            else:
                # It's a primitive in a list, e.g. tags: ["a", "b"]
                # We can't really select "tags.0", "tags.1" generically if the list length varies.
                # We'll just add the parent key itself as a selectable field.
                if parent_key:
                    keys.add(parent_key)
    else:
        if parent_key:
            keys.add(parent_key)
            
    return keys

def get_value_by_path(data: Any, path: str, sep: str = '.') -> Any:
    """
    Retrieve value from nested data using a dot-notation path.
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

def find_list_paths(data: Any, parent_key: str = '', sep: str = '.') -> List[str]:
    """
    Find all paths in the JSON that point to a list.
    """
    paths = []
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


def load_and_parse_json_with_preview(file_obj):
    data, _, root_dropdown, message = prepare_dataset_payload(file_obj)
    # On new upload, clear selected fields, mapping table, and preview.
    if data is None:
        return None, [], root_dropdown, message, [], None, ""

    count_text = compute_document_count_text(data, root_dropdown.get("value") if isinstance(root_dropdown, dict) else "(root)")
    return data, [], root_dropdown, message, [], None, count_text


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


def handle_root_change_single_dataset(data: Any, root_path: str, mapping_df):
    # Root path changes affect the iteration unit; clear preview to avoid stale output.
    return compute_document_count_text(data, root_path or '(root)'), None


def update_mapping_table_and_clear_preview(selected_fields):
    return update_mapping_table(selected_fields), None

def update_mapping_table(selected_fields):
    # Create a list of lists for the dataframe: [Input Path, Output Name]
    # Default Output Name is the same as Input Path
    if not selected_fields:
        return []
    return [[f, f] for f in selected_fields]


def update_mapping_table_and_preview(selected_fields, data, root_path):
    table = update_mapping_table(selected_fields)
    if data is None or not table:
        return table, None
    mapping = {row[0]: row[1] for row in table}
    fields = [row[0] for row in table]
    preview_rows = flatten_data_for_preview(data, fields, mapping, root_path or '(root)', limit=3)
    return table, preview_rows if preview_rows else None


def extract_record_keys(data: Any, root_path: str, sample_size: int = 50) -> List[str]:
    """Extract dot-path keys relative to items under the selected root.

    This is intentionally different from extract_all_keys(data): for merging, we
    want join keys like 'question' rather than 'data.question' when root is 'data'.
    """
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


def resolve_groups_for_merge(data: Any, root_path: str = '(root)'):
    """Resolve the selected root into a list of record-groups.

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
            # Ignore primitives
            continue

    # If root itself is a list[dict], the loop above creates one group per dict.
    # Collapse that into a single group to preserve the original list shape.
    if not grouped and groups:
        flat: List[Dict[str, Any]] = [rec for g in groups for rec in g]
        groups = [flat]

    return groups, grouped


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


def flatten_data_for_export(data: Any, selected_fields: List[str], mapping: Dict[str, str], root_path: str = '(root)') -> List[Dict[str, Any]]:
    """
    Flattens the data into a list of dictionaries based on selected fields and root path.
    """
    rows: List[Dict[str, Any]] = []

    # Use the same group-aware root resolution as merges so we iterate records,
    # not groups. This prevents values like `data.question` from becoming a list
    # (and then being joined into one string) when the root is list[list[dict]].
    groups, _ = resolve_groups_for_merge(data, root_path)
    records = [rec for group in groups for rec in group]

    for record in records:
        row: Dict[str, Any] = {}
        for field in selected_fields:
            val = resolve_field_value(data, record, field, root_path)

            # Handle lists in values (e.g. tags: ["a", "b"]) -> join primitives.
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


def flatten_data_for_preview(data: Any, selected_fields: List[str], mapping: Dict[str, str], root_path: str = '(root)', limit: int = 3) -> List[Dict[str, Any]]:
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

def export_data_handler(data, mapping_df, output_format, file_name, root_path=None):
    if data is None:
        return None, "No data loaded."
    
    if mapping_df is None or mapping_df.empty:
        return None, "No fields selected."
    
    if root_path is None:
        root_path = "(root)"

    # Convert dataframe to dict mapping
    try:
        # If it's a dataframe
        mapping = dict(zip(mapping_df["Input Path"], mapping_df["Output Name"]))
        selected_fields = mapping_df["Input Path"].tolist()
    except:
        # If it's a list of lists
        mapping = {row[0]: row[1] for row in mapping_df}
        selected_fields = [row[0] for row in mapping_df]

    if not selected_fields:
        return None, "No fields selected."

    processed_rows = flatten_data_for_export(data, selected_fields, mapping, root_path)
    
    # Determine filename
    if not file_name or not file_name.strip():
        file_name = "output"
    
    # Ensure extension matches format
    ext = f".{output_format.lower()}"
    if not file_name.lower().endswith(ext):
        file_name += ext
        
    # Create file in temp dir
    temp_dir = tempfile.gettempdir()
    path = os.path.join(temp_dir, file_name)
    
    try:
        if output_format == "CSV":
            # Always write headers even if no data
            headers = [mapping.get(f, f) for f in selected_fields]
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                if processed_rows:
                    writer.writerows(processed_rows)
        else: # JSON
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
    # Merge join keys are treated as relative to the current record (item)
    # to avoid root-path prefix mismatches like 'data.question' vs 'question'.
    return tuple(normalize_key_component(get_value_by_path(item, path)) for path in join_paths)


def build_merged_record(primary_record, secondary_record):
    # Flat merged record: union of fields.
    # Prefer primary values; fill missing/None from secondary.
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

    # Inner join only (focused workflow)

    secondary_index = {}
    for idx, item in enumerate(secondary_records):
        key = build_join_key_tuple(item, join_keys)
        secondary_index.setdefault(key, []).append(idx)

    merged_rows: List[Dict[str, Any]] = []
    merged_groups: List[List[Dict[str, Any]]] = [[] for _ in range(len(primary_groups))] if primary_grouped else []
    matched_secondary = set()
    match_pairs = 0
    primary_only = 0
    secondary_only = 0

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
        'secondary_only': secondary_only,
    }
    merged_payload = merged_groups if primary_grouped else merged_rows
    return merged_payload, stats


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


def build_merged_output_container(primary_data, primary_root, merged_items):
    """Preserve primary JSON structure by replacing the primary root list with merged items."""
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

    preview = flat_preview
    summary = (
        f"Matches: {stats['match_pairs']} | "
        f"Primary rows: {stats['primary_total']} (unmatched {stats['primary_only']}) | "
        f"Secondary rows: {stats['secondary_total']} (unmatched {stats['secondary_only']})."
    )

    return path, summary, preview


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

# --- UI Definition ---
with gr.Blocks(title="JSON Schema Extractor") as demo:
    gr.Markdown("# JSON Schema Extractor and Converter")
    gr.Markdown("Upload JSON files, explore their schemas, and optionally merge datasets on shared keys.")

    # State
    json_data_state = gr.State()
    selected_fields_state = gr.State(value=[])
    merge_primary_data_state = gr.State()
    merge_secondary_data_state = gr.State()
    merge_primary_keys_state = gr.State(value=[])
    merge_secondary_keys_state = gr.State(value=[])

    with gr.Tab("Single Dataset"):
        with gr.Row():
            # Left Panel: Input & Schema
            with gr.Column(scale=1):
                gr.Markdown("### 1. Import")
                file_input = gr.File(label="Upload JSON File", file_types=[".json"])
                status_msg = gr.Textbox(label="Status", interactive=False)

                gr.Markdown("### 2. Select Fields")

                @gr.render(inputs=[json_data_state], triggers=[json_data_state.change])
                def render_schema(data):
                    if data is None:
                        gr.Markdown("No data loaded.")
                        return

                    all_keys = sorted(list(extract_all_keys(data)))
                    tree = build_tree_from_keys(all_keys)

                    def on_change(path, is_selected, current_selected):
                        if is_selected:
                            if path not in current_selected:
                                current_selected.append(path)
                        else:
                            if path in current_selected:
                                current_selected.remove(path)
                        return current_selected

                    def recursive_ui(node, label="root"):
                        if isinstance(node, dict):
                            if "__self__" in node:
                                full_path = node["__self__"]
                                cb = gr.Checkbox(label=f"{label} (value)", value=False)
                                cb.change(fn=partial(on_change, full_path), inputs=[cb, selected_fields_state], outputs=[selected_fields_state])

                            with gr.Accordion(label, open=False):
                                for k, v in node.items():
                                    if k == "__self__":
                                        continue
                                    recursive_ui(v, k)
                        else:
                            full_path = node
                            cb = gr.Checkbox(label=label, value=False)
                            cb.change(fn=partial(on_change, full_path), inputs=[cb, selected_fields_state], outputs=[selected_fields_state])

                    for k, v in tree.items():
                        recursive_ui(v, k)

            # Right Panel: Output Builder
            with gr.Column(scale=1):
                gr.Markdown("### 3. Output Builder")
                output_format = gr.Radio(choices=["CSV", "JSON"], value="CSV", label="Output Format")

                root_path_selector = gr.Dropdown(
                    label="Data Root Path (for iteration)",
                    choices=["(root)"],
                    value="(root)",
                    allow_custom_value=True,
                    interactive=True,
                )

                gr.Markdown("### 4. Field Mapping")
                gr.Markdown("Rename output columns if needed.")
                mapping_table = gr.Dataframe(
                    headers=["Input Path", "Output Name"],
                    datatype=["str", "str"],
                    col_count=(2, "fixed"),
                    interactive=True,
                    label="Field Mapping",
                )

                gr.Markdown("### 5. Export")
                output_filename = gr.Textbox(label="Output Filename (optional)", placeholder="output")
                document_count = gr.Textbox(label="Document Count", interactive=False)
                load_preview_btn = gr.Button("Load Preview")
                export_btn = gr.Button("Export Data", variant="primary")
                download_output = gr.File(label="Download Result")
                single_preview = gr.JSON(label="Preview (first 3 rows)")

        file_input.upload(
            fn=load_and_parse_json_with_preview,
            inputs=[file_input],
            outputs=[json_data_state, selected_fields_state, root_path_selector, status_msg, mapping_table, single_preview, document_count],
        )

        selected_fields_state.change(
            fn=update_mapping_table_and_clear_preview,
            inputs=[selected_fields_state],
            outputs=[mapping_table, single_preview],
        )

        root_path_selector.change(
            fn=handle_root_change_single_dataset,
            inputs=[json_data_state, root_path_selector, mapping_table],
            outputs=[document_count, single_preview],
        )

        load_preview_btn.click(
            fn=preview_single_dataset_handler,
            inputs=[json_data_state, mapping_table, root_path_selector],
            outputs=[single_preview],
        )

        export_btn.click(
            fn=export_data_handler,
            inputs=[json_data_state, mapping_table, output_format, output_filename, root_path_selector],
            outputs=[download_output, status_msg],
        )

    with gr.Tab("Merge Datasets"):
        gr.Markdown("### 1. Upload both datasets")
        with gr.Row():
            with gr.Column():
                primary_merge_file = gr.File(label="Primary Dataset", file_types=[".json"])
                primary_status = gr.Textbox(label="Primary Status", interactive=False)
                primary_root_selector = gr.Dropdown(
                    label="Primary Root Path",
                    choices=["(root)"],
                    value="(root)",
                    allow_custom_value=True,
                    interactive=True,
                )
            with gr.Column():
                secondary_merge_file = gr.File(label="Secondary Dataset", file_types=[".json"])
                secondary_status = gr.Textbox(label="Secondary Status", interactive=False)
                secondary_root_selector = gr.Dropdown(
                    label="Secondary Root Path",
                    choices=["(root)"],
                    value="(root)",
                    allow_custom_value=True,
                    interactive=True,
                )

        gr.Markdown("### 2. Configure merge")
        join_key_selector = gr.Dropdown(
            label="Common Join Keys",
            choices=[],
            value=[],
            multiselect=True,
            interactive=False,
            allow_custom_value=False,
            info="Select one or more fields present in both datasets.",
        )
        merge_filename = gr.Textbox(label="Merged Output Filename", placeholder="merged_output.json")

        gr.Markdown("### 3. Merge & export")
        merge_btn = gr.Button("Merge & Download", variant="primary")
        merge_download = gr.File(label="Merged Result")
        merge_status = gr.Textbox(label="Merge Status", interactive=False)
        merge_preview = gr.JSON(label="Preview (first 3 rows)")

        primary_merge_file.upload(
            fn=handle_primary_dataset_upload,
            inputs=[primary_merge_file, merge_secondary_keys_state, join_key_selector],
            outputs=[
                merge_primary_data_state,
                merge_primary_keys_state,
                primary_root_selector,
                primary_status,
                join_key_selector,
            ],
        )

        secondary_merge_file.upload(
            fn=handle_secondary_dataset_upload,
            inputs=[secondary_merge_file, merge_primary_keys_state, join_key_selector],
            outputs=[
                merge_secondary_data_state,
                merge_secondary_keys_state,
                secondary_root_selector,
                secondary_status,
                join_key_selector,
            ],
        )

        primary_root_selector.change(
            fn=handle_primary_root_change,
            inputs=[merge_primary_data_state, primary_root_selector, merge_secondary_keys_state, join_key_selector],
            outputs=[merge_primary_keys_state, join_key_selector],
        )

        secondary_root_selector.change(
            fn=handle_secondary_root_change,
            inputs=[merge_secondary_data_state, secondary_root_selector, merge_primary_keys_state, join_key_selector],
            outputs=[merge_secondary_keys_state, join_key_selector],
        )

        merge_btn.click(
            fn=merge_datasets_handler,
            inputs=[
                merge_primary_data_state,
                merge_secondary_data_state,
                primary_root_selector,
                secondary_root_selector,
                join_key_selector,
                merge_filename,
            ],
            outputs=[merge_download, merge_status, merge_preview],
        )

if __name__ == "__main__":
    demo.launch()
