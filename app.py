import gradio as gr
import json
import csv
import os
import tempfile
from typing import List, Dict, Any, Set
from functools import partial

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
        parts = key.split('.')
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
                _flatten(x[a], name + a + sep)
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
            current_key = f"{parent_key}{sep}{k}" if parent_key else k
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
    keys = path.split(sep)
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
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key, None)
            elif isinstance(val, list):
                # If we are at a list, we need to "broadcast" the key access
                # and collect all results from all items (and nested items)
                val = collect_values(val, key)
                if not val:
                    val = None
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
            current_key = f"{parent_key}{sep}{k}" if parent_key else k
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

def load_and_parse_json(file_obj):
    if file_obj is None:
        return None, gr.update(choices=[]), gr.update(choices=[]), "No file uploaded."
    
    try:
        # Handle file_obj being a file-like object or a path string
        if hasattr(file_obj, 'read'):
            # It's a file object (likely open). Read directly to avoid Windows locking issues.
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            content = file_obj.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            data = json.loads(content)
        else:
            # It's a path string or wrapper with .name
            path = file_obj.name if hasattr(file_obj, 'name') else file_obj
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        all_keys = sorted(list(extract_all_keys(data)))
        list_paths = find_list_paths(data)
        if not list_paths and isinstance(data, list):
             list_paths = ["(root)"]
        elif not list_paths:
             list_paths = ["(root)"]
        
        # Default to (root) if available, else first list
        default_root = "(root)" if "(root)" in list_paths else (list_paths[0] if list_paths else None)

        # Reset selected fields state to empty list
        return data, [], gr.update(choices=list_paths, value=default_root), f"Successfully loaded. Found {len(all_keys)} unique fields."
    except Exception as e:
        return None, [], gr.update(choices=[]), f"Error parsing JSON: {str(e)}"

def update_mapping_table(selected_fields):
    # Create a list of lists for the dataframe: [Input Path, Output Name]
    # Default Output Name is the same as Input Path
    if not selected_fields:
        return []
    return [[f, f] for f in selected_fields]

def flatten_data_for_export(data: Any, selected_fields: List[str], mapping: Dict[str, str], root_path: str = '(root)') -> List[Dict[str, Any]]:
    """
    Flattens the data into a list of dictionaries based on selected fields and root path.
    """
    rows = []
    
    # Determine items to process based on root_path
    items_to_process = []
    
    if root_path == "(root)" or not root_path:
        if isinstance(data, list):
            items_to_process = data
        else:
            items_to_process = [data]
    else:
        # Navigate to the root path
        target = get_value_by_path(data, root_path)
        if isinstance(target, list):
            items_to_process = target
        elif target is not None:
            items_to_process = [target]
        else:
            items_to_process = []

    for item in items_to_process:
        row = {}
        for field in selected_fields:
            val = None
            # Logic to resolve field relative to item or absolute from data
            # If root_path is (root), everything is relative to item (which is data element)
            if root_path == "(root)" or not root_path:
                val = get_value_by_path(item, field)
            else:
                # If field starts with root_path, extract relative
                # e.g. root="users", field="users.name" -> rel="name"
                prefix = root_path + "."
                if field == root_path:
                     val = item # The item itself? Or maybe we shouldn't select the list itself.
                elif field.startswith(prefix):
                    rel_path = field[len(prefix):]
                    val = get_value_by_path(item, rel_path)
                else:
                    # Field is outside the root path (e.g. global metadata)
                    # Retrieve from global data object
                    val = get_value_by_path(data, field)

            # Handle lists in values (e.g. tags: ["a", "b"]) -> join them
            if isinstance(val, list):
                val = ", ".join([str(v) for v in val])
            
            # Map to new name
            out_name = mapping.get(field, field)
            row[out_name] = val
        rows.append(row)
    
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

# --- UI Definition ---
with gr.Blocks(title="JSON Schema Extractor") as demo:
    gr.Markdown("# JSON Schema Extractor and Converter")
    gr.Markdown("Upload a JSON file, select fields, map them to new names, and export to CSV or JSON.")
    
    # State
    json_data_state = gr.State()
    selected_fields_state = gr.State(value=[])
    
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
                        # Check for __self__ leaf
                        if "__self__" in node:
                            full_path = node["__self__"]
                            cb = gr.Checkbox(label=f"{label} (value)", value=False)
                            cb.change(fn=partial(on_change, full_path), inputs=[cb, selected_fields_state], outputs=[selected_fields_state])
                        
                        with gr.Accordion(label, open=False):
                            for k, v in node.items():
                                if k == "__self__": continue
                                recursive_ui(v, k)
                    else:
                        # Leaf
                        full_path = node
                        cb = gr.Checkbox(label=label, value=False)
                        cb.change(fn=partial(on_change, full_path), inputs=[cb, selected_fields_state], outputs=[selected_fields_state])

                # Start recursion
                # The tree root keys are the top level keys
                for k, v in tree.items():
                    recursive_ui(v, k)
            
        # Right Panel: Output Builder
        with gr.Column(scale=1):
            gr.Markdown("### 3. Output Builder")
            output_format = gr.Radio(choices=["CSV", "JSON"], value="CSV", label="Output Format")
            
            # New: Root Path Selector
            root_path_selector = gr.Dropdown(label="Data Root Path (for iteration)", choices=["(root)"], value="(root)", allow_custom_value=True, interactive=True)
            
            gr.Markdown("### 4. Field Mapping")
            gr.Markdown("Rename output columns if needed.")
            # Dataframe for mapping: Input Field (Read-only ideally, but here just reference) -> Output Name
            mapping_table = gr.Dataframe(
                headers=["Input Path", "Output Name"],
                datatype=["str", "str"],
                col_count=(2, "fixed"),
                interactive=True,
                label="Field Mapping"
            )
            
            gr.Markdown("### 5. Export")
            output_filename = gr.Textbox(label="Output Filename (optional)", placeholder="output")
            export_btn = gr.Button("Export Data", variant="primary")
            download_output = gr.File(label="Download Result")

    # Interactions
    file_input.upload(
        fn=load_and_parse_json,
        inputs=[file_input],
        outputs=[json_data_state, selected_fields_state, root_path_selector, status_msg]
    )
    
    selected_fields_state.change(
        fn=update_mapping_table,
        inputs=[selected_fields_state],
        outputs=[mapping_table]
    )
    
    export_btn.click(
        fn=export_data_handler,
        inputs=[json_data_state, mapping_table, output_format, output_filename, root_path_selector],
        outputs=[download_output, status_msg]
    )

if __name__ == "__main__":
    demo.launch()
