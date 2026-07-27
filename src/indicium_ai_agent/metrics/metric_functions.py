from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import duckdb


def _make_period(start: str, end: str) -> str:
    return f"{start} to {end}"


def _today_br() -> date:
    import datetime as dt

    return dt.datetime.now(dt.UTC).date()


def get_case_growth_rate(
    con: duckdb.DuckDBPyConnection,
    end_date_str: str | None = None,
    days: int = 7,
) -> dict[str, Any]:
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
    params = [start_current.isoformat(), end.isoformat(),
              start_prior.isoformat(), mid_point.isoformat()]
    row = con.execute(query, params).fetchone()

    if row is None:
        current, prior = 0, 0
    else:
        current, prior = row

    computable = prior is not None and prior > 0
    value = ((current - prior) / prior * 100) if computable else None

    return {
        "value": round(value, 2) if value is not None else None,
        "computable": computable,
        "numerator": current or 0,
        "denominator": prior or 0,
        "period": _make_period(start_current.isoformat(), end.isoformat()),
        "definition_ref": "case_growth_rate_v1",
        "query": query,
    }


def get_mortality_rate(
    con: duckdb.DuckDBPyConnection,
    start_date_str: str,
    end_date_str: str,
) -> dict[str, Any]:
    query = """
        SELECT
            SUM(CASE WHEN EVOLUCAO = 2 THEN 1 ELSE 0 END) AS obitos,
            SUM(CASE WHEN EVOLUCAO IN (1, 2) THEN 1 ELSE 0 END) AS resolvidos
        FROM srag
        WHERE CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
          AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
    """
    params = [start_date_str, end_date_str]
    row = con.execute(query, params).fetchone()

    if row is None:
        obitos, resolvidos = 0, 0
    else:
        obitos, resolvidos = row

    computable = resolvidos is not None and resolvidos > 0
    value = (obitos / resolvidos) if computable else None

    return {
        "value": round(value, 4) if value is not None else None,
        "computable": computable,
        "numerator": obitos or 0,
        "denominator": resolvidos or 0,
        "period": _make_period(start_date_str, end_date_str),
        "definition_ref": "mortality_rate_v1",
        "query": query,
    }


def get_uti_admission_rate(
    con: duckdb.DuckDBPyConnection,
    start_date_str: str,
    end_date_str: str,
) -> dict[str, Any]:
    query = """
        SELECT
            SUM(CASE WHEN UTI = 1 THEN 1 ELSE 0 END) AS uti_cases,
            SUM(CASE WHEN HOSPITAL = 1 THEN 1 ELSE 0 END) AS hospital_cases
        FROM srag
        WHERE CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
          AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
    """
    params = [start_date_str, end_date_str]
    row = con.execute(query, params).fetchone()

    if row is None:
        uti_cases, hospital_cases = 0, 0
    else:
        uti_cases, hospital_cases = row

    computable = hospital_cases is not None and hospital_cases > 0
    value = (uti_cases / hospital_cases) if computable else None

    return {
        "value": round(value, 4) if value is not None else None,
        "computable": computable,
        "numerator": uti_cases or 0,
        "denominator": hospital_cases or 0,
        "period": _make_period(start_date_str, end_date_str),
        "definition_ref": "uti_admission_rate_v1",
        "query": query,
    }


def get_vaccination_coverage(
    con: duckdb.DuckDBPyConnection,
    start_date_str: str,
    end_date_str: str,
) -> dict[str, Any]:
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
    params = [start_date_str, end_date_str]
    row = con.execute(query, params).fetchone()

    if row is None:
        cov_vaccinated, flu_vaccinated, hospital_cases = 0, 0, 0
    else:
        cov_vaccinated, flu_vaccinated, hospital_cases = row

    computable = hospital_cases is not None and hospital_cases > 0
    value = (
        {
            "covid": round(cov_vaccinated / hospital_cases, 4),
            "flu": round(flu_vaccinated / hospital_cases, 4),
        }
        if computable
        else None
    )

    return {
        "value": value,
        "computable": computable,
        "numerator": {"covid": cov_vaccinated or 0, "flu": flu_vaccinated or 0},
        "denominator": hospital_cases or 0,
        "period": _make_period(start_date_str, end_date_str),
        "definition_ref": "vaccination_coverage_v1",
        "query": query,
    }
