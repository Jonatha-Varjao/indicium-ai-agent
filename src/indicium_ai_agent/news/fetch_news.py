"""Fetch SRAG news via Tavily with robust year extraction and typed results."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Final, Literal, TypedDict

import httpx
from tavily import TavilyClient

from indicium_ai_agent.config.news_domains import get_all_domains
from indicium_ai_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

QUERY_TEMPLATE: Final[str] = "SRAG Síndrome Respiratória Aguda Grave surto casos {year}"
DEFAULT_YEAR: Final[str] = "2026"
METRIC_YEAR_KEYS: Final[tuple[str, ...]] = (
    "case_growth_rate",
    "mortality_rate",
    "uti_admission_rate",
)


class NewsItem(TypedDict):
    """Single news article returned by Tavily."""

    title: str
    url: str
    source: str
    published_date: str
    snippet: str


class FetchNewsResult(TypedDict):
    """Result of :func:`fetch_news`."""

    news_items: list[NewsItem]
    news_source: Literal["tavily", "unavailable"]


def _year_from_iso(value: str) -> str | None:
    """Parse *value* as ISO date and return year string, or ``None``."""
    try:
        return str(date.fromisoformat(value.strip()).year)
    except ValueError:
        return None


def _year_from_period(period: str) -> str | None:
    """Extract year from a period string like ``"2026-01-01 to 2026-02-01"``."""
    period = period.strip()
    if not period:
        return None
    if " to " in period:
        _, end_str = period.split(" to ", 1)
        end_str = end_str.strip()
        year = _year_from_iso(end_str)
        if year is not None:
            return year
        candidate = end_str[:4]
        if candidate.isdigit():
            return candidate
        return None
    return _year_from_iso(period)


def _year_from_entry(entry: dict[str, Any]) -> str | None:
    """Extract year from a single metric entry, if present."""
    for date_key in ("end_date", "start_date"):
        raw = entry.get(date_key)
        if isinstance(raw, str) and raw.strip():
            year = _year_from_iso(raw)
            if year is not None:
                return year
    period = entry.get("period")
    if isinstance(period, str) and period.strip():
        year = _year_from_period(period)
        if year is not None:
            return year
    return None


def _extract_year_from_metrics(metrics: dict[str, Any]) -> str:
    """Extract year for the Tavily query from metrics or fallback to 2026.

    Strategy:
    1. Iterate over the three period-bearing metrics.
    2. Prefer explicit ``end_date`` / ``start_date`` keys if present.
    3. Parse ``period`` via :func:`date.fromisoformat` on the end date.
    4. Fall back to top-level ``end_date`` / ``start_date`` if metrics
       were passed with ReportState dates.
    5. Return ``"2026"`` as final fallback.
    """
    for metric_name in METRIC_YEAR_KEYS:
        entry = metrics.get(metric_name)
        if not isinstance(entry, dict):
            continue
        year = _year_from_entry(entry)
        if year is not None:
            return year

    for top_key in ("end_date", "start_date"):
        raw = metrics.get(top_key)
        if isinstance(raw, str) and raw.strip():
            year = _year_from_iso(raw)
            if year is not None:
                return year

    return DEFAULT_YEAR


def _extract_news_items(response: dict[str, Any]) -> list[NewsItem]:
    """Extract :class:`NewsItem` list from Tavily ``response``."""
    items: list[NewsItem] = []
    results = response.get("results")
    if not isinstance(results, list):
        return items
    for result in results:
        if not isinstance(result, dict):
            continue
        items.append(
            {
                "title": str(result.get("title", "")),
                "url": str(result.get("url", "")),
                "source": str(result.get("source", "")),
                "published_date": str(result.get("published_date", "")),
                "snippet": str(result.get("content", "")),
            }
        )
    return items


def fetch_news(metrics: dict[str, Any]) -> FetchNewsResult:
    """Fetch recent SRAG news via Tavily.

    Args:
        metrics: Mapping of metric name to metric payload (must contain
            ``period`` or ``end_date`` for year extraction).

    Returns:
        :class:`FetchNewsResult` with ``news_items`` and ``news_source``.
        On any network or API failure returns ``unavailable`` with an
        empty list; never raises for expected failures. Only ``Exception``
        (not ``BaseException``) is caught.
    """
    settings = get_settings()
    year = _extract_year_from_metrics(metrics)
    query = QUERY_TEMPLATE.format(year=year)

    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        response: dict[str, Any] = client.search(
            query=query,
            include_domains=get_all_domains(),
            max_results=5,
            topic="news",
        )
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Tavily search failed (network): %s", exc)
        return {"news_items": [], "news_source": "unavailable"}
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return {"news_items": [], "news_source": "unavailable"}

    items = _extract_news_items(response)

    if not items:
        return {"news_items": [], "news_source": "unavailable"}

    return {"news_items": items, "news_source": "tavily"}
