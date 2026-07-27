from __future__ import annotations

import re
from typing import Any

DELIMITER_START = "{{NEWS_CONTENT_START}}"
DELIMITER_END = "{{NEWS_CONTENT_END}}"

INJECTION_PATTERN = re.compile(
    r"(?i)\b(ignore|disregard|override|system|instruction|"
    r"prompt|you are|act as|role)\b"
)


def sanitize_news(news_items: list[dict[str, str]]) -> dict[str, Any]:
    flagged = False
    sanitized_parts: list[str] = []

    for item in news_items:
        text = item.get("snippet", "")

        text = text.replace(DELIMITER_START, "").replace(DELIMITER_END, "")

        if INJECTION_PATTERN.search(text):
            flagged = True

        sanitized_parts.append(text)

    if sanitized_parts:
        sanitized_news = (
            f"{DELIMITER_START}\n"
            + "\n\n".join(sanitized_parts)
            + f"\n{DELIMITER_END}"
        )
    else:
        sanitized_news = ""

    return {
        "sanitized_news": sanitized_news,
        "news_flagged": flagged,
    }
