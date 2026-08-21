"""Tests for the compute_metrics orchestrator (swap guard, isolation, fallbacks)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from indicium_ai_agent.metrics.compute_metrics import (
    _fallback_result,
    compute_metrics,
)

COMPUTE = "indicium_ai_agent.metrics.compute_metrics"


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    db = duckdb.connect(":memory:")
    db.execute("""
        CREATE TABLE srag AS SELECT * FROM (
            VALUES
                ('2026-01-05', 1, 1, 1, 1, 1, 'SP'),
                ('2026-01-10', 2, 1, 2, 1, 2, 'RJ'),
                ('2026-02-01', 1, 1, 1, 2, 1, 'SP'),
                ('2026-02-05', 2, 1, 1, 2, 2, 'RJ'),
                ('2026-02-08', 1, 1, 2, 1, 1, 'SP')
        ) AS t(DT_SIN_PRI, EVOLUCAO, HOSPITAL, UTI, VACINA_COV, VACINA, SG_UF)
    """)
    return db


def _mock_result(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "value": 1.0,
        "computable": True,
        "numerator": 1,
        "denominator": 100,
        "period": "p",
        "definition_ref": "x_v1",
        "query": "SELECT 1",
    }
    base.update(overrides)
    return base


# --- A. Happy path -----------------------------------------------------------


def test_compute_metrics_all_success(con: duckdb.DuckDBPyConnection) -> None:
    result = compute_metrics(con, "2026-01-01", "2026-02-28")
    metrics = result["metrics"]

    assert set(metrics.keys()) == {
        "case_growth_rate",
        "mortality_rate",
        "uti_admission_rate",
        "vaccination_coverage",
    }
    for key, metric in metrics.items():
        assert metric["definition_ref"] == f"{key}_v1"
        assert "SELECT" in metric["query"]
    # Fixture has resolvable cases -> rates computable
    assert metrics["mortality_rate"]["computable"] is True
    assert metrics["uti_admission_rate"]["computable"] is True
    assert isinstance(metrics["vaccination_coverage"]["value"], dict)


# --- B. Swapped dates --------------------------------------------------------


def _patch_all_success() -> Any:
    """Patch all four getters capturing their args."""
    return (
        patch(f"{COMPUTE}.get_case_growth_rate", return_value=_mock_result()),
        patch(f"{COMPUTE}.get_mortality_rate", return_value=_mock_result()),
        patch(
            f"{COMPUTE}.get_uti_admission_rate",
            return_value=_mock_result(),
        ),
        patch(
            f"{COMPUTE}.get_vaccination_coverage",
            return_value=_mock_result(),
        ),
    )


def test_swapped_dates_swaps_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mocks = _patch_all_success()
    fake_con = MagicMock()
    with mocks[0] as m_growth, mocks[1] as m_mort, mocks[2], mocks[3]:
        with caplog.at_level(logging.WARNING, logger=COMPUTE):
            compute_metrics(fake_con, "2026-03-01", "2026-01-01")

    assert any("Swapped" in r.message for r in caplog.records)
    # Mortality receives post-swap ascending order
    m_mort.assert_called_once_with(fake_con, "2026-01-01", "2026-03-01")
    # Growth uses the (swapped) later date as its window end
    m_growth.assert_called_once_with(fake_con, end_date_str="2026-03-01")


def test_normal_order_no_swap(caplog: pytest.LogCaptureFixture) -> None:
    mocks = _patch_all_success()
    with mocks[0], mocks[1], mocks[2], mocks[3]:
        with caplog.at_level(logging.WARNING, logger=COMPUTE):
            compute_metrics(MagicMock(), "2026-01-01", "2026-03-01")

    assert not any("Swapped" in r.message for r in caplog.records)


# --- C. _fallback_result unit contract ---------------------------------------


def test_fallback_scalar_not_computable() -> None:
    result = _fallback_result("2026-01-01 to 2026-01-31", "case_growth_rate_v1", 0, 0)
    assert result["value"] is None
    assert result["computable"] is False
    assert result["query"] == ""
    assert result["definition_ref"] == "case_growth_rate_v1"
    assert result["denominator"] == 0


def test_fallback_dict_numerator_preserved() -> None:
    result = _fallback_result(
        "p", "vaccination_coverage_v1", {"covid": 0, "flu": 0}
    )
    assert result["numerator"] == {"covid": 0, "flu": 0}


def test_fallback_explicit_denominator_still_not_computable() -> None:
    result = _fallback_result("p", "mortality_rate_v1", 5, denominator=10)
    assert result["denominator"] == 10
    assert result["computable"] is False


# --- D. Per-metric failure isolation -----------------------------------------


def test_case_growth_failure_period_computed(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with patch(
        f"{COMPUTE}.get_case_growth_rate",
        side_effect=RuntimeError("boom"),
    ):
        result = compute_metrics(con, "2026-01-01", "2026-02-10")

    fallback = result["metrics"]["case_growth_rate"]
    assert fallback["computable"] is False
    assert fallback["definition_ref"] == "case_growth_rate_v1"
    # 7-day window derived from DEFAULT_GROWTH_DAYS inside the handler
    assert fallback["period"] == "2026-02-03 to 2026-02-10"
    # Isolation: remaining metrics still succeed
    assert result["metrics"]["mortality_rate"]["computable"] is True
    assert result["metrics"]["uti_admission_rate"]["computable"] is True


def test_case_growth_failure_bad_end_date_inner_except(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Malformed end_date must fall back to the generic period string."""
    with patch(
        f"{COMPUTE}.get_case_growth_rate",
        side_effect=RuntimeError("boom"),
    ):
        result = compute_metrics(con, "2026-01-01", "bad-date")

    fallback = result["metrics"]["case_growth_rate"]
    assert fallback["computable"] is False
    assert fallback["period"] == "2026-01-01 to bad-date"


def test_mortality_failure_isolated(con: duckdb.DuckDBPyConnection) -> None:
    with patch(
        f"{COMPUTE}.get_mortality_rate",
        side_effect=RuntimeError("sql fail"),
    ):
        result = compute_metrics(con, "2026-01-01", "2026-02-28")

    mortality = result["metrics"]["mortality_rate"]
    assert mortality["computable"] is False
    assert mortality["value"] is None
    assert mortality["numerator"] == 0
    assert mortality["definition_ref"] == "mortality_rate_v1"
    # Others unaffected (growth window is legitimately non-computable
    # for this fixture: empty trailing 7d windows -> prior=0)
    assert result["metrics"]["uti_admission_rate"]["computable"] is True
    assert result["metrics"]["vaccination_coverage"]["computable"] is True


def test_uti_failure_isolated(con: duckdb.DuckDBPyConnection) -> None:
    with patch(
        f"{COMPUTE}.get_uti_admission_rate",
        side_effect=RuntimeError("sql fail"),
    ):
        result = compute_metrics(con, "2026-01-01", "2026-02-28")

    uti = result["metrics"]["uti_admission_rate"]
    assert uti["computable"] is False
    assert uti["definition_ref"] == "uti_admission_rate_v1"
    assert result["metrics"]["mortality_rate"]["computable"] is True


def test_vaccination_failure_dict_numerator(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with patch(
        f"{COMPUTE}.get_vaccination_coverage",
        side_effect=RuntimeError("sql fail"),
    ):
        result = compute_metrics(con, "2026-01-01", "2026-02-28")

    vaccination = result["metrics"]["vaccination_coverage"]
    assert vaccination["computable"] is False
    assert vaccination["numerator"] == {"covid": 0, "flu": 0}
    assert vaccination["definition_ref"] == "vaccination_coverage_v1"


def test_all_metrics_fail_returns_four_fallbacks(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with (
        patch(f"{COMPUTE}.get_case_growth_rate", side_effect=RuntimeError("x")),
        patch(f"{COMPUTE}.get_mortality_rate", side_effect=RuntimeError("x")),
        patch(
            f"{COMPUTE}.get_uti_admission_rate",
            side_effect=RuntimeError("x"),
        ),
        patch(
            f"{COMPUTE}.get_vaccination_coverage",
            side_effect=RuntimeError("x"),
        ),
    ):
        result = compute_metrics(con, "2026-01-01", "2026-02-28")

    for key in result["metrics"]:
        assert result["metrics"][key]["computable"] is False
        assert result["metrics"][key]["value"] is None


# --- E. METRIC_KEYS defensive completeness -----------------------------------


def test_metric_keys_defense_adds_missing(
    con: duckdb.DuckDBPyConnection,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from indicium_ai_agent.config.constants import METRIC_KEYS

    monkeypatch.setattr(
        f"{COMPUTE}.METRIC_KEYS",
        (*METRIC_KEYS, "extra_metric"),
    )
    with caplog.at_level(logging.WARNING, logger=COMPUTE):
        result = compute_metrics(con, "2026-01-01", "2026-02-28")

    assert "extra_metric" in result["metrics"]
    assert result["metrics"]["extra_metric"]["computable"] is False
    assert result["metrics"]["extra_metric"]["definition_ref"] == "extra_metric_v1"
    assert any(
        "Missing metric key: extra_metric" in r.message for r in caplog.records
    )
