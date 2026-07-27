from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from indicium_ai_agent.render.render_report import render_report


class _MockSettings:
    def __init__(self, output_reports_dir: Path) -> None:
        self.output_reports_dir = output_reports_dir


def _minimal_kwargs(report_dir: Path) -> dict:
    return {
        "metrics": {
            "case_growth_rate": {
                "computable": True,
                "value": 15.5,
                "numerator": 30,
                "denominator": 20,
                "period": "2026-01-01 to 2026-02-01",
            },
            "mortality_rate": {
                "computable": True,
                "value": 0.05,
                "numerator": 5,
                "denominator": 100,
                "period": "2026-01-01 to 2026-02-01",
            },
            "uti_admission_rate": {
                "computable": False,
                "value": None,
            },
            "vaccination_coverage": {
                "computable": True,
                "value": {"covid": 0.85, "flu": 0.72},
                "numerator": {"covid": 85, "flu": 72},
                "denominator": 100,
                "period": "2026-01-01 to 2026-02-01",
            },
        },
        "narrative_validated": "Houve um aumento de casos no período analisado.",
        "chart_paths": {"daily": str(Path.cwd() / "outputs" / "charts" / "daily_cases.png")},
        "news_items": [
            {
                "title": "SRAG News",
                "url": "https://fiocruz.br/srag",
                "source": "Fiocruz",
                "published_date": "",
                "snippet": "",
            }
        ],
        "exclusion_log": {
            "pii_columns": {"NU_CPF": "present_and_stripped", "NU_CNS": "already_absent"},
            "output": {"rows": 100},
        },
        "validation_passed": True,
        "source_csv_hash": "abc123def456",
        "source_extraction_date": "2026-07-20",
        "news_source": "tavily",
        "run_id": "test-run-001",
    }


def test_render_report_creates_md_file(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    path = Path(result["report_path"])
    assert path.exists()
    assert path.suffix == ".md"


def test_render_report_contains_metrics_table(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    content = Path(result["report_path"]).read_text()
    assert "| Métrica | Valor | Período |" in content
    assert "Taxa de aumento de casos" in content
    assert "Taxa de mortalidade" in content
    assert "Taxa de vacinação" in content


def test_render_report_non_computable(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    content = Path(result["report_path"]).read_text()
    assert "Dados insuficientes" in content
    assert "Taxa de internação em UTI" in content


def test_render_report_contains_narrative(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    content = Path(result["report_path"]).read_text()
    assert "Houve um aumento de casos" in content


def test_render_report_contains_charts(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    (tmp_path / "outputs" / "charts").mkdir(parents=True)
    chart = tmp_path / "outputs" / "charts" / "daily_cases.png"
    chart.write_text("fake-png")
    kwargs["chart_paths"] = {"daily": str(chart)}
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    content = Path(result["report_path"]).read_text()
    assert "daily_cases.png" in content


def test_render_report_contains_sources(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    content = Path(result["report_path"]).read_text()
    assert "SRAG News" in content
    assert "https://fiocruz.br/srag" in content


def test_render_report_methodology_section(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    content = Path(result["report_path"]).read_text()
    assert "Metodologia e Limitações" in content
    assert "abc123def456" in content
    assert "NU_CPF" in content


def test_render_report_vaccination_caveat(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    content = Path(result["report_path"]).read_text()
    assert "casos hospitalizados" in content


def test_render_report_timestamped_filename(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    path = Path(result["report_path"])
    assert "relatorio_srag_" in path.name
    assert path.suffix == ".md"


def test_render_report_unavailable_news(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    kwargs = _minimal_kwargs(out)
    kwargs["news_source"] = "unavailable"
    kwargs["news_items"] = []
    with patch("indicium_ai_agent.render.render_report.get_settings", return_value=_MockSettings(out)):
        result = render_report(**kwargs)
    content = Path(result["report_path"]).read_text()
    assert "Nenhuma notícia relevante encontrada" in content
