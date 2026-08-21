from __future__ import annotations

from unittest.mock import MagicMock, patch

from indicium_ai_agent.logging.log_trace import (
    create_langfuse_handler,
    log_langfuse_trace,
)


def _minimal_state() -> dict:
    return {
        "run_id": "test-run-001",
        "data_mode": "pinned",
        "data_check_result": {"action": "pinned_snapshot"},
        "narrative_draft": "Draft text.",
        "narrative_validated": "Validated text.",
        "validation_passed": True,
        "retry_count": 0,
    }


def test_create_handler_returns_none_when_not_configured() -> None:
    with patch("indicium_ai_agent.logging.log_trace.get_settings") as mock_s:
        mock_s.return_value.langfuse_public_key = ""
        mock_s.return_value.langfuse_secret_key = ""
        handler = create_langfuse_handler()
        assert handler is None


def test_create_handler_returns_handler_when_configured() -> None:
    with (
        patch("indicium_ai_agent.logging.log_trace.get_settings") as mock_s,
        patch("indicium_ai_agent.logging.log_trace.CallbackHandler") as mock_cls,
    ):
        mock_s.return_value.langfuse_public_key = "pk-test"
        mock_s.return_value.langfuse_secret_key = "sk-test"
        mock_s.return_value.langfuse_host = "http://localhost:3000"
        mock_h = mock_cls.return_value
        handler = create_langfuse_handler()
        assert handler is mock_h


def test_log_trace_calls_start_as_current_observation() -> None:
    mock_client = MagicMock()
    mock_ctx = MagicMock()
    mock_client.start_as_current_observation.return_value = mock_ctx

    with patch("indicium_ai_agent.logging.log_trace.get_client", return_value=mock_client):
        log_langfuse_trace(_minimal_state())

        mock_client.start_as_current_observation.assert_called_once()
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["name"] == "srag_report"
        assert call_kwargs["as_type"] == "span"


def test_log_trace_includes_run_id_in_trace_context() -> None:
    mock_client = MagicMock()
    mock_ctx = MagicMock()
    mock_client.start_as_current_observation.return_value = mock_ctx

    with patch("indicium_ai_agent.logging.log_trace.get_client", return_value=mock_client):
        log_langfuse_trace(_minimal_state())

        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["trace_context"]["id"] == "test-run-001"


def test_log_trace_includes_metadata() -> None:
    mock_client = MagicMock()
    mock_ctx = MagicMock()
    mock_client.start_as_current_observation.return_value = mock_ctx

    with patch("indicium_ai_agent.logging.log_trace.get_client", return_value=mock_client):
        log_langfuse_trace(_minimal_state())

        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["metadata"]["data_mode"] == "pinned"
        assert call_kwargs["metadata"]["data_check_action"] == "pinned_snapshot"


def test_log_trace_calls_flush() -> None:
    mock_client = MagicMock()
    mock_ctx = MagicMock()
    mock_client.start_as_current_observation.return_value = mock_ctx

    with patch("indicium_ai_agent.logging.log_trace.get_client", return_value=mock_client):
        log_langfuse_trace(_minimal_state())

        mock_client.flush.assert_called_once()


def test_log_trace_failure_does_not_raise() -> None:
    mock_client = MagicMock()
    mock_client.start_as_current_observation.side_effect = ConnectionError("API down")

    with patch("indicium_ai_agent.logging.log_trace.get_client", return_value=mock_client):
        log_langfuse_trace(_minimal_state())
