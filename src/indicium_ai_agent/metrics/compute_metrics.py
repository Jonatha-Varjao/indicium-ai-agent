from __future__ import annotations

from typing import Any

import duckdb

from indicium_ai_agent.metrics.metric_functions import (
    get_case_growth_rate,
    get_mortality_rate,
    get_uti_admission_rate,
    get_vaccination_coverage,
)


def compute_metrics(
    con: duckdb.DuckDBPyConnection,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}

    metrics["case_growth_rate"] = get_case_growth_rate(con, end_date_str=end_date)
    metrics["mortality_rate"] = get_mortality_rate(con, start_date, end_date)
    metrics["uti_admission_rate"] = get_uti_admission_rate(con, start_date, end_date)
    metrics["vaccination_coverage"] = get_vaccination_coverage(con, start_date, end_date)

    return {"metrics": metrics}
