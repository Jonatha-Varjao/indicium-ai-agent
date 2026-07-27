from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import (
    ChatGoogleGenerativeAI,  # type: ignore[import-untyped]
)

from indicium_ai_agent.config.settings import get_settings
from indicium_ai_agent.narrative.prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


def synthesize_narrative(
    metrics: dict[str, Any],
    sanitized_news: str,
    news_source: str,
) -> dict[str, Any]:
    settings = get_settings()
    user_prompt = build_user_prompt(metrics, sanitized_news, news_source)

    try:
        llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            google_api_key=settings.google_api_key,
        )

        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])

        return {"narrative_draft": response.content}

    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM synthesis failed (non-blocking): %s", exc)
        return {
            "narrative_draft": (
                "Narrativa indisponível no momento. "
                "Consulte a tabela de métricas para análises detalhadas."
            ),
        }
