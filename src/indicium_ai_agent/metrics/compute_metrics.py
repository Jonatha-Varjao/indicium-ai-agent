"""Orchestrate computation of all SRAG epidemiological metrics."""

from __future__ import annotations

import logging
from typing import TypedDict

import duckdb

from indicium_ai_agent.config.constants import METRIC_KEYS
from indicium_ai_agent.metrics.metric_functions import (
    MetricResult,
    _make_period,
    get_case_growth_rate,
    get_mortality_rate,
    get_uti_admission_rate,
    get_vaccination_coverage,
)

logger = logging.getLogger(__name__)


class MetricsResult(TypedDict):
    """Return shape for :func:`compute_metrics`.

    Attributes:
        metrics: Mapping from metric key to :class:`MetricResult`.
    """

    metrics: dict[str, MetricResult]


def _fallback_result(
    period: str,
    definition_ref: str,
    numerator: int | dict[str, int],
    denominator: int = 0,
) -> MetricResult:
    """Build a non-computable fallback result for error cases.

    Args:
        period: Period string.
        definition_ref: Metric definition identifier.
        numerator: Zero numerator (or dict for vaccination).
        denominator: Zero denominator.

    Returns:
        Non-computable :class:`MetricResult` with ``value=None``.
    """
    return {
        "value": None,
        "computable": False,
        "numerator": numerator,
        "denominator": denominator,
        "period": period,
        "definition_ref": definition_ref,
        "query": "",
    }


def compute_metrics(
    con: duckdb.DuckDBPyConnection,
    start_date: str,
    end_date: str,
) -> MetricsResult:
    """Compute all metrics for the given period.

    Handles swapped ``start_date``/``end_date`` by swapping, and
    isolates failures per metric so a missing table or query error
    does not abort the whole pipeline.

    Args:
        con: DuckDB connection with ``srag`` table.
        start_date: ISO start date (inclusive).
        end_date: ISO end date (exclusive).

    Returns:
        Typed dict ``{"metrics": {...}}`` keyed by :const:`METRIC_KEYS`.
    """
    # Handle swapped dates (ISO strings compare lexicographically)
    if start_date > end_date:
        logger.warning("Swapped start_date > end_date: %s > %s", start_date, end_date)
        start_date, end_date = end_date, start_date

    period = _make_period(start_date, end_date)
    metrics: dict[str, MetricResult] = {}

    # case_growth_rate uses end_date window; period differs
    try:
        metrics["case_growth_rate"] = get_case_growth_rate(con, end_date_str=end_date)
    except Exception as exc:
        logger.warning("case_growth_rate failed: %s", exc)
        # Growth period is computed inside helper; reuse swapped end
        fallback_period = period
        try:
            # Try to compute period as helper does (7-day window)
            from datetime import date, timedelta  # local import to avoid cycle

            from indicium_ai_agent.metrics.metric_functions import DEFAULT_GROWTH_DAYS

            end = date.fromisoformat(end_date)
            start = end - timedelta(days=DEFAULT_GROWTH_DAYS)
            fallback_period = _make_period(start.isoformat(), end.isoformat())
        except Exception:
            fallback_period = period
        metrics["case_growth_rate"] = _fallback_result(fallback_period, "case_growth_rate_v1", 0, 0)

    try:
        metrics["mortality_rate"] = get_mortality_rate(con, start_date, end_date)
    except Exception as exc:
        logger.warning("mortality_rate failed: %s", exc)
        metrics["mortality_rate"] = _fallback_result(period, "mortality_rate_v1", 0, 0)

    try:
        metrics["uti_admission_rate"] = get_uti_admission_rate(con, start_date, end_date)
    except Exception as exc:
        logger.warning("uti_admission_rate failed: %s", exc)
        metrics["uti_admission_rate"] = _fallback_result(period, "uti_admission_rate_v1", 0, 0)

    try:
        metrics["vaccination_coverage"] = get_vaccination_coverage(con, start_date, end_date)
    except Exception as exc:
        logger.warning("vaccination_coverage failed: %s", exc)
        metrics["vaccination_coverage"] = _fallback_result(
            period, "vaccination_coverage_v1", {"covid": 0, "flu": 0}, 0
        )

    # Ensure all expected keys present (defensive, uses METRIC_KEYS import)
    for key in METRIC_KEYS:
        if key not in metrics:
            logger.warning("Missing metric key: %s", key)
            metrics[key] = _fallback_result(period, f"{key}_v1", 0, 0)

    return {"metrics": metrics}
