"""Epidemiological metric functions backed by DuckDB aggregates."""

from __future__ import annotations

import datetime as dt
import zoneinfo
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any, Final, TypedDict

import duckdb

DEFAULT_GROWTH_DAYS: Final[int] = 7
"""Default window in days for case growth rate comparison."""

GROWTH_ROUND: Final[int] = 2
"""Decimal places for growth rate (percentage)."""

RATE_ROUND: Final[int] = 4
"""Decimal places for proportion rates (mortality, UTI, vaccination)."""

_BRAZIL_TZ: Final[zoneinfo.ZoneInfo] = zoneinfo.ZoneInfo("America/Sao_Paulo")
"""Timezone for Brazil-local date calculations."""


class MetricResult(TypedDict):
    """Standard shape for metric outputs.

    Attributes:
        value: Computed metric value (float, dict for vaccination, or None).
        computable: Whether the metric could be computed (denominator > 0).
        numerator: Raw numerator count or dict for vaccination.
        denominator: Raw denominator count.
        period: Human-readable period string ``'{start} to {end}'``.
        definition_ref: Versioned definition identifier.
        query: SQL query used for computation.
    """

    value: float | dict[str, float] | None
    computable: bool
    numerator: int | dict[str, int]
    denominator: int
    period: str
    definition_ref: str
    query: str


def _make_period(start: str, end: str) -> str:
    """Format a period string.

    Args:
        start: ISO date string for period start (inclusive).
        end: ISO date string for period end (exclusive).

    Returns:
        Formatted period string ``'{start} to {end}'``.
    """
    return f"{start} to {end}"


def _today_br() -> date:
    """Return today's date in ``America/Sao_Paulo`` timezone.

    Returns:
        Current date in Brazil timezone.
    """
    return dt.datetime.now(_BRAZIL_TZ).date()


def _execute_aggregate(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: Sequence[Any],
) -> tuple[Any, ...]:
    """Execute an aggregate query and fetch one row.

    Handles the ``SUM``-over-empty-table case where DuckDB returns
    ``(None, None)`` rather than ``None`` for the row itself.

    Args:
        con: DuckDB connection.
        query: SQL with positional ``?`` placeholders.
        params: Parameters bound to the query.

    Returns:
        Tuple of aggregate values, possibly containing ``None``. Empty
        tuple if ``fetchone`` returns ``None`` (e.g., missing table
        would raise before this).
    """
    row = con.execute(query, params).fetchone()
    if row is None:
        return ()
    return tuple(row)


def _normalize_aggregates(row: tuple[Any, ...]) -> list[int | None]:
    """Normalize an aggregate row into ints or ``None`` per column.

    Args:
        row: Raw tuple from :func:`_execute_aggregate` (may be empty).

    Returns:
        List with one entry per expected aggregate: the value as
        ``int``, or ``None`` when absent/NULL.
    """
    return [int(v) if v is not None else None for v in row]


def _build_result(
    value: float | dict[str, float] | None,
    numerator: int | dict[str, int],
    denominator: int,
    period: str,
    definition_ref: str,
    query: str,
) -> MetricResult:
    """Build a standardized metric result dict.

    Computable is derived from ``value is not None`` to avoid
    duplicating denominator checks across call sites.

    Args:
        value: Computed metric value, rounded, or ``None``.
        numerator: Raw numerator count(s).
        denominator: Raw denominator count.
        period: Period string from :func:`_make_period`.
        definition_ref: Versioned definition identifier.
        query: SQL query used.

    Returns:
        Standardized :class:`MetricResult` dict.
    """
    return {
        "value": value,
        "computable": value is not None,
        "numerator": numerator,
        "denominator": denominator,
        "period": period,
        "definition_ref": definition_ref,
        "query": query,
    }


def get_case_growth_rate(
    con: duckdb.DuckDBPyConnection,
    end_date_str: str | None = None,
    days: int = DEFAULT_GROWTH_DAYS,
) -> MetricResult:
    """Compute case growth rate over rolling windows.

    Formula: ``(current - prior) / prior * 100`` where ``current`` is
    count in ``[end - days, end)`` and ``prior`` in
    ``[end - 2*days, end - days)``.

    Args:
        con: DuckDB connection with ``srag`` table.
        end_date_str: ISO end date (exclusive). Defaults to today in
            ``America/Sao_Paulo``.
        days: Window size in days.

    Returns:
        Metric result with percentage value rounded to
        :const:`GROWTH_ROUND` decimals.
    """
    end = date.fromisoformat(end_date_str) if end_date_str else _today_br()
    start_current = end - timedelta(days=days)
    start_prior = end - timedelta(days=2 * days)
    mid_point = end - timedelta(days=days)

    query = """
        SELECT
            SUM(CASE WHEN CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
                      AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
                THEN 1 ELSE 0 END) AS current_period,
            SUM(CASE WHEN CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
                      AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
                THEN 1 ELSE 0 END) AS prior_period
        FROM srag
    """
    params: Sequence[Any] = [
        start_current.isoformat(),
        end.isoformat(),
        start_prior.isoformat(),
        mid_point.isoformat(),
    ]
    row = _execute_aggregate(con, query, params)
    vals = _normalize_aggregates(row)
    current_raw: int | None = vals[0] if len(vals) > 0 else None
    prior_raw: int | None = vals[1] if len(vals) > 1 else None

    current: int = 0 if current_raw is None else current_raw
    prior: int = 0 if prior_raw is None else prior_raw

    computable = prior_raw is not None and prior_raw > 0 and current_raw is not None
    value: float | None = None
    if computable:
        # prior > 0 guaranteed, current is int
        value = round((current - prior) / prior * 100, GROWTH_ROUND)

    return _build_result(
        value,
        current,
        prior,
        _make_period(start_current.isoformat(), end.isoformat()),
        "case_growth_rate_v1",
        query,
    )


def get_mortality_rate(
    con: duckdb.DuckDBPyConnection,
    start_date_str: str,
    end_date_str: str,
) -> MetricResult:
    """Compute mortality rate among resolved cases.

    Formula: ``obitos / resolvidos`` where ``obitos`` counts
    ``EVOLUCAO = 2`` and ``resolvidos`` counts ``EVOLUCAO IN (1, 2)``.
    ``EVOLUCAO = 3`` (death other causes) and ``9`` are excluded.

    Args:
        con: DuckDB connection.
        start_date_str: ISO start date (inclusive).
        end_date_str: ISO end date (exclusive).

    Returns:
        Metric result with proportion rounded to :const:`RATE_ROUND`.
    """
    query = """
        SELECT
            SUM(CASE WHEN EVOLUCAO = 2 THEN 1 ELSE 0 END) AS obitos,
            SUM(CASE WHEN EVOLUCAO IN (1, 2) THEN 1 ELSE 0 END) AS resolvidos
        FROM srag
        WHERE CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
          AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
    """
    params: Sequence[Any] = [start_date_str, end_date_str]
    row = _execute_aggregate(con, query, params)
    vals = _normalize_aggregates(row)
    obitos_raw: int | None = vals[0] if len(vals) > 0 else None
    resolvidos_raw: int | None = vals[1] if len(vals) > 1 else None

    obitos: int = 0 if obitos_raw is None else obitos_raw
    resolvidos: int = 0 if resolvidos_raw is None else resolvidos_raw

    computable = obitos_raw is not None and resolvidos_raw is not None and resolvidos_raw > 0
    value: float | None = None
    if computable:
        value = round(obitos / resolvidos, RATE_ROUND)

    return _build_result(
        value,
        obitos,
        resolvidos,
        _make_period(start_date_str, end_date_str),
        "mortality_rate_v1",
        query,
    )


def get_uti_admission_rate(
    con: duckdb.DuckDBPyConnection,
    start_date_str: str,
    end_date_str: str,
) -> MetricResult:
    """Compute UTI admission rate among hospitalized cases.

    Formula: ``uti_cases / hospital_cases`` where ``UTI = 1`` and
    ``HOSPITAL = 1``.

    Args:
        con: DuckDB connection.
        start_date_str: ISO start date (inclusive).
        end_date_str: ISO end date (exclusive).

    Returns:
        Metric result with proportion rounded to :const:`RATE_ROUND`.
    """
    query = """
        SELECT
            SUM(CASE WHEN UTI = 1 THEN 1 ELSE 0 END) AS uti_cases,
            SUM(CASE WHEN HOSPITAL = 1 THEN 1 ELSE 0 END) AS hospital_cases
        FROM srag
        WHERE CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
          AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
    """
    params: Sequence[Any] = [start_date_str, end_date_str]
    row = _execute_aggregate(con, query, params)
    vals = _normalize_aggregates(row)
    uti_raw: int | None = vals[0] if len(vals) > 0 else None
    hospital_raw: int | None = vals[1] if len(vals) > 1 else None

    uti_cases: int = 0 if uti_raw is None else uti_raw
    hospital_cases: int = 0 if hospital_raw is None else hospital_raw

    computable = uti_raw is not None and hospital_raw is not None and hospital_raw > 0
    value: float | None = None
    if computable:
        value = round(uti_cases / hospital_cases, RATE_ROUND)

    return _build_result(
        value,
        uti_cases,
        hospital_cases,
        _make_period(start_date_str, end_date_str),
        "uti_admission_rate_v1",
        query,
    )


def get_vaccination_coverage(
    con: duckdb.DuckDBPyConnection,
    start_date_str: str,
    end_date_str: str,
) -> MetricResult:
    """Compute vaccination coverage among hospitalized cases.

    Reports two separate proportions for ``VACINA_COV`` and ``VACINA``
    over hospitalized cases (``HOSPITAL = 1``). Explicitly hospital-
    based, not population coverage.

    Args:
        con: DuckDB connection.
        start_date_str: ISO start date (inclusive).
        end_date_str: ISO end date (exclusive).

    Returns:
        Metric result with dict value ``{"covid": ..., "flu": ...}``
        rounded to :const:`RATE_ROUND`, or ``None`` if not computable.
    """
    query = """
        SELECT
            SUM(CASE WHEN VACINA_COV = 1 THEN 1 ELSE 0 END) AS cov_vaccinated,
            SUM(CASE WHEN VACINA = 1 THEN 1 ELSE 0 END) AS flu_vaccinated,
            SUM(CASE WHEN HOSPITAL = 1 THEN 1 ELSE 0 END) AS hospital_cases
        FROM srag
        WHERE HOSPITAL = 1
          AND CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
          AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
    """
    params: Sequence[Any] = [start_date_str, end_date_str]
    row = _execute_aggregate(con, query, params)
    vals = _normalize_aggregates(row)
    cov_raw: int | None = vals[0] if len(vals) > 0 else None
    flu_raw: int | None = vals[1] if len(vals) > 1 else None
    hospital_raw: int | None = vals[2] if len(vals) > 2 else None

    cov_vaccinated: int = 0 if cov_raw is None else cov_raw
    flu_vaccinated: int = 0 if flu_raw is None else flu_raw
    hospital_cases: int = 0 if hospital_raw is None else hospital_raw

    computable = (
        cov_raw is not None
        and flu_raw is not None
        and hospital_raw is not None
        and hospital_raw > 0
    )
    value: dict[str, float] | None = None
    if computable:
        value = {
            "covid": round(cov_vaccinated / hospital_cases, RATE_ROUND),
            "flu": round(flu_vaccinated / hospital_cases, RATE_ROUND),
        }

    return _build_result(
        value,
        {"covid": cov_vaccinated, "flu": flu_vaccinated},
        hospital_cases,
        _make_period(start_date_str, end_date_str),
        "vaccination_coverage_v1",
        query,
    )
