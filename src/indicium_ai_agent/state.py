from __future__ import annotations

from typing import Any, Literal, TypedDict

from indicium_ai_agent.config.settings import DataMode


class ReportState(TypedDict):
    data_mode: DataMode
    data_source_url: str
    start_date: str
    end_date: str
    data_check_result: dict[str, Any]
    raw_csv_path: str
    con: Any
    exclusion_log: dict[str, Any]
    metrics: dict[str, Any]
    chart_paths: dict[str, str]
    news_items: list[dict[str, str]]
    news_source: Literal["tavily", "unavailable"]
    news_flagged: bool
    sanitized_news: str
    narrative_draft: str
    narrative_validated: str
    validation_passed: bool
    validation_diff: dict[str, Any]
    retry_count: int
    run_id: str
    source_csv_hash: str
    source_extraction_date: str
    timezone: str
    report_path: str
    audit_log_path: str
