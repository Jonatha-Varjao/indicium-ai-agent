from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph  # type: ignore[attr-defined]

from indicium_ai_agent.charts.generate_charts import generate_charts
from indicium_ai_agent.config.settings import get_settings
from indicium_ai_agent.data.check_sync import check_and_sync_data
from indicium_ai_agent.data.load_clean import load_and_clean
from indicium_ai_agent.logging.audit_logger import write_audit_log
from indicium_ai_agent.logging.log_trace import log_langfuse_trace
from indicium_ai_agent.metrics.compute_metrics import compute_metrics
from indicium_ai_agent.narrative.synthesize import synthesize_narrative
from indicium_ai_agent.narrative.validate import validate_narrative
from indicium_ai_agent.news.fetch_news import fetch_news
from indicium_ai_agent.news.sanitize_news import sanitize_news
from indicium_ai_agent.render.render_report import render_report
from indicium_ai_agent.state import ReportState


def _node_check_and_sync(state: ReportState) -> dict[str, Any]:
    settings = get_settings()
    result = check_and_sync_data(
        data_mode=state["data_mode"],
        raw_dir=settings.data_raw_dir,
        cache_dir=settings.data_cache_dir,
        resource_url=state["data_source_url"],
    )
    return {
        "raw_csv_path": result["raw_csv_path"],
        "data_check_result": result["data_check_result"],
    }


def _node_load_and_clean(state: ReportState) -> dict[str, Any]:
    result = load_and_clean(state["raw_csv_path"])
    return {
        "con": result["con"],
        "exclusion_log": result["exclusion_log"],
        "source_csv_hash": result["source_csv_hash"],
        "source_extraction_date": result["source_extraction_date"],
    }


def _node_compute_metrics(state: ReportState) -> dict[str, Any]:
    start = state["start_date"]
    end = state["end_date"]
    result = compute_metrics(state["con"], start, end)
    return {"metrics": result["metrics"]}


def _node_generate_charts(state: ReportState) -> dict[str, Any]:
    settings = get_settings()
    result = generate_charts(state["con"], settings.output_charts_dir, state.get("end_date"))
    return {"chart_paths": result}


def _node_fetch_news(state: ReportState) -> dict[str, Any]:
    result = fetch_news(state["metrics"])
    return {"news_items": result["news_items"], "news_source": result["news_source"]}


def _node_sanitize_news(state: ReportState) -> dict[str, Any]:
    result = sanitize_news(state["news_items"])
    return {"sanitized_news": result["sanitized_news"], "news_flagged": result["news_flagged"]}


def _node_synthesize_narrative(state: ReportState) -> dict[str, Any]:
    result = synthesize_narrative(
        state["metrics"], state["sanitized_news"], state["news_source"]
    )
    return {"narrative_draft": result["narrative_draft"]}


def _node_validate_narrative(state: ReportState) -> dict[str, Any]:
    result = validate_narrative(
        narrative_draft=state["narrative_draft"],
        metrics=state["metrics"],
        news_items=state["news_items"],
        retry_count=state.get("retry_count", 0),
    )
    return {
        "validation_passed": result["validation_passed"],
        "narrative_validated": result["narrative_validated"],
        "validation_diff": result["validation_diff"],
        "retry_count": result["retry_count"],
    }


def _node_render_report(state: ReportState) -> dict[str, Any]:
    result = render_report(
        metrics=state["metrics"],
        narrative_validated=state["narrative_validated"],
        chart_paths=state["chart_paths"],
        news_items=state["news_items"],
        exclusion_log=state["exclusion_log"],
        validation_passed=state["validation_passed"],
        source_csv_hash=state["source_csv_hash"],
        source_extraction_date=state["source_extraction_date"],
        news_source=state["news_source"],
        run_id=state["run_id"],
    )
    return {"report_path": result["report_path"]}


def _node_log_audit(state: ReportState) -> dict[str, Any]:
    path = write_audit_log(state)  # type: ignore[arg-type]
    return {"audit_log_path": path}


def _node_log_trace(state: ReportState) -> None:
    log_langfuse_trace(state)  # type: ignore[arg-type]


def _should_retry(state: ReportState) -> str:
    if state.get("validation_passed", False) or state.get("retry_count", 0) >= 3:
        return "continue"
    return "retry"


def build_graph() -> CompiledStateGraph:  # type: ignore[return-value]
    graph: StateGraph = StateGraph(ReportState)  # type: ignore[var-annotated]

    graph.add_node("check_and_sync", _node_check_and_sync)
    graph.add_node("load_and_clean", _node_load_and_clean)
    graph.add_node("compute_metrics", _node_compute_metrics)
    graph.add_node("generate_charts", _node_generate_charts)
    graph.add_node("fetch_news", _node_fetch_news)
    graph.add_node("sanitize_news", _node_sanitize_news)
    graph.add_node("synthesize_narrative", _node_synthesize_narrative)
    graph.add_node("validate_narrative", _node_validate_narrative)
    graph.add_node("render_report", _node_render_report)
    graph.add_node("log_audit", _node_log_audit)
    graph.add_node("log_trace", _node_log_trace)

    graph.set_entry_point("check_and_sync")
    graph.add_edge("check_and_sync", "load_and_clean")
    graph.add_edge("load_and_clean", "compute_metrics")
    graph.add_edge("compute_metrics", "generate_charts")
    graph.add_edge("generate_charts", "fetch_news")
    graph.add_edge("fetch_news", "sanitize_news")
    graph.add_edge("sanitize_news", "synthesize_narrative")
    graph.add_edge("synthesize_narrative", "validate_narrative")
    graph.add_conditional_edges(
        "validate_narrative",
        _should_retry,
        {"retry": "synthesize_narrative", "continue": "render_report"},
    )
    graph.add_edge("render_report", "log_audit")
    graph.add_edge("log_audit", "log_trace")
    graph.add_edge("log_trace", END)

    return graph.compile()
