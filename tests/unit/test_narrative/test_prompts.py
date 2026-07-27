from __future__ import annotations

from indicium_ai_agent.narrative.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
)


def test_system_prompt_exists() -> None:
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 100


def test_system_prompt_contains_rules() -> None:
    assert "REGRAS ESTRITAS" in SYSTEM_PROMPT
    assert "nunca" in SYSTEM_PROMPT.lower()


def test_user_prompt_contains_metric_names() -> None:
    metrics = {
        "case_growth_rate": {
            "computable": True,
            "value": 15.5,
            "numerator": 30,
            "denominator": 20,
            "period": "2026-01-01 to 2026-02-01",
        },
    }
    prompt = build_user_prompt(metrics, "", "unavailable")
    assert "Taxa de aumento de casos" in prompt
    assert "15.5" in prompt


def test_user_prompt_with_news() -> None:
    metrics = {
        "case_growth_rate": {
            "computable": True,
            "value": 10.0,
            "numerator": 10,
            "denominator": 100,
            "period": "2026-01-01 to 2026-02-01",
        },
    }
    sanitized = "{{NEWS_CONTENT_START}}\nNews content\n{{NEWS_CONTENT_END}}"
    prompt = build_user_prompt(metrics, sanitized, "tavily")
    assert "{{NEWS_CONTENT_START}}" in prompt
    assert "News content" in prompt


def test_user_prompt_without_news() -> None:
    metrics = {
        "case_growth_rate": {
            "computable": False,
            "value": None,
        },
    }
    prompt = build_user_prompt(metrics, "", "unavailable")
    assert "Nenhuma notícia relevante encontrada" in prompt


def test_user_prompt_non_computable() -> None:
    metrics = {
        "case_growth_rate": {
            "computable": False,
            "value": None,
        },
    }
    prompt = build_user_prompt(metrics, "", "unavailable")
    assert "Dados insuficientes" in prompt or "dados insuficientes" in prompt
