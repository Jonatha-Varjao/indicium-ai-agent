"""Validation of narrative grounding for numeric and source citations."""

from __future__ import annotations

import re
from typing import Any, Final

from indicium_ai_agent.config.constants import (
    KNOWN_DURATION_DAYS,
    MAX_RETRIES,
    METRIC_KEYS,
)
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

# Numbers followed by a month name are prose dates; intermediate
# "e DD"/"a DD" covers ranges ("entre 13 e 20", "de 13 a 20 de julho").
_DATE_CONTEXT: Final[re.Pattern[str]] = re.compile(
    rf"\s*(?:[ae]\s+\d{{1,2}}\s*)?(?:de\s+)?{ _MONTHS_PT }\b", re.IGNORECASE
)
# Numbers followed by "dia(s)" are duration references to documented
# windows; "a N" covers ranges ("últimos 7 a 14 dias").
_DURATION_CONTEXT: Final[re.Pattern[str]] = re.compile(
    r"\s*(?:a\s+\d+)?\s*dias?\b", re.IGNORECASE
)
# Methodology anchors that legitimise a window reference.
# The anchor must be immediately adjacent to the duration token (or its
# range predecessor), not merely anywhere in the preceding window.
# This prevents leakage: "nos últimos 30 dias, 7 dias de internação"
# must NOT exempt the second "7 dias" (anchor "últimos" is followed by
# an intervening "30 dias," -> not adjacent).
_DURATION_ANCHOR_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:últim[oa]s|ultimos|próxim[oa]s|proximos|per[íi]odo(?:\s+de)?|"
    r"janela(?:\s+de)?)(?:\s+\d+\s*a)?\s*$",
    re.IGNORECASE,
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


def _is_documented_year(raw: str) -> bool:
    """Plain 4-digit year 1900-2100 without a ``%`` sign."""
    if "%" in raw or not re.fullmatch(r"\d{4}", raw):
        return False
    return 1900 <= int(raw) <= 2100


_CLINICAL_DURATION_WORDS: Final[frozenset[str]] = frozenset(
    {
        "internação",
        "internacao",
        "internações",
        "internacoes",
        "hospitalização",
        "hospitalizacao",
        "hospitalizações",
        "hospitalizacoes",
        "febre",
        "tratamento",
        "tratamentos",
        "sintomas",
        "sintoma",
        "doença",
        "doenca",
        "doenças",
        "doencas",
        "enfermaria",
        "uti",
        "utis",
        "estadia",
        "permanência",
        "permanencia",
        "recuperação",
        "recuperacao",
        "isolamento",
        "isolamentos",
        "quarentena",
        "quarentenas",
        "ventilação",
        "ventilacao",
    }
)

# Methodology continuations that legitimately follow a window: keep exempt
# e.g. "14 dias de observação" -> still a documented window description
_METHODOLOGY_DURATION_WORDS: Final[frozenset[str]] = frozenset(
    {
        "observação",
        "observacao",
        "observações",
        "observacoes",
        "análise",
        "analise",
        "análises",
        "analises",
        "coleta",
        "estudo",
        "estudos",
        "monitoramento",
        "vigilância",
        "vigilancia",
        "notificação",
        "notificacao",
        "acompanhamento",
        "avaliação",
        "avaliacao",
        "período",
        "periodo",
        "janela",
    }
)


def _is_documented_duration(num: float, tail: str, before_context: str) -> bool:
    """Duration token referencing a documented methodology window (7/14/30).

    Exemption requires BOTH the value to be a known window AND an
    anchoring methodology phrase immediately before the token
    ("últimos 7 dias", "próximos 14 dias", "período de 7 a 14 dias").
    Bare clinical claims like "internação média de 7 dias" do NOT match
    and stay subject to numeric grounding. Even with a valid anchor,
    a trailing clinical qualifier ("7 dias de internação",
    "7 dias na UTI", "7 dias de longa internação") indicates a
    fabricated clinical duration and is NOT exempt, while methodology
    continuations ("7 dias de observação") remain exempt.

    Args:
        num: Token value with sign.
        tail: Text immediately after the token.
        before_context: Lowercased text window before the token.

    Returns:
        Whether the token is exempt from grounding as a documented window.
    """
    m = _DURATION_CONTEXT.match(tail)
    if not m:
        return False
    if not (num.is_integer() and int(abs(num)) in KNOWN_DURATION_DAYS):
        return False
    if _DURATION_ANCHOR_RE.search(before_context) is None:
        return False
    # A trailing prepositional continuation with a clinical noun
    # (e.g. "dias de internação", "dias na UTI",
    # "dias de longa internação") signals a clinical duration claim
    # and must be grounded. Methodology continuations like
    # "dias de observação" (observação not in clinical set) remain exempt.
    remaining = tail[m.end():].lstrip().lower()
    if remaining.startswith(
        ("de ", "da ", "do ", "das ", "dos ", "na ", "no ", "nas ", "nos ", "em ", "com ", "para ")
    ):
        # A prepositional continuation after "dias" is clinical by default
        # (e.g. "7 dias de internação", "7 dias na UTI",
        # "7 dias de ventilação mecânica") and must be grounded.
        # Only methodology continuations like "dias de observação" remain
        # exempt — check next 1-2 words against the methodology allowlist.
        # Clinical takes priority: any clinical noun in the continuation
        # (e.g. "de observação em internação" -> "internação") must be
        # grounded, even if a methodology word also appears.
        words = re.findall(r"\b\w+\b", remaining.lower())
        if any(w in _CLINICAL_DURATION_WORDS for w in words):
            return False
        if any(w in _METHODOLOGY_DURATION_WORDS for w in words[:3]):
            return True
        return False
    return True


def _extract_all_numbers(text: str) -> list[tuple[str, float, int]]:
    """Extract numeric tokens with spans, filtering non-quantitative contexts.

    Skips tokens that are structurally not metric values:
    - components of slash-dates (``20/07/2026``)
    - 4-digit years 1900-2100 without a ``%``
    - ordinals (``1º``)
    - letter-hyphen codes (the ``19`` in ``COVID-19``)
    - prose dates (number followed by a month name)
    - durations matching documented windows only (7 / 14 days); any
      other "N dias" claim stays in the list for grounding

    Signed literals keep their sign (``-78,12`` -> -78.12).

    Args:
        text: Narrative text to scan.

    Returns:
        List of ``(raw, value, start_index)`` tuples.
    """
    pattern = r"(?<!\d)\d+(?:[.,]\d+)?%?(?!\d)"
    matches: list[tuple[str, float, int]] = []
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
        # Alphanumeric codes: the "1" in "g1", the "2" in "H3N2"
        if before.isalpha():
            continue
        if _is_documented_year(raw):
            continue
        num = canonicalize_number(raw)
        if num is None:
            continue
        # Explicit signed literal: "-78,12" carries its own sign
        if before == "-":
            num = -num
        tail = text[end:]
        # Prose dates stay contextual (calendar facts, not quantities)
        before_context = text[max(0, start - _DIRECTION_WINDOW):start].lower()
        if _DATE_CONTEXT.match(tail) or _is_documented_duration(
            num, tail, before_context
        ):
            continue
        matches.append((raw, num, start))
    return matches


def _get_metric_values(metrics: dict[str, Any]) -> list[float]:
    """Collect all values the narrative is allowed to reference.

    Includes metric ``value``, plus numerators/denominators — both are
    provided verbatim to the LLM in the user prompt, so citing them is
    grounded by definition. Unit proportions (0 < |v| < 1) also accept
    their percent voicing (``0.388`` -> ``38.8``), a standard reading.

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
                for sub in val.values():
                    _append_allowed(values, sub)
            elif isinstance(val, (int, float)):
                _append_allowed(values, val)
    return values


def _append_allowed(values: list[float], v: Any) -> None:
    """Append one allowed value, plus its percent voice when unit-scaled."""
    if not isinstance(v, (int, float)):
        return
    f = float(v)
    values.append(f)
    if 0 < abs(f) < 1:
        values.append(f * 100)


_DECREASE_WORDS: Final[tuple[str, ...]] = (
    "redução", "queda", "diminuição", "declínio", "recuo",
    "caída", "caiu", "reduziu", "diminuiu", "desceu", "menor",
)
_INCREASE_WORDS: Final[tuple[str, ...]] = (
    "aumento", "alta", "crescimento", "elevação", "subida",
    "subiu", "aumentou", "cresceu", "maior",
)

# Word-boundary alternation (longest first so "aumentos" still hits
# "aumento"); used to locate the NEAREST direction word to the token.
_DIRECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b("
    + "|".join(
        sorted((*_DECREASE_WORDS, *_INCREASE_WORDS), key=len, reverse=True)
    )
    + r")\b"
)
# Immediate direction phrase: word + "de" directly before the number,
# allowing 0-4 modifiers ("queda muito acentuada anual de 78,12%").
# Prevents distant words like "Após queda anterior, mortalidade de
# 0,0579" from misgrounding while still catching phrasing variants.
_IMMEDIATE_DIRECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b("
    + "|".join(
        sorted((*_DECREASE_WORDS, *_INCREASE_WORDS), key=len, reverse=True)
    )
    + r")(?:\s+\w+){0,4}\s+de\s*$"
)
_DECREASE_SET: Final[frozenset[str]] = frozenset(_DECREASE_WORDS)

# How many chars before a token to look for the direction word
_DIRECTION_WINDOW: Final[int] = 48


def _within_tolerance(num: float, allowed: float) -> bool:
    """Numeric tolerance only (sign-sensitive): absolute for zero."""
    diff = abs(num - allowed)
    if allowed == 0:
        return diff <= ROUNDING_TOLERANCE
    return diff / abs(allowed) <= ROUNDING_TOLERANCE


def _nearest_direction_word(context: str) -> str | None:
    """Return the direction word occurring LAST in *context* (nearest the
    numeric token), or None when no direction word is present.

    Args:
        context: Lowercased text immediately before the token.

    Returns:
        The matched word in lowercase, or None.
    """
    last: str | None = None
    for match in _DIRECTION_RE.finditer(context):
        last = match.group().lower()
    return last


def _immediate_direction_word(context: str) -> str | None:
    """Return direction word if it immediately precedes the number
    as ``<word> de`` (e.g. "queda de 78,12%").

    Handles signed literals like "aumento de -78,12%" where the
    context ends with "de -" — the trailing dash/space is stripped
    before matching. Prevents distant words like "Após queda
    anterior, mortalidade de 0,0579" from being misattributed.

    Args:
        context: Lowercased text immediately before the token.

    Returns:
        The direction word or None.
    """
    # Strip trailing dash left by signed literals ("de -" -> "de")
    stripped = context.rstrip(" \t\n\r-")
    m = _IMMEDIATE_DIRECTION_RE.search(stripped)
    if m:
        return m.group(1).lower()
    return None


_METRIC_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "mortalidade",
        "letalidade",
        "óbitos",
        "obitos",
        "casos",
        "internação",
        "internacao",
        "uti",
        "vacinação",
        "vacinacao",
        "covid",
        "influenza",
        "gripe",
        "srag",
        "taxa",
    }
)


def _nearby_direction_word(context: str) -> str | None:
    """Nearest direction word in *context* before the token.

    Uses the full preserved context (48 chars) and only skips words
    separated by sentence boundaries (.,;) or by an intervening metric
    keyword that indicates a different clause (e.g. "queda anterior,
    mortalidade de 0,0579"). Long modifiers like
    "queda muito acentuada anual de 78,12%" are correctly handled
    because no metric keyword intervenes.

    Args:
        context: Lowercased text window before the token (up to 48 chars).

    Returns:
        Direction word or None.
    """
    last: str | None = None
    for match in _DIRECTION_RE.finditer(context):
        between = context[match.end():].lower()
        if any(c in between for c in ".;"):
            continue
        if any(kw in between for kw in _METRIC_KEYWORDS):
            continue
        last = match.group().lower()
    return last


def _is_grounded(num: float, allowed: float, context: str) -> bool:
    """Direction-aware grounding check.

    Signed matches are checked against the nearest direction word within
    a bounded window (free-form wording like "queda no total, 78,12%"
    still validates), while opposite-sign magnitudes require an
    immediate "<word> de" phrase. This balances catching reversed
    trends against distant-word misattribution.

    Args:
        num: Token value with its literal sign.
        allowed: Metric value to ground against.
        context: Lowercased text immediately before the token.

    Returns:
        Whether the token is grounded on ``allowed``.
    """
    if _within_tolerance(num, allowed):
        nearby = _nearby_direction_word(context)
        if nearby is not None:
            expected_decrease = allowed < 0
            is_decrease = nearby in _DECREASE_SET
            if expected_decrease != is_decrease:
                return False
        return True
    if num == 0 or allowed == 0:
        return False
    if not _within_tolerance(abs(num), abs(allowed)):
        return False
    # Opposite-sign magnitude requires immediate direction word
    immediate = _immediate_direction_word(context)
    if allowed < 0:
        return immediate is not None and immediate in _DECREASE_SET
    # allowed > 0: magnitude of a positive metric must read as increase
    return immediate is not None and immediate not in _DECREASE_SET


def _collect_news_numbers(news_items: list[dict[str, str]] | None) -> frozenset[float]:
    """Collect numbers appearing verbatim in retrieved news items.

    The LLM legitimately cites statistics from the sanitized news block
    (rule 4 of the system prompt); such figures are grounded by their
    source even though they are not pipeline-computed metrics. The same
    extraction/noise filters apply, so prose dates etc. are excluded.

    Args:
        news_items: News items with ``title``/``snippet`` fields.

    Returns:
        Set of canonicalised values found across all items.
    """
    values: set[float] = set()
    for item in news_items or []:
        blob = f"{item.get('title', '')} {item.get('snippet', '')}"
        values.update(
            v for _raw, v, _start in _extract_all_numbers(blob)
        )
    return frozenset(values)


def check_numeric_grounding(
    narrative: str,
    metrics: dict[str, Any],
    news_items: list[dict[str, str]] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """Check that every number in the narrative is grounded.

    A token is grounded when it matches (sign-aware, direction-checked)
    a computed metric value/numerator/denominator, or appears verbatim
    in a retrieved news item.

    Args:
        narrative: Narrative text to validate.
        metrics: Computed metrics providing allowed values.
        news_items: Retrieved news whose own figures are citable.

    Returns:
        Tuple of (is_valid, mismatches).
    """
    allowed_values = _get_metric_values(metrics)
    news_values = _collect_news_numbers(news_items)
    found = _extract_all_numbers(narrative)
    mismatches: list[dict[str, Any]] = []

    for raw, num, start in found:
        context = narrative[max(0, start - _DIRECTION_WINDOW):start].lower()
        grounded_metric = any(
            _is_grounded(num, allowed, context) for allowed in allowed_values
        )
        if not grounded_metric and num not in news_values:
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
    numeric_ok, numeric_diff = check_numeric_grounding(
        narrative_draft, metrics, news_items
    )
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
