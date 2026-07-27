from __future__ import annotations

from unittest.mock import MagicMock, patch

from indicium_ai_agent.news.fetch_news import _extract_year_from_metrics, fetch_news


def test_extract_year_from_metrics() -> None:
    metrics = {
        "case_growth_rate": {
            "period": "2026-01-01 to 2026-02-01",
        }
    }
    assert _extract_year_from_metrics(metrics) == "2026"


def test_extract_year_from_empty_metrics() -> None:
    assert _extract_year_from_metrics({}) == "2026"


def test_fetch_news_happy_path() -> None:
    mock_response = {
        "results": [
            {
                "title": "SRAG cases rise in Brazil",
                "url": "https://fiocruz.br/srag-news",
                "source": "Fiocruz",
                "published_date": "2026-07-25",
                "content": "New data shows increase in SRAG cases.",
            },
            {
                "title": "Health ministry warns about SRAG",
                "url": "https://gov.br/saude/srag",
                "source": "Ministério da Saúde",
                "published_date": "2026-07-24",
                "content": "Seasonal increase expected.",
            },
        ]
    }

    with (
        patch("indicium_ai_agent.news.fetch_news.get_settings") as mock_settings,
        patch("indicium_ai_agent.news.fetch_news.TavilyClient") as mock_client_cls,
    ):
        mock_settings.return_value.tavily_api_key = "test-key"
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = fetch_news({"case_growth_rate": {"period": "2026-01-01 to 2026-02-01"}})

    assert result["news_source"] == "tavily"
    assert len(result["news_items"]) == 2
    assert result["news_items"][0]["title"] == "SRAG cases rise in Brazil"
    assert result["news_items"][1]["source"] == "Ministério da Saúde"


def test_fetch_news_empty_results() -> None:
    with (
        patch("indicium_ai_agent.news.fetch_news.get_settings") as mock_settings,
        patch("indicium_ai_agent.news.fetch_news.TavilyClient") as mock_client_cls,
    ):
        mock_settings.return_value.tavily_api_key = "test-key"
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        result = fetch_news({"case_growth_rate": {"period": "2026-01-01 to 2026-02-01"}})

    assert result["news_source"] == "unavailable"
    assert result["news_items"] == []


def test_fetch_news_tavily_failure() -> None:
    with (
        patch("indicium_ai_agent.news.fetch_news.get_settings") as mock_settings,
        patch("indicium_ai_agent.news.fetch_news.TavilyClient") as mock_client_cls,
    ):
        mock_settings.return_value.tavily_api_key = "test-key"
        mock_client = MagicMock()
        mock_client.search.side_effect = ConnectionError("API unreachable")
        mock_client_cls.return_value = mock_client

        result = fetch_news({"case_growth_rate": {"period": "2026-01-01 to 2026-02-01"}})

    assert result["news_source"] == "unavailable"
    assert result["news_items"] == []


def test_fetch_news_domain_list_passed() -> None:
    from indicium_ai_agent.config.news_domains import get_all_domains

    all_domains = get_all_domains()

    with (
        patch("indicium_ai_agent.news.fetch_news.get_settings") as mock_settings,
        patch("indicium_ai_agent.news.fetch_news.TavilyClient") as mock_client_cls,
    ):
        mock_settings.return_value.tavily_api_key = "test-key"
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        fetch_news({"case_growth_rate": {"period": "2026-01-01 to 2026-02-01"}})

        _call_kwargs = mock_client.search.call_args.kwargs
        assert "include_domains" in _call_kwargs
        assert len(_call_kwargs["include_domains"]) == len(all_domains)
        for domain in all_domains:
            assert domain in _call_kwargs["include_domains"]


def test_fetch_news_query_contains_year() -> None:
    with (
        patch("indicium_ai_agent.news.fetch_news.get_settings") as mock_settings,
        patch("indicium_ai_agent.news.fetch_news.TavilyClient") as mock_client_cls,
    ):
        mock_settings.return_value.tavily_api_key = "test-key"
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        fetch_news({"case_growth_rate": {"period": "2025-06-01 to 2026-06-01"}})

        _call_kwargs = mock_client.search.call_args.kwargs
        assert "2026" in _call_kwargs["query"]


def test_fetch_news_no_metrics_year_fallback() -> None:
    with (
        patch("indicium_ai_agent.news.fetch_news.get_settings") as mock_settings,
        patch("indicium_ai_agent.news.fetch_news.TavilyClient") as mock_client_cls,
    ):
        mock_settings.return_value.tavily_api_key = "test-key"
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        fetch_news({})

        _call_kwargs = mock_client.search.call_args.kwargs
        assert "2026" in _call_kwargs["query"]
