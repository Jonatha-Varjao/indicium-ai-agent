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


def test_numeric_grounding_nearest_direction_word_wins() -> None:
    """Review regression: an earlier 'queda' within the window must not
    ground a nearer conflicting 'aumento' claim on a negative metric."""
    narrative = (
        "Após queda de 3,1% na semana passada, registrou-se "
        "aumento de 78,12% no número de casos."
    )
    metrics = {
        "case_growth_rate": {"computable": True, "value": -78.12},
    }
    # The 3,1% claim itself has no grounding either; what matters here
    # is that 78,12% is flagged despite 'queda' appearing earlier.
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is False
    raws = {d["raw"] for d in diffs}
    assert "78,12%" in raws


def test_numeric_grounding_signed_match_ignores_direction_words() -> None:
    """Exact signed values pass regardless of nearby direction words —
    direction vocabulary only gates OPPOSITE-SIGN magnitude matching."""
    metrics = {"mortality_rate": {"computable": True, "value": 0.0579}}
    ok, _ = check_numeric_grounding(
        "Após queda anterior, mortalidade de 0,0579.", metrics
    )
    assert ok is True


def test_negative_metric_magnitude_requires_decrease_nearest() -> None:
    """Positive magnitude on a negative metric: polarity of the NEAREST
    direction word decides — both plain and conflicting-clause forms."""
    metrics = {"case_growth_rate": {"computable": True, "value": -78.12}}

    ok, _ = check_numeric_grounding("Alta isolada de 78,12%.", metrics)  # wrong dir
    assert ok is False

    ok, diffs = check_numeric_grounding(
        "Observou-se aumento de 78,12% nos casos.", metrics
    )
    assert ok is False and any(d["raw"] == "78,12%" for d in diffs)

    ok, _ = check_numeric_grounding("Queda de 78,12% confirmada.", metrics)
    assert ok is True


def test_unsupported_duration_with_clinical_framing_is_flagged() -> None:
    """Review regression: value-based exemption let fabricated clinical
    durations ('internação média de 7 dias') bypass grounding."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    text = "pacientes apresentaram internação média de 7 dias."
    extracted = _extract_all_numbers(text)
    assert any(raw == "7" for raw, _v, _s in extracted)

    metrics = {"mortality_rate": {"computable": True, "value": 0.0579}}
    ok, diffs = check_numeric_grounding(text, metrics)
    assert ok is False
    assert any(d["raw"] == "7" for d in diffs)


def test_anchored_duration_frames_still_skipped() -> None:
    """Legitimate temporal frames keep their documented-window skip."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    for frame in (
        "dados dos últimos 14 dias.",
        "acompanhamento nos próximos 7 dias.",
        "evolução no período de 7 dias.",
        "janela de 14 dias.",
    ):
        assert _extract_all_numbers(frame) == [], frame


def test_generic_clinical_durante_not_exempt() -> None:
    """Review regression: generic 'durante 7 dias' (clinical duration)
    must be grounded, not silently exempt as a methodology window."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    for text in (
        "pacientes foram hospitalizados durante 7 dias.",
        "tratamento durou ao longo de 7 dias.",
        "observado durante 14 dias na coorte.",
    ):
        extracted = _extract_all_numbers(text)
        raws = {raw for raw, _v, _s in extracted}
        assert "7" in raws or "14" in raws, text

        metrics = {"mortality_rate": {"computable": True, "value": 0.0579}}
        ok, diffs = check_numeric_grounding(text, metrics)
        assert ok is False, f"should flag clinical {text!r}: diffs={diffs}"


def test_duration_anchor_does_not_leak_through_intervening_phrase() -> None:
    """Review regression: 'nos últimos 30 dias, 7 dias de internação'
    must NOT exempt the second '7 dias' (anchor belongs to '30 dias')."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    cases = [
        "nos últimos 30 dias, 7 dias de internação",
        "no período de estudo, 7 dias de febre",
    ]
    for text in cases:
        extracted = _extract_all_numbers(text)
        raws = {raw for raw, _v, _s in extracted}
        assert "7" in raws, f"should surface clinical 7 in {text!r}, got {raws}"
        metrics = {"mortality_rate": {"computable": True, "value": 0.0579}}
        ok, diffs = check_numeric_grounding(text, metrics)
        assert ok is False, f"should flag {text!r}"
        assert any(d["raw"] == "7" for d in diffs), text


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
        "caíram nos últimos 7 dias."
    )
    assert _extract_all_numbers(text) == []


def test_extract_skips_alphanumeric_codes_and_de_ranges() -> None:
    """Review-followup regressions from a real pipeline run:
    'g1' (news outlet) must not yield token '1'; the range variant
    'de 13 a 20 de julho' must stay contextual like 'entre 13 e 20'."""
    from indicium_ai_agent.narrative.validate import _extract_all_numbers

    assert _extract_all_numbers("Conforme reportado pelo g1, cenário em 2026.") == []
    assert (
        _extract_all_numbers("análise dos dados de 13 a 20 de julho de 2026 indica.")
        == []
    )


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


def test_numbers_from_retrieved_news_are_grounded() -> None:
    """Figures cited faithfully from news items ground via the source."""
    narrative = (
        "A Bahia registrou 1.732 casos até março, com crescimento "
        "de 14,6% nos casos."
    )
    metrics = {"case_growth_rate": {"computable": True, "value": -78.12}}
    news = [
        {
            "title": "Bahia registra aumento nos casos de SRAG",
            "snippet": "o estado apontou crescimento de 14,6% nos casos; "
                       "foram 1.732 registros até março.",
            "url": "https://g1.globo.com/ba/srag",
        }
    ]
    ok, diffs = check_numeric_grounding(narrative, metrics, news)
    assert ok is True, diffs


def test_news_grounding_does_not_open_invention_door() -> None:
    """Numbers absent from both metrics and news stay blocked even when
    other numbers were legitimately grounded from news."""
    narrative = "A Bahia registrou 1.732 casos e a mortalidade foi de 88,8%."
    metrics: dict = {}
    news = [
        {"title": "Bahia SRAG", "snippet": "crescimento de 14,6%; 1.732 registros."}
    ]
    ok, diffs = check_numeric_grounding(narrative, metrics, news)
    assert ok is False
    assert [d["raw"] for d in diffs] == ["88,8%"]


def test_percent_voicing_of_unit_proportions_is_grounded() -> None:
    """'0.388' may be voiced as '38,8%' — same fact, percent scale."""
    narrative = "A cobertura vacinal é de 38,8% para COVID-19 e 41,55% para Influenza."
    metrics = {
        "vaccination_coverage": {
            "computable": True,
            "value": {"covid": 0.388, "flu": 0.4155},
        }
    }
    ok, diffs = check_numeric_grounding(narrative, metrics)
    assert ok is True, diffs


def test_percent_voicing_does_not_scale_percent_metrics() -> None:
    """Metrics already in percent must NOT accept a x100 reading."""
    narrative = "A taxa cresceu 7812% no período."
    metrics = {"case_growth_rate": {"computable": True, "value": -78.12}}
    ok, _diffs = check_numeric_grounding(narrative, metrics)
    assert ok is False


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
