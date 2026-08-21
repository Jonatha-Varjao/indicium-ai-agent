"""Unit tests for LangGraph node wrappers: happy paths, errors and guards."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from indicium_ai_agent.config.settings import DataMode
from indicium_ai_agent.graph import (
    _node_check_and_sync,
    _node_compute_metrics,
    _node_fetch_news,
    _node_generate_charts,
    _node_load_and_clean,
    _node_log_audit,
    _node_log_trace,
    _node_render_report,
    _node_sanitize_news,
    _node_synthesize_narrative,
    _node_validate_narrative,
    _should_retry,
    build_graph,
)
from indicium_ai_agent.state import ReportState

G = "indicium_ai_agent.graph"


def _state(**overrides: Any) -> ReportState:
    """Build a minimal ReportState (total=False allows partial)."""
    base: dict[str, Any] = {
        "data_mode": DataMode.PINNED.value,
        "data_source_url": "http://test",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "run_id": "test-run",
        "metrics": {},
        "chart_paths": {},
        "news_items": [],
        "news_source": "unavailable",
        "sanitized_news": "",
        "narrative_draft": "draft text",
        "narrative_validated": "",
        "validation_passed": False,
        "exclusion_log": {},
        "source_csv_hash": "abc123",
        "source_extraction_date": "2026-07-20",
        "retry_count": 0,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


# --- Error guard: every wrapper must skip when an error already exists -------


@pytest.mark.parametrize(
    ("node",),
    [
        (_node_check_and_sync,),
        (_node_load_and_clean,),
        (_node_compute_metrics,),
        (_node_generate_charts,),
        (_node_fetch_news,),
        (_node_sanitize_news,),
        (_node_synthesize_narrative,),
        (_node_validate_narrative,),
        (_node_render_report,),
    ],
)
def test_node_guards_return_empty_on_existing_error(node: Any) -> None:
    state = _state(error="original failure")
    result = node(state)
    assert result == {}


def test_should_retry_continues_on_error() -> None:
    state = _state(error="fatal", validation_passed=False, retry_count=0)
    assert _should_retry(state) == "continue"


# --- Node 0: check_and_sync ---------------------------------------------------


@patch(f"{G}.get_settings")
@patch(f"{G}.check_and_sync_data", side_effect=OSError("network down"))
def test_check_and_sync_exception(
    mock_sync: MagicMock, mock_settings: MagicMock, tmp_path: Path
) -> None:
    mock_settings.return_value.data_raw_dir = tmp_path
    mock_settings.return_value.data_cache_dir = tmp_path
    result = _node_check_and_sync(_state())
    assert result == {"error": "network down"}


# --- Node 1: load_and_clean ---------------------------------------------------


@patch(f"{G}.load_and_clean")
def test_load_and_clean_happy(mock_load: MagicMock) -> None:
    mock_load.return_value = {
        "con": MagicMock(),
        "exclusion_log": {"pii_columns": {}},
        "source_csv_hash": "abc",
        "source_extraction_date": "2026-07-20",
    }
    result = _node_load_and_clean(_state(raw_csv_path="data/raw/x.csv"))
    assert "con" in result
    assert result["source_csv_hash"] == "abc"
    assert "error" not in result


@patch(f"{G}.load_and_clean", side_effect=FileNotFoundError("CSV not found"))
def test_load_and_clean_exception(mock_load: MagicMock) -> None:
    result = _node_load_and_clean(_state(raw_csv_path="/missing.csv"))
    assert result == {"error": "CSV not found"}


# --- Node 2: compute_metrics --------------------------------------------------


@patch(f"{G}.compute_metrics")
def test_compute_metrics_happy(mock_cm: MagicMock) -> None:
    mock_cm.return_value = {"metrics": {"mortality_rate": {"computable": True}}}
    fake_con = MagicMock()
    result = _node_compute_metrics(_state(con=fake_con))
    assert result == {"metrics": {"mortality_rate": {"computable": True}}}
    mock_cm.assert_called_once_with(fake_con, "2026-01-01", "2026-01-31")


def test_compute_metrics_missing_con() -> None:
    result = _node_compute_metrics(_state(con=None))
    assert "DuckDB connection missing" in str(result.get("error"))


@patch(f"{G}.compute_metrics", side_effect=RuntimeError("sql fail"))
def test_compute_metrics_exception(mock_cm: MagicMock) -> None:
    result = _node_compute_metrics(_state(con=MagicMock()))
    assert result == {"error": "sql fail"}


# --- Node 3: generate_charts --------------------------------------------------


@patch(f"{G}.get_settings")
@patch(f"{G}.generate_charts")
def test_generate_charts_happy(
    mock_charts: MagicMock, mock_settings: MagicMock, tmp_path: Path
) -> None:
    mock_settings.return_value.output_charts_dir = tmp_path
    mock_charts.return_value = {"daily": str(tmp_path / "d.png")}
    fake_con = MagicMock()
    result = _node_generate_charts(_state(con=fake_con))
    assert result == {"chart_paths": {"daily": str(tmp_path / "d.png")}}


def test_generate_charts_missing_con() -> None:
    result = _node_generate_charts(_state(con=None))
    assert "connection missing" in str(result.get("error"))


@patch(f"{G}.get_settings")
@patch(f"{G}.generate_charts", side_effect=OSError("disk full"))
def test_generate_charts_exception(
    mock_charts: MagicMock, mock_settings: MagicMock, tmp_path: Path
) -> None:
    mock_settings.return_value.output_charts_dir = tmp_path
    result = _node_generate_charts(_state(con=MagicMock()))
    assert result == {"error": "disk full"}


# --- Node 4: fetch_news -------------------------------------------------------


@patch(f"{G}.fetch_news")
def test_fetch_news_happy(mock_fetch: MagicMock) -> None:
    items = [{"title": "t", "url": "https://x", "source": "s", "snippet": "n"}]
    mock_fetch.return_value = {"news_items": items, "news_source": "tavily"}
    result = _node_fetch_news(_state(metrics={"k": {}}))
    assert result["news_source"] == "tavily"
    assert result["news_items"] == items


@patch(f"{G}.fetch_news", side_effect=RuntimeError("api down"))
def test_fetch_news_exception(mock_fetch: MagicMock) -> None:
    result = _node_fetch_news(_state(metrics={}))
    assert result == {"error": "api down"}


# --- Node 5: sanitize_news ----------------------------------------------------


@patch(f"{G}.sanitize_news")
def test_sanitize_news_happy(mock_sanitize: MagicMock) -> None:
    mock_sanitize.return_value = {
        "sanitized_news": "{{NEWS_CONTENT_START}}x{{NEWS_CONTENT_END}}",
        "news_flagged": False,
    }
    result = _node_sanitize_news(_state(news_items=[{"snippet": "x"}]))
    assert result["news_flagged"] is False
    assert "sanitized_news" in result


@patch(f"{G}.sanitize_news", side_effect=TypeError("bad input"))
def test_sanitize_news_exception(mock_sanitize: MagicMock) -> None:
    result = _node_sanitize_news(_state(news_items=[]))
    assert result == {"error": "bad input"}


# --- Node 6: synthesize_narrative ---------------------------------------------


@patch(f"{G}.synthesize_narrative")
def test_synthesize_narrative_happy(mock_synth: MagicMock) -> None:
    mock_synth.return_value = {"narrative_draft": "texto analítico"}
    result = _node_synthesize_narrative(_state())
    assert result == {"narrative_draft": "texto analítico"}


@patch(f"{G}.synthesize_narrative", side_effect=RuntimeError("quota"))
def test_synthesize_narrative_exception(mock_synth: MagicMock) -> None:
    result = _node_synthesize_narrative(_state())
    assert result == {"error": "quota"}


# --- Node 7: validate_narrative -----------------------------------------------


@patch(f"{G}.validate_narrative")
def test_validate_narrative_happy(mock_validate: MagicMock) -> None:
    mock_validate.return_value = {
        "validation_passed": True,
        "narrative_validated": "ok",
        "validation_diff": {},
        "retry_count": 1,
    }
    result = _node_validate_narrative(_state(retry_count=0))
    assert result["validation_passed"] is True
    assert result["retry_count"] == 1
    # Retry counter propagated from state
    _, kwargs = mock_validate.call_args
    assert kwargs["retry_count"] == 0


@patch(f"{G}.validate_narrative", side_effect=ValueError("bad draft"))
def test_validate_narrative_exception(mock_validate: MagicMock) -> None:
    result = _node_validate_narrative(_state())
    assert result == {"error": "bad draft"}


# --- Node 8: render_report ----------------------------------------------------


@patch(f"{G}.render_report")
def test_render_report_happy(mock_render: MagicMock, tmp_path: Path) -> None:
    expected = str(tmp_path / "report.md")
    mock_render.return_value = {"report_path": expected}
    result = _node_render_report(_state())
    assert result == {"report_path": expected}
    mock_render.assert_called_once()


@patch(f"{G}.render_report", side_effect=OSError("cannot write"))
def test_render_report_exception(mock_render: MagicMock) -> None:
    result = _node_render_report(_state())
    assert result == {"error": "cannot write"}


# --- Node 9/10: audit + trace -------------------------------------------------


@patch(f"{G}.write_audit_log", return_value="outputs/logs/audit.json")
def test_log_audit_happy(mock_audit: MagicMock) -> None:
    result = _node_log_audit(_state())
    assert result == {"audit_log_path": "outputs/logs/audit.json"}


@patch(f"{G}.write_audit_log", side_effect=OSError("readonly fs"))
def test_log_audit_exception(mock_audit: MagicMock) -> None:
    result = _node_log_audit(_state())
    assert result == {"error": "readonly fs"}


@patch(f"{G}.log_langfuse_trace")
def test_log_trace_happy_returns_none(mock_trace: MagicMock) -> None:
    result = _node_log_trace(_state())
    assert result is None
    mock_trace.assert_called_once()


@patch(
    f"{G}.log_langfuse_trace",
    side_effect=ConnectionError("langfuse down"),
)
def test_log_trace_exception_warns_non_blocking(
    mock_trace: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="indicium_ai_agent.graph"):
        result = _node_log_trace(_state())
    assert result is None
    assert any(
        "log_trace failed (non-blocking)" in r.message for r in caplog.records
    )
    # Non-blocking: WARNING level, never ERROR/exception propagation
    assert all(r.levelno < logging.ERROR for r in caplog.records)


# --- Integration: halt-on-error through the compiled graph --------------------


def test_pipeline_halt_preserves_first_error(tmp_path: Path) -> None:
    """Early failure must skip downstream nodes, keep first error, run audit."""
    initial = _state()
    with (
        patch(f"{G}.check_and_sync_data", side_effect=RuntimeError("first")) as m_sync,
        patch(f"{G}.load_and_clean") as m_load,
        patch(f"{G}.compute_metrics") as m_metrics,
        patch(f"{G}.render_report") as m_render,
        patch(f"{G}.write_audit_log", return_value=str(tmp_path / "a.json")) as m_audit,
        patch(f"{G}.log_langfuse_trace"),
        patch(f"{G}.get_settings") as m_settings,
    ):
        m_settings.return_value.data_raw_dir = tmp_path
        m_settings.return_value.data_cache_dir = tmp_path
        result: ReportState = build_graph().invoke(initial)

    m_sync.assert_called_once()
    # Downstream work skipped entirely
    assert not m_load.called
    assert not m_metrics.called
    assert not m_render.called
    # First error preserved verbatim (not overwritten)
    assert result.get("error") == "first"
    # Audit still written for provenance
    assert m_audit.called
