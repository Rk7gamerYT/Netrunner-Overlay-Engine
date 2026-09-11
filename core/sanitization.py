"""Small, deterministic limits for content received from platform connectors."""

import re


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value, max_length=4000):
    text = str(value or "")
    text = _CONTROL_CHARS.sub("", text)
    return text[:max(1, int(max_length))]


def sanitize_value(value, depth=0):
    """Bound nested connector metadata without changing its JSON shape."""
    if depth >= 4:
        return sanitize_text(value, 500) if not isinstance(value, (dict, list, tuple)) else "[conteúdo limitado]"
    if isinstance(value, str):
        return sanitize_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {
            sanitize_text(key, 80): sanitize_value(item, depth + 1)
            for key, item in list(value.items())[:64]
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_value(item, depth + 1) for item in list(value)[:100]]
    return sanitize_text(value, 500)
