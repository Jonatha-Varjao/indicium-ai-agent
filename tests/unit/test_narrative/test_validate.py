from __future__ import annotations

from indicium_ai_agent.narrative.validate import (
    canonicalize_number,
    check_numeric_grounding,
    check_source_grounding,
    validate_narrative,
)


def test_canonicalize_number_simple() -> None:
    assert canonicalize_number("15.5") == 15.5


def test_canonicalize_number_comma_decimal() -> None:
    assert canonicalize_number("15,5") == 15.5


def test_canonicalize_number_percentage() -> None:
    assert canonicalize_number("15.5%") == 15.5


def test_canonicalize_number_invalid() -> None:
    assert canonicalize_number("abc") is None


def test_numeric_grounding_passes() -> None:
    narrative = "A taxa de aumento foi de 15.5%."
    metrics = {
        "case_growth_rate": {
            "computable": True,
            "value": 15.5,
        },
    }
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is True
    assert diffs == []


def test_numeric_grounding_catches_invented() -> None:
    narrative = "A taxa de aumento foi de 99.9%."
    metrics = {
        "case_growth_rate": {
            "computable": True,
            "value": 15.5,
        },
    }
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is False
    assert len(diffs) == 1
    assert diffs[0]["value"] == 99.9


def test_numeric_grounding_rounding_tolerance() -> None:
    narrative = "A taxa de mortalidade foi de 0.154."
    metrics = {
        "mortality_rate": {
            "computable": True,
            "value": 0.1539,
        },
    }
    ok, _diffs = check_numeric_grounding(narrative, metrics)
    assert ok is True


def test_numeric_grounding_non_computable() -> None:
    narrative = "Dados insuficientes para cálculo."
    metrics = {
        "mortality_rate": {
            "computable": False,
            "value": None,
        },
    }
    ok, _diffs = check_numeric_grounding(narrative, metrics)
    assert ok is True


def test_source_grounding_passes() -> None:
    narrative = "Segundo a Fiocruz (https://fiocruz.br/srag)."
    news_items = [
        {"url": "https://fiocruz.br/srag", "source": "Fiocruz"},
    ]
    ok, diffs = check_source_grounding(narrative, news_items)
    assert ok is True
    assert diffs == []


def test_source_grounding_catches_hallucination() -> None:
    narrative = "Segundo https://noticiasfalsas.com.br."
    news_items = [
        {"url": "https://fiocruz.br/srag", "source": "Fiocruz"},
    ]
    ok, diffs = check_source_grounding(narrative, news_items)
    assert ok is False
    assert len(diffs) == 1
    assert diffs[0]["cited"] == "https://noticiasfalsas.com.br"


def test_source_grounding_no_urls() -> None:
    narrative = "Texto sem URLs."
    news_items: list[dict[str, str]] = []
    ok, _diffs = check_source_grounding(narrative, news_items)
    assert ok is True


def test_validate_passes() -> None:
    result = validate_narrative(
        narrative_draft="A taxa foi de 15.5%.",
        metrics={
            "case_growth_rate": {
                "computable": True,
                "value": 15.5,
            },
        },
        news_items=[],
        retry_count=0,
    )
    assert result["validation_passed"] is True
    assert result["narrative_validated"] == "A taxa foi de 15.5%."


def test_validate_fails_and_retries() -> None:
    result = validate_narrative(
        narrative_draft="A taxa foi de 99.9%.",
        metrics={
            "case_growth_rate": {
                "computable": True,
                "value": 15.5,
            },
        },
        news_items=[],
        retry_count=0,
    )
    assert result["validation_passed"] is False
    assert result["retry_count"] == 1
    assert "numeric_mismatches" in result["validation_diff"]


def test_validate_graceful_degradation_after_max_retries() -> None:
    narrative = "A taxa foi de 99.9%. Fonte: https://falso.com."
    result = validate_narrative(
        narrative_draft=narrative,
        metrics={
            "case_growth_rate": {
                "computable": True,
                "value": 15.5,
            },
        },
        news_items=[],
        retry_count=3,
    )
    assert result["validation_passed"] is False
    assert "parcialmente validada" in result["narrative_validated"].lower()
    assert "99.9%" not in result["narrative_validated"]
