from __future__ import annotations

import duckdb
import pytest

from indicium_ai_agent.metrics.metric_functions import (
    get_case_growth_rate,
    get_mortality_rate,
    get_uti_admission_rate,
    get_vaccination_coverage,
)


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    db = duckdb.connect(":memory:")
    db.execute("""
        CREATE TABLE srag AS SELECT * FROM (
            VALUES
                ('2026-01-01', 1, 1, 2, 1, 1, 'SP'),
                ('2026-01-02', 2, 1, 1, 1, 2, 'SP'),
                ('2026-01-05', 1, 1, 1, 2, 1, 'RJ'),
                ('2026-01-10', 2, 2, 1, 1, 1, 'SP'),
                ('2026-01-15', 1, 1, 2, 2, 2, 'RJ'),
                ('2026-01-20', 3, 1, 1, 1, 1, 'SP'),
                ('2026-01-25', 9, 1, 2, 1, 2, 'RJ'),
                ('2026-01-28', 1, 2, 2, 2, 1, 'SP'),
                ('2026-02-01', 2, 1, 1, 1, 1, 'RJ'),
                ('2026-02-05', 1, 1, 1, 2, 2, 'SP'),
        ) AS t(DT_SIN_PRI, EVOLUCAO, HOSPITAL, UTI, VACINA_COV, VACINA, SG_UF)
    """)
    return db


def test_get_case_growth_rate_computable(con: duckdb.DuckDBPyConnection) -> None:
    result = get_case_growth_rate(con, end_date_str="2026-02-10", days=7)
    assert result["computable"] is True
    assert result["numerator"] >= 0
    assert result["denominator"] >= 0
    assert result["definition_ref"] == "case_growth_rate_v1"
    assert "SELECT" in result["query"]


def test_get_case_growth_rate_zero_prior(con: duckdb.DuckDBPyConnection) -> None:
    result = get_case_growth_rate(con, end_date_str="2026-01-03", days=7)
    assert result["computable"] is False
    assert result["value"] is None


def test_get_case_growth_rate_empty_table() -> None:
    empty = duckdb.connect(":memory:")
    empty.execute("""
        CREATE TABLE srag AS
        SELECT * FROM (VALUES ('2026-01-01'::VARCHAR, 1::INT, 1::INT, 1::INT, 1::INT, 1::INT, 'SP'::VARCHAR))
        AS t(DT_SIN_PRI, EVOLUCAO, HOSPITAL, UTI, VACINA_COV, VACINA, SG_UF) WHERE 1=0
    """)
    result = get_case_growth_rate(empty, end_date_str="2026-02-10", days=7)
    assert result["computable"] is False
    assert result["numerator"] == 0
    assert result["denominator"] == 0
    assert result["value"] is None


def test_get_mortality_rate_excludes_evolucao_3(
    con: duckdb.DuckDBPyConnection,
) -> None:
    result = get_mortality_rate(con, "2026-01-01", "2026-02-28")
    assert result["computable"] is True
    assert 0 <= result["value"] <= 1
    assert result["numerator"] >= 0
    assert result["denominator"] >= 0
    assert result["definition_ref"] == "mortality_rate_v1"


def test_get_mortality_rate_evolucao_3_excluded(
    con: duckdb.DuckDBPyConnection,
) -> None:
    result = get_mortality_rate(con, "2026-01-20", "2026-02-01")
    assert result["computable"] is True
    assert result["denominator"] == 1
    assert result["numerator"] == 0


def test_get_mortality_rate_zero_denominator(con: duckdb.DuckDBPyConnection) -> None:
    result = get_mortality_rate(con, "2026-01-03", "2026-01-04")
    assert result["computable"] is False
    assert result["value"] is None


def test_get_uti_admission_rate(con: duckdb.DuckDBPyConnection) -> None:
    result = get_uti_admission_rate(con, "2026-01-01", "2026-02-28")
    assert result["computable"] is True
    assert 0 <= result["value"] <= 1
    assert result["definition_ref"] == "uti_admission_rate_v1"


def test_get_uti_admission_rate_zero_denominator(
    con: duckdb.DuckDBPyConnection,
) -> None:
    result = get_uti_admission_rate(con, "2026-03-01", "2026-03-31")
    assert result["computable"] is False
    assert result["value"] is None


def test_get_vaccination_coverage(con: duckdb.DuckDBPyConnection) -> None:
    result = get_vaccination_coverage(con, "2026-01-01", "2026-02-28")
    assert result["computable"] is True
    assert isinstance(result["value"], dict)
    assert "covid" in result["value"]
    assert "flu" in result["value"]
    assert 0 <= result["value"]["covid"] <= 1
    assert 0 <= result["value"]["flu"] <= 1
    assert isinstance(result["numerator"], dict)
    assert "covid" in result["numerator"]
    assert "flu" in result["numerator"]
    assert result["definition_ref"] == "vaccination_coverage_v1"


def test_get_vaccination_coverage_zero_denominator(
    con: duckdb.DuckDBPyConnection,
) -> None:
    result = get_vaccination_coverage(con, "2026-03-01", "2026-03-31")
    assert result["computable"] is False
    assert result["value"] is None


def test_metric_functions_return_queries(
    con: duckdb.DuckDBPyConnection,
) -> None:
    r0 = get_case_growth_rate(con, end_date_str="2026-02-10", days=7)
    r1 = get_mortality_rate(con, "2026-01-01", "2026-02-28")
    r2 = get_uti_admission_rate(con, "2026-01-01", "2026-02-28")
    r3 = get_vaccination_coverage(con, "2026-01-01", "2026-02-28")
    for r in [r0, r1, r2, r3]:
        assert "SELECT" in r["query"]
