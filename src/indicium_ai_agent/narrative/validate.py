"""Validation of narrative grounding for numeric and source citations."""

from __future__ import annotations

import re
from typing import Any, Final

from indicium_ai_agent.config.constants import MAX_RETRIES, METRIC_KEYS
from indicium_ai_agent.narrative._utils import coerce_content_to_str

# Tolerance for numeric grounding: 1% relative for non-zero, absolute for zero.
# Using relative tolerance avoids overly lenient absolute checks for small
# values (e.g. 0.05 absolute 0.01 == 20% relative would incorrectly pass).
ROUNDING_TOLERANCE: Final[float] = 0.01

# PT-BR thousands grouping: 7.485 / 129.373 / 1.234.567 (leading block captured)
_THOUSANDS_GROUPED: Final[re.Pattern[str]] = re.compile(r"^(\d{1,3})(?:\.\d{3})+$")

_MONTHS_PT: Final[str] = (
    r"(?:jan(?:eiro)?|fev(?:ereiro)?|mar[çc]o|abr(?:il)?|mai(?:o)?|jun(?:ho)?|"
    r"jul(?:ho)?|ago(?:sto)?|set(?:embro)?|out(?:ubro)?|nov(?:embro)?|dez(?:embro)?)"
)

# Numbers followed by a month name are prose dates; an intermediate
# "e DD" covers ranges ("entre 13 e 20 de julho").
_DATE_CONTEXT: Final[re.Pattern[str]] = re.compile(
    rf"\s*(?:e\s+\d{{1,2}}\s*)?(?:de\s+)?{ _MONTHS_PT }\b", re.IGNORECASE
)
# Numbers followed by "dia(s)" are duration references to documented
# windows; "a N" covers ranges ("últimos 7 a 14 dias").
_DURATION_CONTEXT: Final[re.Pattern[str]] = re.compile(
    r"\s*(?:a\s+\d+)?\s*dias?\b", re.IGNORECASE
)

_MONTHS_RE = _DATE_CONTEXT


def canonicalize_number(text: str) -> float | None:
    """Parse a numeric string using PT-BR conventions.

    Rules (domain is a Brazilian narrative):
    - Comma is the decimal separator; dots, when a comma exists, are
      thousands separators (``1.234,56`` → ``1234.56``).
    - Dot-grouped integers without a comma are thousands-separated
      counts (``7.485`` → ``7485``), not decimals.
    - A trailing ``%`` is ignored.

    Args:
        text: Raw numeric token (e.g. "15,5%", "7.485").

    Returns:
        Float value or None if parsing fails.
    """
    cleaned = text.strip().removesuffix("%")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        grouped = _THOUSANDS_GROUPED.match(cleaned)
        # Thousands grouping ("7.485") only when the leading block isn't
        # "0" — "0.154" is a decimal, never a count.
        if grouped and grouped.group(1) != "0":
            cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_all_numbers(text: str) -> list[tuple[str, float]]:
    """Extract numeric tokens, filtering non-quantitative contexts.

    Skips tokens that are structurally not metric values:
    - components of slash-dates (``20/07/2026``)
    - 4-digit years 1900-2100 without a ``%``
    - ordinals (``1º``)
    - letter-hyphen codes (the ``19`` in ``COVID-19``)
    - prose dates (number followed by a month name)
    - day-duration references (``7 dias``, matching documented windows)

    Args:
        text: Narrative text to scan.

    Returns:
        List of (raw, value) tuples for grounded numbers.
    """
    pattern = r"(?<!\d)\d+(?:[.,]\d+)?%?(?!\d)"
    matches: list[tuple[str, float]] = []
    for match in re.finditer(pattern, text):
        raw = match.group()
        start, end = match.span()
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        # Slash-date components
        if before == "/" or after == "/":
            continue
        # Ordinals: "1º de janeiro"
        if after == "º":
            continue
        # Letter-hyphen codes: the "19" in "COVID-19"
        if before == "-" and start >= 2 and text[start - 2].isalpha():
            continue
        # Prose dates and durations
        tail = text[end:]
        if _DATE_CONTEXT.match(tail) or _DURATION_CONTEXT.match(tail):
            continue
        # Plain 4-digit years 1900-2100 when not a percentage
        if "%" not in raw and re.fullmatch(r"\d{4}", raw):
            year = int(raw)
            if 1900 <= year <= 2100:
                continue
        num = canonicalize_number(raw)
        if num is not None:
            matches.append((raw, num))
    return matches


def _get_metric_values(metrics: dict[str, Any]) -> list[float]:
    """Collect all values the narrative is allowed to reference.

    Includes metric ``value``, plus numerators/denominators — both are
    provided verbatim to the LLM in the user prompt, so citing them is
    grounded by definition.

    Args:
        metrics: Full metrics dict.

    Returns:
        List of allowed numeric values for grounding.
    """
    values: list[float] = []
    for metric_key in METRIC_KEYS:
        data = metrics.get(metric_key, {})
        if not isinstance(data, dict):
            continue
        if not data.get("computable", False):
            continue
        for field in ("value", "numerator", "denominator"):
            val = data.get(field)
            if isinstance(val, dict):
                values.extend(
                    float(v) for v in val.values() if isinstance(v, (int, float))
                )
            elif isinstance(val, (int, float)):
                values.append(float(val))
    return values


def _is_grounded(num: float, allowed: float) -> bool:
    """Sign-agnostic tolerance check.

    Magnitude comparison: an LLM legitimately phrases negative rates as
    positive magnitudes ("redução de 78,12%" for -78.12), so the sign
    carries meaning in words while the number itself is grounded.
    """
    diff = abs(abs(num) - abs(allowed))
    if allowed == 0:
        return diff <= ROUNDING_TOLERANCE
    return diff / abs(allowed) <= ROUNDING_TOLERANCE


def check_numeric_grounding(
    narrative: str,
    metrics: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """Check that every number in the narrative is grounded in metrics.

    Uses single tolerance strategy: absolute for zero, relative for non-zero.

    Args:
        narrative: Narrative text to validate.
        metrics: Computed metrics providing allowed values.

    Returns:
        Tuple of (is_valid, mismatches).
    """
    allowed_values = _get_metric_values(metrics)
    found = _extract_all_numbers(narrative)
    mismatches: list[dict[str, Any]] = []

    for raw, num in found:
        if not any(_is_grounded(num, allowed) for allowed in allowed_values):
            mismatches.append({"raw": raw, "value": num})

    return len(mismatches) == 0, mismatches


def check_source_grounding(
    narrative: str,
    news_items: list[dict[str, str]],
) -> tuple[bool, list[dict[str, Any]]]:
    """Check that every URL in the narrative is from known news items.

    Normalizes URLs by stripping trailing slashes for comparison.

    Args:
        narrative: Narrative text to validate.
        news_items: List of known news items with ``url`` keys.

    Returns:
        Tuple of (is_valid, mismatches).
    """
    known_urls = {
        item.get("url", "").rstrip("/") for item in news_items if item.get("url", "")
    }

    url_pattern = r"https?://[^\s\)\"']+"
    raw_urls = re.findall(url_pattern, narrative)
    # Strip trailing punctuation then trailing slash for comparison
    cited_urls = {u.rstrip(".,)").rstrip("/") for u in raw_urls}
    # Also normalize the set for display: keep original stripped only punctuation?
    # For mismatch reporting, use normalized without trailing slash.
    mismatches: list[dict[str, Any]] = []

    for url in sorted(cited_urls):
        normalized = url.rstrip("/")
        if normalized not in known_urls:
            mismatches.append({"cited": url, "type": "url"})

    return len(mismatches) == 0, mismatches


def _strip_mismatches(
    narrative: str,
    numeric_mismatches: list[dict[str, Any]],
    source_mismatches: list[dict[str, Any]],
) -> str:
    """Remove hallucinated numbers and URLs from narrative.

    Uses digit-aware boundaries for numeric replacements to avoid corrupting
    substrings inside larger numbers (e.g. removing 99.9 from 199.9).

    Args:
        narrative: Original narrative text.
        numeric_mismatches: List of numeric mismatches with ``raw``.
        source_mismatches: List of source mismatches with ``cited``.

    Returns:
        Cleaned narrative string.
    """
    result = narrative
    for m in numeric_mismatches:
        raw = m.get("raw", "")
        if not raw:
            continue
        # Word-boundary-aware replace for numbers
        pattern = rf"(?<!\d){re.escape(raw)}(?!\d)"
        result = re.sub(pattern, "", result)
    for m in source_mismatches:
        cited = m.get("cited", "")
        if cited:
            result = result.replace(cited, "")
            # Also handle variant with/without trailing slash if needed
            alt = cited.rstrip("/")
            if alt != cited:
                result = result.replace(alt, "")
            alt2 = cited + "/"
            if alt2 in result:
                result = result.replace(alt2, "")
    result = re.sub(r" {2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def validate_narrative(
    narrative_draft: str | list[Any],
    metrics: dict[str, Any],
    news_items: list[dict[str, str]],
    retry_count: int = 0,
) -> dict[str, Any]:
    """Validate narrative for numeric and source grounding.

    Args:
        narrative_draft: Raw narrative which may be str or Gemini list content.
        metrics: Computed metrics for grounding.
        news_items: Known news items for source validation.
        retry_count: Current retry attempt count.

    Returns:
        Dict with validation_passed, narrative_validated, validation_diff,
        and retry_count.
    """
    narrative_draft = coerce_content_to_str(narrative_draft)
    numeric_ok, numeric_diff = check_numeric_grounding(narrative_draft, metrics)
    source_ok, source_diff = check_source_grounding(narrative_draft, news_items)

    validation_diff: dict[str, Any] = {}
    if numeric_diff:
        validation_diff["numeric_mismatches"] = numeric_diff
    if source_diff:
        validation_diff["source_mismatches"] = source_diff

    passed = numeric_ok and source_ok

    if passed:
        return {
            "validation_passed": True,
            "narrative_validated": narrative_draft,
            "validation_diff": {},
            "retry_count": retry_count,
        }

    new_retry = retry_count + 1
    if new_retry >= MAX_RETRIES:
        cleaned = _strip_mismatches(narrative_draft, numeric_diff, source_diff)
        notice = (
            "\n\n> ⚠️ Narrativa parcialmente validada — "
            "consulte a tabela de métricas oficiais."
        )
        return {
            "validation_passed": False,
            "narrative_validated": cleaned + notice,
            "validation_diff": validation_diff,
            "retry_count": new_retry,
        }

    return {
        "validation_passed": False,
        "narrative_validated": "",
        "validation_diff": validation_diff,
        "retry_count": new_retry,
    }
