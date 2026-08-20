from __future__ import annotations

from typing import Any, Literal, Required, TypedDict

import duckdb

from indicium_ai_agent.config.settings import DataMode


class DataCheckResult(TypedDict, total=False):
    """Outcome of the freshness check / sync step."""

    action: str  # pinned_snapshot | cached_up_to_date | downloaded | used_cache
    checked_at: str  # ISO timestamp of the check
    remote_last_modified: str  # remote Last-Modified header value
    remote_etag: str  # remote ETag header value
    cached_last_modified: str  # cached Last-Modified for comparison
    error: str  # error message when fallback occurred


class ReportState(TypedDict, total=False):
    """Shared mutable state threaded through the LangGraph pipeline.

    Required keys are present at invocation; optional keys are filled
    incrementally by nodes. ``total=False`` allows incremental building.
    """

    data_mode: Required[DataMode]  # execution mode: pinned or live
    data_source_url: Required[str]  # remote CSV URL for live mode
    start_date: Required[str]  # period start, inclusive (YYYY-MM-DD)
    end_date: Required[str]  # period end, exclusive (YYYY-MM-DD)
    run_id: Required[str]  # unique identifier for this pipeline run
    data_check_result: DataCheckResult  # freshness / sync outcome
    raw_csv_path: str  # resolved local path to raw CSV
    con: duckdb.DuckDBPyConnection | None  # in-memory DuckDB connection
    exclusion_log: dict[str, Any]  # PII and column-filter provenance log
    metrics: dict[str, Any]  # computed epidemiological metrics
    chart_paths: dict[str, str]  # generated chart file paths by label
    news_items: list[dict[str, str]]  # fetched news items
    news_source: Literal["tavily", "unavailable"]  # news provider id
    news_flagged: bool  # whether news was flagged (e.g. content issues)
    sanitized_news: str  # sanitized news text for LLM synthesis
    narrative_draft: str  # raw LLM narrative draft
    narrative_validated: str  # validated / cleaned narrative
    validation_passed: bool  # whether narrative passed grounding checks
    validation_diff: dict[str, Any]  # mismatches found during validation
    retry_count: int  # validation retry attempts performed
    source_csv_hash: str  # SHA256 of source CSV
    source_extraction_date: str  # extraction date from filename (YYYY-MM-DD)
    timezone: str  # timezone for all report timestamps
    report_path: str  # rendered Markdown report path
    audit_log_path: str  # audit log JSON path
    error: str | None  # per-node error message, if any
