#!/usr/bin/env python3
"""CLI entry point for the SRAG Surveillance Report pipeline.

Usage:
    python scripts/run_report.py
    python scripts/run_report.py --start-date 2026-01-01 --end-date 2026-07-27
    DATA_MODE=live python scripts/run_report.py

Loads configuration from .env, builds the LangGraph pipeline,
executes all nodes (0-9), and prints a summary of the results.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta

from indicium_ai_agent.config.settings import DataMode, get_settings
from indicium_ai_agent.graph import build_graph
from indicium_ai_agent.logging.log_trace import create_langfuse_handler
from indicium_ai_agent.state import ReportState


def _resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    end = date.fromisoformat(args.end_date) if args.end_date else datetime.now(UTC).date()
    start = date.fromisoformat(args.start_date) if args.start_date else end - timedelta(days=365)
    return start.isoformat(), end.isoformat()


def _print_summary(state: ReportState) -> None:
    print(f"\n{'='*60}")
    print("RELATÓRIO SRAG — RESUMO")
    print(f"{'='*60}")
    print(f"  Run ID:          {state.get('run_id', 'N/A')}")
    print(f"  Modo de dados:   {state.get('data_mode', 'N/A')}")
    print(f"  Ação dos dados:  {state.get('data_check_result', {}).get('action', 'N/A')}")

    metrics = state.get("metrics", {})
    print("\n  Métricas:")
    for key, data in metrics.items():
        if data.get("computable", False):
            value = data.get("value")
            if isinstance(value, dict):
                value_str = "; ".join(f"{k}={v}" for k, v in value.items())
            else:
                value_str = str(value)
            print(f"    - {key}: {value_str}")
        else:
            print(f"    - {key}: Dados insuficientes")

    print(f"\n  Narrativa validada: {state.get('validation_passed', False)}")
    print(f"  Tentativas:         {state.get('retry_count', 0)}")
    print(f"  Gráficos:           {state.get('chart_paths', {})}")
    print(f"  Fontes de notícias: {state.get('news_source', 'N/A')}")

    print(f"\n  Relatório:  {state.get('report_path', 'N/A')}")
    print(f"  Audit log:  {state.get('audit_log_path', 'N/A')}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="SRAG Surveillance Report Generator")
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="YYYY-MM-DD (default: 12 months before end-date)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    settings = get_settings()
    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    start_date, end_date = _resolve_dates(args)

    graph = build_graph()

    langfuse_handler = create_langfuse_handler()
    invoke_config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}

    initial_state: ReportState = {
        "data_mode": DataMode(settings.data_mode.value),
        "data_source_url": settings.datasus_resource_url,
        "start_date": start_date,
        "end_date": end_date,
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
        "run_id": run_id,
        "source_csv_hash": "",
        "source_extraction_date": "",
        "timezone": settings.timezone,
        "report_path": "",
        "audit_log_path": "",
    }

    result: ReportState = graph.invoke(initial_state, invoke_config)  # type: ignore[typeddict-item, call-overload, assignment]

    if langfuse_handler:
        from langfuse import get_client  # type: ignore[import-untyped]
        get_client().flush()

    _print_summary(result)

    if result.get("error"):
        print(f"\n[error] pipeline failed: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
