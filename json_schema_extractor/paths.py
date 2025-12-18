from __future__ import annotations

from typing import List


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
