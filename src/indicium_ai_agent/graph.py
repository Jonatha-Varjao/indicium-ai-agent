from __future__ import annotations

import logging
from typing import Any, cast

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from indicium_ai_agent.charts.generate_charts import generate_charts
from indicium_ai_agent.config.constants import MAX_RETRIES
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

logger = logging.getLogger(__name__)

# Node name constants — avoid stringly-typed duplication.
NODE_CHECK_AND_SYNC = "check_and_sync"
NODE_LOAD_AND_CLEAN = "load_and_clean"
NODE_COMPUTE_METRICS = "compute_metrics"
NODE_GENERATE_CHARTS = "generate_charts"
NODE_FETCH_NEWS = "fetch_news"
NODE_SANITIZE_NEWS = "sanitize_news"
NODE_SYNTHESIZE_NARRATIVE = "synthesize_narrative"
NODE_VALIDATE_NARRATIVE = "validate_narrative"
NODE_RENDER_REPORT = "render_report"
NODE_LOG_AUDIT = "log_audit"
NODE_LOG_TRACE = "log_trace"


def _node_check_and_sync(state: ReportState) -> dict[str, Any]:
    """Check freshness and sync CSV; returns paths and check result."""
    if state.get("error"):
        return {}
    try:
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
    except Exception as exc:
        logger.exception("check_and_sync failed: %s", exc)
        return {"error": str(exc)}


def _node_load_and_clean(state: ReportState) -> dict[str, Any]:
    """Load CSV, strip PII and register DuckDB table."""
    if state.get("error"):
        return {}
    try:
        result = load_and_clean(state["raw_csv_path"])
        return {
            "con": result["con"],
            "exclusion_log": result["exclusion_log"],
            "source_csv_hash": result["source_csv_hash"],
            "source_extraction_date": result["source_extraction_date"],
        }
    except Exception as exc:
        logger.exception("load_and_clean failed: %s", exc)
        return {"error": str(exc)}


def _node_compute_metrics(state: ReportState) -> dict[str, Any]:
    """Compute epidemiological metrics for the selected period."""
    if state.get("error"):
        return {}
    try:
        start = state["start_date"]
        end = state["end_date"]
        con = state.get("con")
        if con is None:
            raise ValueError("DuckDB connection missing in state['con']")
        result = compute_metrics(con, start, end)
        return {"metrics": result["metrics"]}
    except Exception as exc:
        logger.exception("compute_metrics failed: %s", exc)
        return {"error": str(exc)}


def _node_generate_charts(state: ReportState) -> dict[str, Any]:
    """Generate charts from DuckDB metrics."""
    if state.get("error"):
        return {}
    try:
        settings = get_settings()
        con = state.get("con")
        if con is None:
            raise ValueError("DuckDB connection missing for chart generation")
        result = generate_charts(con, settings.output_charts_dir, state.get("end_date"))
        return {"chart_paths": result}
    except Exception as exc:
        logger.exception("generate_charts failed: %s", exc)
        return {"error": str(exc)}


def _node_fetch_news(state: ReportState) -> dict[str, Any]:
    """Fetch contextual news for the metrics period."""
    if state.get("error"):
        return {}
    try:
        result = fetch_news(state["metrics"])
        return {"news_items": result["news_items"], "news_source": result["news_source"]}
    except Exception as exc:
        logger.exception("fetch_news failed: %s", exc)
        return {"error": str(exc)}


def _node_sanitize_news(state: ReportState) -> dict[str, Any]:
    """Sanitize fetched news for LLM consumption."""
    if state.get("error"):
        return {}
    try:
        result = sanitize_news(state["news_items"])
        return {
            "sanitized_news": result["sanitized_news"],
            "news_flagged": result["news_flagged"],
        }
    except Exception as exc:
        logger.exception("sanitize_news failed: %s", exc)
        return {"error": str(exc)}


def _node_synthesize_narrative(state: ReportState) -> dict[str, Any]:
    """Synthesize narrative from metrics and sanitized news."""
    if state.get("error"):
        return {}
    try:
        result = synthesize_narrative(
            state["metrics"], state["sanitized_news"], state["news_source"]
        )
        return {"narrative_draft": result["narrative_draft"]}
    except Exception as exc:
        logger.exception("synthesize_narrative failed: %s", exc)
        return {"error": str(exc)}


def _node_validate_narrative(state: ReportState) -> dict[str, Any]:
    """Validate narrative grounding and update retry counter."""
    if state.get("error"):
        return {}
    try:
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
    except Exception as exc:
        logger.exception("validate_narrative failed: %s", exc)
        return {"error": str(exc)}


def _node_render_report(state: ReportState) -> dict[str, Any]:
    """Render final Markdown report."""
    if state.get("error"):
        return {}
    try:
        result = render_report(
            metrics=cast(Any, state["metrics"]),
            narrative_validated=state["narrative_validated"],
            chart_paths=state["chart_paths"],
            news_items=cast(Any, state["news_items"]),
            exclusion_log=cast(Any, state["exclusion_log"]),
            validation_passed=state["validation_passed"],
            source_csv_hash=state["source_csv_hash"],
            source_extraction_date=state["source_extraction_date"],
            news_source=state["news_source"],
            run_id=state["run_id"],
        )
        return {"report_path": result["report_path"]}
    except Exception as exc:
        logger.exception("render_report failed: %s", exc)
        return {"error": str(exc)}


def _node_log_audit(state: ReportState) -> dict[str, Any]:
    """Write audit log JSON for the current run.

    Runs even when the pipeline already failed (audit provenance), but
    never overwrites an existing ``error`` with an audit failure.
    """
    try:
        path = write_audit_log(cast(dict[str, Any], state))
        return {"audit_log_path": path}
    except Exception as exc:
        logger.exception("log_audit failed: %s", exc)
        if state.get("error"):
            return {}
        return {"error": str(exc)}


def _node_log_trace(state: ReportState) -> None:
    """Emit Langfuse trace (best-effort, non-blocking)."""
    try:
        log_langfuse_trace(cast(dict[str, Any], state))
    except Exception as exc:
        logger.warning("log_trace failed (non-blocking): %s", exc)


def _should_retry(state: ReportState) -> str:
    """Decide whether narrative synthesis should be retried.

    Returns ``"continue"`` when validation passed or max retries reached,
    otherwise ``"retry"`` to loop back to synthesis. If pipeline already
    has an error, never retry — proceed to render/audit to preserve the
    original failure.

    Args:
        state: Current graph state containing ``validation_passed`` and
            ``retry_count``.

    Returns:
        Routing key for conditional edge: ``"continue"`` or ``"retry"``.
    """
    if state.get("error"):
        return "continue"
    if state.get("validation_passed", False) or state.get("retry_count", 0) >= MAX_RETRIES:
        return "continue"
    return "retry"


def build_graph() -> CompiledStateGraph[ReportState]:
    """Build and compile the SRAG report LangGraph.

    Constructs a linear pipeline with a conditional retry loop around
    narrative synthesis/validation. Uses ``MAX_RETRIES`` from
    ``config/constants.py`` to bound retries.

    Returns:
        Compiled graph ready for ``invoke``/``stream``.
    """
    graph: StateGraph[ReportState] = StateGraph(ReportState)

    graph.add_node(NODE_CHECK_AND_SYNC, _node_check_and_sync)
    graph.add_node(NODE_LOAD_AND_CLEAN, _node_load_and_clean)
    graph.add_node(NODE_COMPUTE_METRICS, _node_compute_metrics)
    graph.add_node(NODE_GENERATE_CHARTS, _node_generate_charts)
    graph.add_node(NODE_FETCH_NEWS, _node_fetch_news)
    graph.add_node(NODE_SANITIZE_NEWS, _node_sanitize_news)
    graph.add_node(NODE_SYNTHESIZE_NARRATIVE, _node_synthesize_narrative)
    graph.add_node(NODE_VALIDATE_NARRATIVE, _node_validate_narrative)
    graph.add_node(NODE_RENDER_REPORT, _node_render_report)
    graph.add_node(NODE_LOG_AUDIT, _node_log_audit)
    graph.add_node(NODE_LOG_TRACE, _node_log_trace)

    graph.set_entry_point(NODE_CHECK_AND_SYNC)
    graph.add_edge(NODE_CHECK_AND_SYNC, NODE_LOAD_AND_CLEAN)
    graph.add_edge(NODE_LOAD_AND_CLEAN, NODE_COMPUTE_METRICS)
    graph.add_edge(NODE_COMPUTE_METRICS, NODE_GENERATE_CHARTS)
    graph.add_edge(NODE_GENERATE_CHARTS, NODE_FETCH_NEWS)
    graph.add_edge(NODE_FETCH_NEWS, NODE_SANITIZE_NEWS)
    graph.add_edge(NODE_SANITIZE_NEWS, NODE_SYNTHESIZE_NARRATIVE)
    graph.add_edge(NODE_SYNTHESIZE_NARRATIVE, NODE_VALIDATE_NARRATIVE)
    graph.add_conditional_edges(
        NODE_VALIDATE_NARRATIVE,
        _should_retry,
        {"retry": NODE_SYNTHESIZE_NARRATIVE, "continue": NODE_RENDER_REPORT},
    )
    graph.add_edge(NODE_RENDER_REPORT, NODE_LOG_AUDIT)
    graph.add_edge(NODE_LOG_AUDIT, NODE_LOG_TRACE)
    graph.add_edge(NODE_LOG_TRACE, END)

    return graph.compile()
