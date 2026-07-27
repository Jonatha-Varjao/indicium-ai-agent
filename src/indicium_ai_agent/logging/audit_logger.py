from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from indicium_ai_agent.config.settings import get_settings


def _extract_metric_audit(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, data in metrics.items():
        result[key] = {
            "value": data.get("value"),
            "computable": data.get("computable", False),
            "numerator": data.get("numerator"),
            "denominator": data.get("denominator"),
            "period": data.get("period", ""),
            "definition_ref": data.get("definition_ref", ""),
            "query": data.get("query", ""),
        }
    return result


def write_audit_log(state: dict[str, Any]) -> str:
    settings = get_settings()
    audit_dir = settings.output_audit_dir
    audit_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "run_id": state.get("run_id", "unknown"),
        "timestamp": datetime.now(UTC).isoformat(),
        "data_mode": state.get("data_mode"),
        "data_check_result": state.get("data_check_result"),
        "source_csv_hash": state.get("source_csv_hash"),
        "source_extraction_date": state.get("source_extraction_date"),
        "exclusion_log": state.get("exclusion_log"),
        "metrics": _extract_metric_audit(state.get("metrics", {})),
        "chart_paths": state.get("chart_paths"),
        "news_source": state.get("news_source"),
        "news_flagged": state.get("news_flagged", False),
        "narrative_draft": state.get("narrative_draft", ""),
        "validation_diff": state.get("validation_diff"),
        "retry_count": state.get("retry_count", 0),
        "validation_passed": state.get("validation_passed", False),
    }

    filename = f"audit_log_{state.get('run_id', 'unknown')}.json"
    path = audit_dir / filename
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return str(path)
