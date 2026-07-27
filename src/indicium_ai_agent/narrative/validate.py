from __future__ import annotations

import re
from typing import Any

MAX_RETRIES = 3
ROUNDING_TOLERANCE = 0.01


def canonicalize_number(text: str) -> float | None:
    cleaned = text.strip().removesuffix("%")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_all_numbers(text: str) -> list[tuple[str, float]]:
    pattern = r"\b\d+[\.,]?\d*%?\b"
    matches: list[tuple[str, float]] = []
    for match in re.finditer(pattern, text):
        raw = match.group()
        num = canonicalize_number(raw)
        if num is not None:
            matches.append((raw, num))
    return matches


def _get_metric_values(metrics: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for metric_key in (
        "case_growth_rate", "mortality_rate",
        "uti_admission_rate", "vaccination_coverage",
    ):
        data = metrics.get(metric_key, {})
        if not data.get("computable", False):
            continue
        val = data.get("value")
        if isinstance(val, dict):
            values.extend(v for v in val.values() if isinstance(v, (int, float)))
        elif isinstance(val, (int, float)):
            values.append(val)
    return values


def check_numeric_grounding(
    narrative: str,
    metrics: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    allowed_values = _get_metric_values(metrics)
    found = _extract_all_numbers(narrative)
    mismatches: list[dict[str, Any]] = []

    for raw, num in found:
        is_valid = any(
            abs(num - allowed) <= ROUNDING_TOLERANCE
            or (allowed > 0 and abs(num - allowed) / allowed <= ROUNDING_TOLERANCE)
            for allowed in allowed_values
        )
        if not is_valid:
            mismatches.append({"raw": raw, "value": num})

    return len(mismatches) == 0, mismatches


def check_source_grounding(
    narrative: str,
    news_items: list[dict[str, str]],
) -> tuple[bool, list[dict[str, Any]]]:
    known_urls = {item.get("url", "") for item in news_items}

    url_pattern = r"https?://[^\s\)\"']+"
    raw_urls = re.findall(url_pattern, narrative)
    cited_urls = {u.rstrip(".,)") for u in raw_urls}
    mismatches: list[dict[str, Any]] = []

    for url in sorted(cited_urls):
        if url not in known_urls:
            mismatches.append({"cited": url, "type": "url"})

    return len(mismatches) == 0, mismatches


def _strip_mismatches(
    narrative: str,
    numeric_mismatches: list[dict[str, Any]],
    source_mismatches: list[dict[str, Any]],
) -> str:
    result = narrative
    for m in numeric_mismatches:
        result = result.replace(m.get("raw", ""), "")
    for m in source_mismatches:
        result = result.replace(m.get("cited", ""), "")
    result = re.sub(r" {2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def validate_narrative(
    narrative_draft: str,
    metrics: dict[str, Any],
    news_items: list[dict[str, str]],
    retry_count: int = 0,
) -> dict[str, Any]:
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
