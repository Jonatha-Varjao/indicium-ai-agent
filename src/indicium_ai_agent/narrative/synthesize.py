"""Narrative synthesis via LLM."""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from indicium_ai_agent.config.settings import get_settings
from indicium_ai_agent.narrative._utils import coerce_content_to_str
from indicium_ai_agent.narrative.prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


def synthesize_narrative(
    metrics: dict[str, Any],
    sanitized_news: str,
    news_source: Literal["tavily", "unavailable"],
) -> dict[str, Any]:
    """Synthesize a narrative draft via LLM.

    Args:
        metrics: Computed epidemiological metrics.
        sanitized_news: Sanitized news context with delimiters.
        news_source: Literal indicating news provenance.

    Returns:
        Dict with ``narrative_draft`` string.
    """
    settings = get_settings()
    user_prompt = build_user_prompt(metrics, sanitized_news, news_source)

    try:
        llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            google_api_key=settings.google_api_key,
        )

        response = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ],
        )

        return {"narrative_draft": coerce_content_to_str(response.content)}

    except Exception as exc:
        logger.warning("LLM synthesis failed (non-blocking): %s", exc)
        return {
            "narrative_draft": (
                "Narrativa indisponível no momento. "
                "Consulte a tabela de métricas para análises detalhadas."
            ),
        }
