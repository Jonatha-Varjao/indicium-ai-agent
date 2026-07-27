from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from indicium_ai_agent.graph import _should_retry, build_graph
from indicium_ai_agent.state import ReportState


def test_graph_builds() -> None:
    graph = build_graph()
    assert graph is not None


def test_graph_has_all_nodes() -> None:
    graph = build_graph()
    expected = {
        "check_and_sync", "load_and_clean", "compute_metrics",
        "generate_charts", "fetch_news", "sanitize_news",
        "synthesize_narrative", "validate_narrative",
        "render_report", "log_audit", "log_trace",
    }
    nodes = set(graph.nodes.keys())
    for name in expected:
        assert name in nodes, f"Missing node: {name}"


def test_graph_entry_point() -> None:
    graph = build_graph()
    assert graph is not None
    assert "check_and_sync" in graph.nodes


def test_should_retry_validation_passed() -> None:
    state: ReportState = {
        "validation_passed": True,
        "retry_count": 0,
        "data_mode": "pinned",
        "data_source_url": "",
        "start_date": "",
        "end_date": "",
        "data_check_result": {},
        "raw_csv_path": "",
        "con": None,
        "exclusion_log": {},
        "metrics": {},
        "chart_paths": {},
        "news_items": [],
        "news_source": "unavailable",
        "news_flagged": False,
        "sanitized_news": "",
        "narrative_draft": "",
        "narrative_validated": "",
        "validation_diff": {},
        "run_id": "",
        "source_csv_hash": "",
        "source_extraction_date": "",
        "timezone": "",
        "report_path": "",
        "audit_log_path": "",
    }
    assert _should_retry(state) == "continue"


def test_should_retry_max_retries() -> None:
    state: ReportState = {
        "validation_passed": False,
        "retry_count": 3,
        "data_mode": "pinned",
        "data_source_url": "",
        "start_date": "",
        "end_date": "",
        "data_check_result": {},
        "raw_csv_path": "",
        "con": None,
        "exclusion_log": {},
        "metrics": {},
        "chart_paths": {},
        "news_items": [],
        "news_source": "unavailable",
        "news_flagged": False,
        "sanitized_news": "",
        "narrative_draft": "",
        "narrative_validated": "",
        "validation_diff": {},
        "run_id": "",
        "source_csv_hash": "",
        "source_extraction_date": "",
        "timezone": "",
        "report_path": "",
        "audit_log_path": "",
    }
    assert _should_retry(state) == "continue"


def test_should_retry_mismatch() -> None:
    state: ReportState = {
        "validation_passed": False,
        "retry_count": 0,
        "data_mode": "pinned",
        "data_source_url": "",
        "start_date": "",
        "end_date": "",
        "data_check_result": {},
        "raw_csv_path": "",
        "con": None,
        "exclusion_log": {},
        "metrics": {},
        "chart_paths": {},
        "news_items": [],
        "news_source": "unavailable",
        "news_flagged": False,
        "sanitized_news": "",
        "narrative_draft": "",
        "narrative_validated": "",
        "validation_diff": {},
        "run_id": "",
        "source_csv_hash": "",
        "source_extraction_date": "",
        "timezone": "",
        "report_path": "",
        "audit_log_path": "",
    }
    assert _should_retry(state) == "retry"


@patch("indicium_ai_agent.graph.check_and_sync_data")
def test_node_adapter_check_sync(mock_sync: object, tmp_path: Path) -> None:
    from indicium_ai_agent.graph import _node_check_and_sync

    state: ReportState = {
        "data_mode": "pinned",
        "data_source_url": "http://test",
        "start_date": "",
        "end_date": "",
        "data_check_result": {},
        "raw_csv_path": "",
        "con": None,
        "exclusion_log": {},
        "metrics": {},
        "chart_paths": {},
        "news_items": [],
        "news_source": "unavailable",
        "news_flagged": False,
        "sanitized_news": "",
        "narrative_draft": "",
        "narrative_validated": "",
        "validation_passed": False,
        "validation_diff": {},
        "retry_count": 0,
        "run_id": "test",
        "source_csv_hash": "",
        "source_extraction_date": "",
        "timezone": "America/Sao_Paulo",
        "report_path": "",
        "audit_log_path": "",
    }

    with patch("indicium_ai_agent.graph.get_settings") as mock_settings:
        mock_settings.return_value.data_raw_dir = tmp_path
        mock_settings.return_value.data_cache_dir = tmp_path
        result = _node_check_and_sync(state)

    assert "raw_csv_path" in result
    assert "data_check_result" in result


def test_run_report_importable() -> None:
    import scripts.run_report  # type: ignore[import-untyped]

    assert hasattr(scripts.run_report, "main")
    assert hasattr(scripts.run_report, "_resolve_dates")


def test_resolve_dates_defaults() -> None:
    import argparse

    from scripts.run_report import _resolve_dates

    args = argparse.Namespace(start_date=None, end_date=None)
    start, end = _resolve_dates(args)
    assert start <= end
    assert len(start) == 10
    assert len(end) == 10
