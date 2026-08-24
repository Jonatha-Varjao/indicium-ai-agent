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


# --- PT-BR conventions (regressions from real pipeline run) ------------------


def test_canonicalize_number_thousands_separator() -> None:
    """Dot-grouped integers are PT-BR thousands, not decimals."""
    assert canonicalize_number("7.485") == 7485.0
    assert canonicalize_number("129.373") == 129373.0
    assert canonicalize_number("161.360") == 161360.0


def test_canonicalize_number_leading_zero_is_decimal() -> None:
    """'0.154' can never be a count — leading block '0' forces decimal."""
    assert canonicalize_number("0.154") == 0.154
    assert canonicalize_number("0.0579") == 0.0579


def test_canonicalize_number_mixed_thousands_decimal() -> None:
    assert canonicalize_number("1.234,56") == 1234.56


def test_numeric_grounding_accepts_ptbr_counts() -> None:
    """Counts cited with thousand separators must ground on numerators."""
    narrative = (
        "Foram 7.485 óbitos em 129.373 casos resolvidos, com "
        "40.884 admissões em UTI."
    )
    metrics = {
        "mortality_rate": {
            "computable": True,
            "value": 0.0579,
            "numerator": 7485,
            "denominator": 129373,
        },
        "uti_admission_rate": {
            "computable": True,
            "value": 0.2534,
            "numerator": 40884,
            "denominator": 161360,
        },
    }
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is True, diffs


def test_numeric_grounding_accepts_negative_magnitude() -> None:
    """Negative rates phrased as reduction magnitudes must pass."""
    narrative = "Houve redução de 78,12% nos casos."
    metrics = {
        "case_growth_rate": {"computable": True, "value": -78.12},
    }
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is True, diffs


def test_numeric_grounding_rejects_wrong_direction() -> None:
    """Opposite trend wording must NOT ground a negative metric.

    Review regression: sign-blind abs() matching accepted
    'aumento de 78,12%' for value -78.12, publishing the opposite
    epidemiological trend as validated.
    """
    narrative = "Houve aumento de 78,12% nos casos."
    metrics = {
        "case_growth_rate": {"computable": True, "value": -78.12},
    }
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is False
    assert diffs and diffs[0]["raw"] == "78,12%"


def test_numeric_grounding_accepts_signed_literal_without_direction_word() -> None:
    """Explicit '-N' literals carry their own sign; no verb needed."""
    narrative = "observou-se variação de -78,1200 na taxa de casos."
    metrics = {
        "case_growth_rate": {"computable": True, "value": -78.12},
    }
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is True, diffs


def test_unsupported_duration_is_grounded_not_skipped() -> None:
    """Review regression: '999 dias' previously bypassed grounding."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    text = "pacientes com internação média de 999 dias."
    extracted = _extract_all_numbers(text)
    assert ("999", 999.0, extracted[0][2]) in extracted

    metrics = {
        "mortality_rate": {"computable": True, "value": 0.0579},
    }
    ok, diffs = check_numeric_grounding(text, metrics)
    assert ok is False
    assert any(d["raw"] == "999" for d in diffs)


def test_supported_duration_range_still_skipped() -> None:
    """Documented windows (7 / 14 days) remain contextual."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    text = (
        "dados entre 13 e 20 de julho; últimos 7 a 14 dias "
        "sujeitos a subnotificação."
    )
    assert _extract_all_numbers(text) == []


def test_unsupported_duration_range_surfaces_both_bounds() -> None:
    """'3 a 5 dias' fabricates quantities — both bounds must be checked."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    text = "tempo de internação variando de 3 a 5 dias."
    raws = {raw for raw, _v, _s in _extract_all_numbers(text)}
    assert {"3", "5"} <= raws


def test_extract_skips_prose_noise() -> None:
    """Ordinals, COVID-19 codes, prose dates and durations aren't values."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    text = (
        "Em 1º de janeiro e 20 de julho de 2026, casos de COVID-19 "
        "caíram ao longo de 7 dias."
    )
    assert _extract_all_numbers(text) == []


def test_extract_skips_prose_date_and_duration_ranges() -> None:
    """Ranges ('entre 13 e 20 de julho', '7 a 14 dias') aren't values."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    text = (
        "variação entre 13 e 20 de julho de 2026; "
        "dados dos últimos 7 a 14 dias podem estar sujeitos a subnotificação."
    )
    assert _extract_all_numbers(text) == []


def test_numeric_grounding_still_catches_invention() -> None:
    """Genuine hallucinated stats must remain blocked."""
    narrative = "A mortalidade saltou para 42.7% no período."
    metrics = {
        "mortality_rate": {"computable": True, "value": 0.0579},
    }
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is False
    assert diffs[0]["raw"] == "42.7%"


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
