from __future__ import annotations

import json
from pathlib import Path

from indicium_ai_agent.logging.audit_logger import write_audit_log


def _minimal_state() -> dict:
    return {
        "run_id": "test-run-001",
        "data_mode": "pinned",
        "data_check_result": {"action": "pinned_snapshot", "checked_at": "2026-07-20T00:00:00"},
        "source_csv_hash": "abc123",
        "source_extraction_date": "2026-07-20",
        "exclusion_log": {"pii_columns": {"NU_CPF": "present_and_stripped"}},
        "metrics": {
            "case_growth_rate": {
                "computable": True,
                "value": 15.5,
                "numerator": 30,
                "denominator": 20,
                "period": "2026-01-01 to 2026-02-01",
                "query": "SELECT ...",
            },
        },
        "chart_paths": {"daily": "/path/to/chart.png"},
        "news_source": "tavily",
        "news_flagged": False,
        "narrative_draft": "Narrative text here.",
        "validation_diff": {},
        "retry_count": 0,
        "validation_passed": True,
    }


def test_audit_log_creates_json(tmp_path: Path) -> None:
    state = _minimal_state()
    result = write_audit_log(state)
    path = Path(result)
    assert path.exists()
    assert path.suffix == ".json"


def test_audit_log_valid_json(tmp_path: Path) -> None:
    state = _minimal_state()
    result = write_audit_log(state)
    with open(result) as f:
        data = json.load(f)
    assert data["run_id"] == "test-run-001"


def test_audit_log_fields_complete(tmp_path: Path) -> None:
    state = _minimal_state()
    result = write_audit_log(state)
    with open(result) as f:
        data = json.load(f)

    assert "run_id" in data
    assert "timestamp" in data
    assert "data_mode" in data
    assert "data_check_result" in data
    assert "source_csv_hash" in data
    assert "source_extraction_date" in data
    assert "exclusion_log" in data
    assert "metrics" in data
    assert "news_source" in data
    assert "validation_diff" in data
    assert "retry_count" in data
    assert "validation_passed" in data


def test_audit_log_metric_queries(tmp_path: Path) -> None:
    state = _minimal_state()
    result = write_audit_log(state)
    with open(result) as f:
        data = json.load(f)
    metric = data["metrics"]["case_growth_rate"]
    assert metric["query"] == "SELECT ..."
    assert metric["value"] == 15.5


def test_audit_log_filename_contains_run_id(tmp_path: Path) -> None:
    state = _minimal_state()
    result = write_audit_log(state)
    assert "test-run-001" in Path(result).name
