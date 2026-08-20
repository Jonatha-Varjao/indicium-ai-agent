"""Render SRAG surveillance report to Markdown.

Builds a Markdown report from computed metrics, validated narrative,
chart paths, news items, and provenance metadata.

The module keeps the public ``render_report`` signature for backward
compatibility while exposing typed helpers and ``TypedDict`` definitions
for stricter static analysis.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from indicium_ai_agent.config.constants import METRIC_KEYS
from indicium_ai_agent.config.metrics_spec import METRICS
from indicium_ai_agent.config.settings import get_settings
from indicium_ai_agent.narrative._utils import format_metric_value


class MetricData(TypedDict, total=False):
    """Per-metric result payload."""

    computable: bool
    value: Any
    numerator: Any
    denominator: Any
    period: str
    definition_ref: str
    query: str


class NewsItem(TypedDict, total=False):
    """News reference item."""

    title: str
    url: str
    source: str
    published_date: str
    snippet: str


class ColumnsNotFound(TypedDict, total=False):
    """Columns-not-found section of exclusion log."""

    columns: list[str]


class ExclusionLog(TypedDict, total=False):
    """Provenance log for exclusions / PII stripping."""

    pii_columns: dict[str, str]
    columns_not_found: ColumnsNotFound
    output: dict[str, Any]


class RenderReportResult(TypedDict):
    """Return value of :func:`render_report`."""

    report_path: str


class RenderParams(TypedDict, total=False):
    """Typed grouping of :func:`render_report` parameters.

    Kept for documentation and for callers that prefer ``render_report(**params)``.
    The public signature retains explicit parameters for backward compatibility.
    """

    metrics: dict[str, MetricData]
    narrative_validated: str
    chart_paths: dict[str, str]
    news_items: list[NewsItem]
    exclusion_log: ExclusionLog
    validation_passed: bool
    source_csv_hash: str
    source_extraction_date: str
    news_source: str
    run_id: str


def _format_metric_row(metric_key: str, data: MetricData) -> str:
    """Format a single metric as a Markdown table row.

    Args:
        metric_key: Canonical metric key (e.g. ``case_growth_rate``).
        data: Metric payload with ``computable``, ``value``, and ``period``.

    Returns:
        Markdown table row string.
    """
    meta = METRICS.get(metric_key, {})
    name = str(meta.get("name", metric_key))
    caveat = str(meta.get("caveat", ""))

    if not data.get("computable", False):
        return f"| {name} | Dados insuficientes para cálculo neste período | — |"

    value = data.get("value", "—")
    period = data.get("period", "—")

    value_str = format_metric_value(value)

    note = f" ({caveat})" if caveat else ""
    return f"| {name} | {value_str} | {period}{note} |"


def _build_metrics_table(metrics: dict[str, MetricData]) -> str:
    """Build the metrics Markdown table.

    Args:
        metrics: Mapping from metric key to :class:`MetricData`.

    Returns:
        Markdown section string.
    """
    lines = [
        "## Métricas",
        "",
        "| Métrica | Valor | Período |",
        "|---|---|---|",
    ]
    for key in METRIC_KEYS:
        if key in metrics:
            lines.append(_format_metric_row(key, metrics[key]))
    return "\n".join(lines) + "\n"


def _build_narrative_section(narrative: str, validation_passed: bool) -> str:
    """Build the narrative analysis section.

    Args:
        narrative: Validated narrative text.
        validation_passed: Whether LLM validation succeeded.

    Returns:
        Markdown section string.
    """
    lines = ["## Análise", "", narrative, ""]
    if not validation_passed:
        lines.append(
            "> ⚠️ Esta narrativa foi parcialmente validada — "
            "consulte a tabela de métricas oficiais para valores precisos.\n"
        )
    return "\n".join(lines)


def _build_charts_section(chart_paths: dict[str, str], output_reports_dir: Path) -> str:
    """Build the charts Markdown section.

    Uses :meth:`Path.relative_to` for ``output_reports_dir``-relative links
    with a fallback to :func:`os.path.relpath` when paths are on different
    drives (``ValueError``).

    Args:
        chart_paths: Mapping from chart label to absolute file path.
        output_reports_dir: Base directory for relative link calculation.

    Returns:
        Markdown section string.
    """
    lines = ["## Gráficos", ""]
    for label, path in sorted(chart_paths.items()):
        try:
            rel = str(Path(path).relative_to(output_reports_dir))
        except ValueError:
            rel = os.path.relpath(path, start=output_reports_dir)
        lines.append(f"![{label}]({rel})")
        lines.append("")
    return "\n".join(lines)


def _build_sources_section(news_items: list[NewsItem]) -> str:
    """Build the sources / references section.

    Args:
        news_items: List of news reference dicts.

    Returns:
        Markdown section string.
    """
    if not news_items:
        return "## Fontes\n\nNenhuma notícia relevante encontrada neste período.\n"

    lines = ["## Fontes e Referências", ""]
    for i, item in enumerate(news_items, 1):
        title = item.get("title", "")
        url = item.get("url", "")
        source = item.get("source", "")
        lines.append(f"{i}. **{title}** — {source} ({url})")
    return "\n".join(lines) + "\n"


def _build_methodology_section(
    source_csv_hash: str,
    source_extraction_date: str,
    exclusion_log: ExclusionLog,
    news_source: str,
) -> str:
    """Build the methodology and limitations section.

    Args:
        source_csv_hash: Hex hash of the source CSV.
        source_extraction_date: Extraction date string.
        exclusion_log: Provenance log with PII and missing-column info.
        news_source: News source identifier (``unavailable`` adds a note).

    Returns:
        Markdown section string.
    """
    lines = [
        "## Metodologia e Limitações",
        "",
        "- **Fonte dos dados**: Open DATASUS / SIVEP-Gripe",
        f"- **Data de extração**: {source_extraction_date}",
        f"- **Hash do arquivo**: `{source_csv_hash[:16]}...`",
        "",
        "### Exclusões aplicadas",
    ]

    pii = exclusion_log.get("pii_columns") or {}
    present_pii = [k for k, v in pii.items() if v == "present_and_stripped"]
    if present_pii:
        lines.append(f"- Colunas com dados sensíveis removidas: {', '.join(present_pii)}")

    cols_not_found = exclusion_log.get("columns_not_found") or {}
    columns_raw = cols_not_found.get("columns") if isinstance(cols_not_found, dict) else None
    if isinstance(columns_raw, list):
        lines.append(f"- Colunas esperadas não encontradas: {', '.join(columns_raw)}")

    if news_source == "unavailable":
        lines.append("")
        lines.append(
            "### Notícias\n"
            "Não foi possível obter notícias neste período. "
            "A análise baseia-se exclusivamente nas métricas disponíveis."
        )

    lines.append("")
    lines.append(
        "### Vacinação\n"
        "As taxas de vacinação reportadas referem-se à proporção de "
        "casos hospitalizados com esquema vacinal completo (VACINA_COV e VACINA). "
        "Não representam cobertura populacional."
    )

    return "\n".join(lines) + "\n"


def render_report(
    metrics: dict[str, MetricData],
    narrative_validated: str,
    chart_paths: dict[str, str],
    news_items: list[NewsItem],
    exclusion_log: ExclusionLog,
    validation_passed: bool,
    source_csv_hash: str,
    source_extraction_date: str,
    news_source: str,
    run_id: str,
) -> RenderReportResult:
    """Render the full SRAG surveillance report to Markdown.

    The function keeps an explicit parameter list for backward compatibility
    (see :class:`RenderParams` for a typed grouping alternative).

    Args:
        metrics: Computed metrics keyed by canonical name.
        narrative_validated: Validated narrative text.
        chart_paths: Chart label to absolute path mapping.
        news_items: News references.
        exclusion_log: Provenance exclusion log.
        validation_passed: Whether narrative validation passed.
        source_csv_hash: Source CSV hash.
        source_extraction_date: Source extraction date.
        news_source: News source identifier.
        run_id: Pipeline run identifier.

    Returns:
        Mapping with ``report_path`` pointing to the written Markdown file.

    Raises:
        OSError: If the output directory cannot be created or the report
            cannot be written.
    """
    settings = get_settings()

    now = datetime.now(UTC)
    sections: list[str] = []

    sections.append("# Relatório de Vigilância SRAG\n")

    sections.append(_build_metrics_table(metrics))

    sections.append(_build_narrative_section(narrative_validated, validation_passed))

    sections.append(_build_charts_section(chart_paths, settings.output_reports_dir))

    sections.append(_build_sources_section(news_items))

    sections.append(
        _build_methodology_section(
            source_csv_hash,
            source_extraction_date,
            exclusion_log,
            news_source,
        )
    )

    timestamp = now.strftime("%d/%m/%Y %H:%M:%S")
    sections.append(f"---\n*Relatório gerado em: {timestamp} — run_id: `{run_id}`*\n")

    report = "\n".join(sections)

    output_dir = settings.output_reports_dir
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"Failed to create output directory {output_dir}: {exc}") from exc

    filename = f"relatorio_srag_{now.strftime('%Y%m%d_%H%M%S')}.md"
    path = output_dir / filename
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
    except OSError as exc:
        raise OSError(f"Failed to write report to {path}: {exc}") from exc

    return {"report_path": str(path)}
