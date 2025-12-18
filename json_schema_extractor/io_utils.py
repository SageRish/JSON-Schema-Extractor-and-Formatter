from __future__ import annotations

import json


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
