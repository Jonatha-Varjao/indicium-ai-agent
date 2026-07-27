from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from indicium_ai_agent.config.metrics_spec import METRICS
from indicium_ai_agent.config.settings import get_settings


def _format_metric_row(metric_key: str, data: dict[str, Any]) -> str:
    meta = METRICS.get(metric_key, {})
    name = meta.get("name", metric_key)
    caveat = meta.get("caveat", "")

    if not data.get("computable", False):
        return f"| {name} | Dados insuficientes para cálculo neste período | — |"

    value = data.get("value", "—")
    period = data.get("period", "—")

    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in value.items()]
        value_str = "; ".join(parts)
    elif isinstance(value, float):
        value_str = f"{value:.4f}"
    else:
        value_str = str(value)

    note = f" ({caveat})" if caveat else ""
    return f"| {name} | {value_str} | {period}{note} |"


def _build_metrics_table(metrics: dict[str, Any]) -> str:
    lines = [
        "## Métricas",
        "",
        "| Métrica | Valor | Período |",
        "|---|---|---|",
    ]
    for key in (
        "case_growth_rate",
        "mortality_rate",
        "uti_admission_rate",
        "vaccination_coverage",
    ):
        if key in metrics:
            lines.append(_format_metric_row(key, metrics[key]))
    return "\n".join(lines) + "\n"


def _build_narrative_section(narrative: str, validation_passed: bool) -> str:
    lines = ["## Análise", "", narrative, ""]
    if not validation_passed:
        lines.append(
            "> ⚠️ Esta narrativa foi parcialmente validada — "
            "consulte a tabela de métricas oficiais para valores precisos.\n"
        )
    return "\n".join(lines)


def _build_charts_section(chart_paths: dict[str, str], output_reports_dir: Path) -> str:
    lines = ["## Gráficos", ""]
    for label, path in sorted(chart_paths.items()):
        rel = os.path.relpath(path, start=output_reports_dir)
        lines.append(f"![{label}]({rel})")
        lines.append("")
    return "\n".join(lines)


def _build_sources_section(news_items: list[dict[str, str]]) -> str:
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
    exclusion_log: dict[str, Any],
    news_source: str,
) -> str:
    lines = [
        "## Metodologia e Limitações",
        "",
        "- **Fonte dos dados**: Open DATASUS / SIVEP-Gripe",
        f"- **Data de extração**: {source_extraction_date}",
        f"- **Hash do arquivo**: `{source_csv_hash[:16]}...`",
        "",
        "### Exclusões aplicadas",
    ]

    pii = exclusion_log.get("pii_columns", {})
    present_pii = [k for k, v in pii.items() if v == "present_and_stripped"]
    if present_pii:
        lines.append(f"- Colunas com dados sensíveis removidas: {', '.join(present_pii)}")

    cols_not_found = exclusion_log.get("columns_not_found", {})
    if cols_not_found.get("columns"):
        lines.append(
            f"- Colunas esperadas não encontradas: "
            f"{', '.join(cols_not_found['columns'])}"
        )

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
    metrics: dict[str, Any],
    narrative_validated: str,
    chart_paths: dict[str, str],
    news_items: list[dict[str, str]],
    exclusion_log: dict[str, Any],
    validation_passed: bool,
    source_csv_hash: str,
    source_extraction_date: str,
    news_source: str,
    run_id: str,
) -> dict[str, str]:
    settings = get_settings()

    now = datetime.now(UTC)
    sections: list[str] = []

    sections.append("# Relatório de Vigilância SRAG\n")

    sections.append(_build_metrics_table(metrics))

    sections.append(_build_narrative_section(narrative_validated, validation_passed))

    sections.append(_build_charts_section(chart_paths, settings.output_reports_dir))

    sections.append(_build_sources_section(news_items))

    sections.append(_build_methodology_section(
        source_csv_hash, source_extraction_date, exclusion_log, news_source,
    ))

    sections.append(f"---\n*Relatório gerado em: {now.strftime('%d/%m/%Y %H:%M:%S')} — run_id: `{run_id}`*\n")

    report = "\n".join(sections)

    output_dir = settings.output_reports_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"relatorio_srag_{now.strftime('%Y%m%d_%H%M%S')}.md"
    path = output_dir / filename
    with open(path, "w") as f:
        f.write(report)

    return {"report_path": str(path)}
