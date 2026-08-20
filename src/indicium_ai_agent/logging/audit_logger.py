from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypedDict

from indicium_ai_agent.config.settings import get_settings
from indicium_ai_agent.state import ReportState

logger = logging.getLogger(__name__)


class AuditMetric(TypedDict, total=False):
    """Typed metric entry for audit payload."""

    value: Any
    computable: bool
    numerator: Any
    denominator: Any
    period: str
    definition_ref: str
    query: str


class AuditPayload(TypedDict, total=False):
    """Typed payload for audit log JSON."""

    run_id: str
    timestamp: str
    data_mode: Any
    data_check_result: Any
    source_csv_hash: Any
    source_extraction_date: Any
    exclusion_log: Any
    metrics: dict[str, AuditMetric]
    chart_paths: Any
    news_source: Any
    news_flagged: bool
    narrative_draft: str
    validation_diff: Any
    retry_count: int
    validation_passed: bool


def _extract_metric_audit(metrics: dict[str, Any]) -> dict[str, AuditMetric]:
    """Extract auditable fields from computed metrics.

    Args:
        metrics: Computed metrics dict.

    Returns:
        Filtered metrics with only auditable fields.
    """
    result: dict[str, AuditMetric] = {}
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


def write_audit_log(state: ReportState | dict[str, Any]) -> str:
    """Write audit log JSON for the report run.

    Non-blocking: filesystem errors are logged as warnings and do not raise.

    Args:
        state: Pipeline report state or dict with run metadata.

    Returns:
        Path to the audit log file as string.
    """
    settings = get_settings()
    audit_dir = settings.output_audit_dir
    audit_dir.mkdir(parents=True, exist_ok=True)

    payload: AuditPayload = {
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
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                payload,
                f,
                indent=2,
                default=lambda o: o.value if isinstance(o, Enum) else str(o),
            )
    except OSError as exc:
        logger.warning("audit log write failed (non-blocking): %s", exc)
    return str(path)
