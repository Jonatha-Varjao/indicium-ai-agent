"""Shared narrative utilities.

Provides :func:`coerce_content_to_str` for normalising Gemini response content
and :func:`format_metric_value` for consistent metric value rendering.
"""

from __future__ import annotations

from typing import Any


def coerce_content_to_str(content: Any) -> str:
    """Coerce narrative text to string, handling Gemini list responses.

    Gemini can return ``response.content`` as a list of content blocks
    (e.g. ``[{"type": "text", "text": "..."}]``) or as a plain string.
    This function normalises both forms.

    Args:
        content: Raw content which may be a string, list of blocks, or any
            other type.

    Returns:
        Flattened string representation of the content.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", str(block))))
            elif isinstance(block, str):
                parts.append(block)
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def format_metric_value(value: Any) -> str:
    """Format a metric value for display.

    Handles dict values (e.g. vaccination coverage with multiple keys) by
    joining ``k: v`` pairs, formats floats with 4 decimal places, and
    falls back to ``str(value)`` for other types.

    Args:
        value: Metric value which may be a dict, float, int, or other.

    Returns:
        Human-readable string representation.
    """
    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in value.items()]
        return "; ".join(parts)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
