from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from indicium_ai_agent.charts.generate_charts import generate_charts


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    db = duckdb.connect(":memory:")
    db.execute("""
        CREATE TABLE srag AS
        SELECT CAST('2026-01-01' AS DATE) + INTERVAL (row_number() OVER () - 1) DAY AS DT_SIN_PRI
        FROM range(400) AS t
    """)
    return db


def test_generate_charts_creates_files(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    result = generate_charts(con, tmp_path)
    assert "daily" in result
    assert "monthly" in result
    assert Path(result["daily"]).exists()
    assert Path(result["monthly"]).exists()


def test_charts_have_content(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    result = generate_charts(con, tmp_path, end_date_str="2026-12-31")
    daily_size = Path(result["daily"]).stat().st_size
    monthly_size = Path(result["monthly"]).stat().st_size
    assert daily_size > 1000
    assert monthly_size > 1000


def test_generate_charts_output_dir_created(tmp_path: Path) -> None:
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE srag AS
        SELECT CAST('2026-01-01' AS DATE) AS DT_SIN_PRI
        UNION ALL
        SELECT CAST('2026-06-15' AS DATE)
    """)
    nested = tmp_path / "sub" / "dir"
    result = generate_charts(con, nested, end_date_str="2026-12-31")
    assert Path(result["daily"]).exists()
    assert Path(result["monthly"]).exists()


def test_generate_charts_empty_table(tmp_path: Path) -> None:
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE srag AS
        SELECT CAST('2026-01-01' AS DATE) AS DT_SIN_PRI WHERE 1=0
    """)
    result = generate_charts(con, tmp_path, end_date_str="2026-12-31")
    assert Path(result["daily"]).exists()
    assert Path(result["monthly"]).exists()
