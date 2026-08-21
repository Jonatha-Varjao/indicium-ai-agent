"""Sanitize external news content and detect prompt-injection attempts."""

from __future__ import annotations

import logging
import re
from typing import Any, Final, TypedDict

logger = logging.getLogger(__name__)

DELIMITER_START: Final[str] = "{{NEWS_CONTENT_START}}"
DELIMITER_END: Final[str] = "{{NEWS_CONTENT_END}}"

# Narrow, phrase-based patterns — avoids false positives like
# "health system" or "prompt medical care" from the previous broad pattern.
INJECTION_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"(?i)\b(ignore|disregard)\s+(previous|all)\s+instructions\b"),
    re.compile(r"(?i)\bact\s+as\b"),
    re.compile(r"(?i)\byou\s+are\s+now\b"),
    re.compile(r"(?i)\bdisregard\s+the\s+previous\b"),
    re.compile(r"(?i)\boverride\s+(previous\s+)?instructions\b"),
]

# Portuguese-language phrases — the curated news domain is Brazilian
# (Fiocruz, gov.br, national press), so PT-BR injection attempts are the
# realistic threat model. Qualifier words keep false positives low:
# "não ignore as orientações médicas" does NOT match ("ignorar" != "ignore",
# "orientações" alone lacks the imperative verb + qualifier pair).
INJECTION_PATTERNS_PT: Final[list[re.Pattern[str]]] = [
    re.compile(
        r"(?i)\b(?:ignore|desconsidere|desobede[çc]a)\s+"
        r"(?:todas\s+as\s+|as\s+)?(?:instru[çc][õo]es|regras|ordens)\s+"
        r"(?:anteriores|pr[ée]vias|previas|acima|do\s+sistema)\b"
    ),
    re.compile(
        r"(?i)\bdesconsidere\s+(?:tudo\s+)?o\s+"
        r"(?:que\s+foi\s+dito|texto|conte[úu]do)\s+(?:acima|anterior)\b"
    ),
    re.compile(r"(?i)\baja\s+como\b"),
    re.compile(r"(?i)\bassuma\s+o\s+papel\b"),
    re.compile(r"(?i)\bvoc[êe]\s+[ée]\s+agora\b"),
]

ALL_INJECTION_PATTERNS: Final[list[re.Pattern[str]]] = (
    INJECTION_PATTERNS + INJECTION_PATTERNS_PT
)


class SanitizeNewsResult(TypedDict):
    """Result of :func:`sanitize_news`."""

    sanitized_news: str
    news_flagged: bool


def _is_flagged(text: str) -> bool:
    """Return ``True`` if *text* matches any injection pattern (EN or PT-BR)."""
    return any(pattern.search(text) for pattern in ALL_INJECTION_PATTERNS)


def _strip_injection(text: str) -> str:
    """Remove injection phrases from *text* and normalise whitespace."""
    for pattern in ALL_INJECTION_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"\s+([.,;])", r"\1", text)
    return text


def sanitize_news(news_items: list[dict[str, str]]) -> SanitizeNewsResult:
    """Sanitize news snippets and delimit the result.

    - Handles non-list or empty input gracefully.
    - Strips delimiter markers from snippets.
    - Detects prompt-injection via phrase-based patterns.
    - For flagged items, strips the injection phrase via ``re.sub``
      and skips empty results; ``news_flagged`` remains ``True``.

    Args:
        news_items: List of mappings with at least a ``snippet`` key.

    Returns:
        Mapping with ``sanitized_news`` (delimited string) and
        ``news_flagged`` (whether any injection was detected).
    """
    if not isinstance(news_items, list):
        logger.warning("sanitize_news expected list, got %s", type(news_items).__name__)
        return {"sanitized_news": "", "news_flagged": False}

    if not news_items:
        return {"sanitized_news": "", "news_flagged": False}

    flagged = False
    sanitized_parts: list[str] = []

    for item in news_items:
        if not isinstance(item, dict):
            logger.warning("Skipping non-dict news item: %r", item)
            continue

        snippet: Any = item.get("snippet", "")
        if not isinstance(snippet, str):
            snippet = str(snippet)

        text = snippet.replace(DELIMITER_START, "").replace(DELIMITER_END, "")

        if _is_flagged(text):
            flagged = True
            text = _strip_injection(text)
            if not text:
                continue

        sanitized_parts.append(text)

    if not sanitized_parts:
        return {"sanitized_news": "", "news_flagged": flagged}

    sanitized_news = f"{DELIMITER_START}\n" + "\n\n".join(sanitized_parts) + f"\n{DELIMITER_END}"

    return {"sanitized_news": sanitized_news, "news_flagged": flagged}
