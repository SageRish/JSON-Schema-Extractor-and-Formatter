import gradio as gr
from functools import partial

from json_schema_extractor.schema_utils import build_tree_from_keys, extract_all_keys
from json_schema_extractor.handlers_single import (
    export_data_handler,
    handle_root_change_single_dataset,
    load_and_parse_json_with_preview,
    preview_single_dataset_handler,
    update_mapping_table_and_clear_preview,
)
from json_schema_extractor.handlers_merge import (
    handle_primary_dataset_upload,
    handle_primary_root_change,
    handle_secondary_dataset_upload,
    handle_secondary_root_change,
    merge_datasets_handler,
)

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
