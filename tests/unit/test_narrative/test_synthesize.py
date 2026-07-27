from __future__ import annotations

from unittest.mock import MagicMock, patch

from indicium_ai_agent.narrative.synthesize import synthesize_narrative


def test_synthesize_calls_llm() -> None:
    mock_response = MagicMock()
    mock_response.content = "Narrativa gerada pelo modelo."

    with (
        patch("indicium_ai_agent.narrative.synthesize.get_settings") as mock_settings,
        patch(
            "indicium_ai_agent.narrative.synthesize.ChatGoogleGenerativeAI"
        ) as mock_llm_cls,
    ):
        mock_settings.return_value.google_api_key = "test-key"
        mock_settings.return_value.llm_temperature = 0.2
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_llm_cls.return_value = mock_llm

        result = synthesize_narrative(
            metrics={
                "case_growth_rate": {
                    "computable": True,
                    "value": 15.5,
                    "numerator": 30,
                    "denominator": 20,
                    "period": "2026-01-01 to 2026-02-01",
                },
            },
            sanitized_news="",
            news_source="unavailable",
        )

    assert result["narrative_draft"] == "Narrativa gerada pelo modelo."
    mock_llm.invoke.assert_called_once()


def test_synthesize_uses_correct_messages() -> None:
    mock_response = MagicMock()
    mock_response.content = "Narrativa."

    with (
        patch("indicium_ai_agent.narrative.synthesize.get_settings") as mock_settings,
        patch(
            "indicium_ai_agent.narrative.synthesize.ChatGoogleGenerativeAI"
        ) as mock_llm_cls,
    ):
        mock_settings.return_value.google_api_key = "test-key"
        mock_settings.return_value.llm_temperature = 0.2
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_llm_cls.return_value = mock_llm

        synthesize_narrative(
            metrics={},
            sanitized_news="",
            news_source="unavailable",
        )

        _call_args, call_kwargs = mock_llm.invoke.call_args
        messages = call_kwargs.get("input") if "input" in call_kwargs else _call_args[0]

        types_found = {type(m).__name__ for m in messages}
        assert "SystemMessage" in types_found
        assert "HumanMessage" in types_found


def test_synthesize_uses_settings() -> None:
    mock_response = MagicMock()
    mock_response.content = "Narrativa."

    with (
        patch("indicium_ai_agent.narrative.synthesize.get_settings") as mock_settings,
        patch(
            "indicium_ai_agent.narrative.synthesize.ChatGoogleGenerativeAI"
        ) as mock_llm_cls,
    ):
        mock_settings.return_value.google_api_key = "custom-key"
        mock_settings.return_value.llm_temperature = 0.5
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_llm_cls.return_value = mock_llm

        synthesize_narrative(
            metrics={},
            sanitized_news="",
            news_source="unavailable",
        )

        _call_kwargs = mock_llm_cls.call_args.kwargs
        assert _call_kwargs["google_api_key"] == "custom-key"
        assert _call_kwargs["temperature"] == 0.5


def test_synthesize_failure_fallback() -> None:
    with (
        patch("indicium_ai_agent.narrative.synthesize.get_settings") as mock_settings,
        patch(
            "indicium_ai_agent.narrative.synthesize.ChatGoogleGenerativeAI"
        ) as mock_llm_cls,
    ):
        mock_settings.return_value.google_api_key = "invalid-key"
        mock_settings.return_value.llm_temperature = 0.2
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API error")
        mock_llm_cls.return_value = mock_llm

        result = synthesize_narrative(
            metrics={},
            sanitized_news="",
            news_source="unavailable",
        )

    assert "Narrativa indisponível" in result["narrative_draft"]
