from __future__ import annotations

import logging
from typing import Any

from tavily import TavilyClient  # type: ignore[import-untyped]

from indicium_ai_agent.config.news_domains import get_all_domains
from indicium_ai_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

QUERY_TEMPLATE = "SRAG Síndrome Respiratória Aguda Grave surto casos {year}"


def _extract_year_from_metrics(metrics: dict[str, Any]) -> str:
    for metric_name in ("case_growth_rate", "mortality_rate", "uti_admission_rate"):
        period = metrics.get(metric_name, {}).get("period", "")
        if period:
            parts = period.split(" to ")
            if len(parts) == 2:
                year = parts[1][:4]
                if year.isdigit():
                    return year
    return "2026"


def _extract_news_items(response: dict) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for result in response.get("results", []):
        items.append({
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "source": result.get("source", ""),
            "published_date": result.get("published_date", ""),
            "snippet": result.get("content", ""),
        })
    return items


def fetch_news(
    metrics: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    year = _extract_year_from_metrics(metrics)
    query = QUERY_TEMPLATE.format(year=year)

    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            include_domains=get_all_domains(),
            max_results=5,
            topic="news",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tavily search failed: %s", exc)
        return {"news_items": [], "news_source": "unavailable"}

    items = _extract_news_items(response)

    if not items:
        return {"news_items": [], "news_source": "unavailable"}

    return {"news_items": items, "news_source": "tavily"}
