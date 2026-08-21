from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Final, cast

from langfuse import get_client
from langfuse.langchain import CallbackHandler

from indicium_ai_agent.config.settings import Settings, get_settings
from indicium_ai_agent.state import ReportState

logger = logging.getLogger(__name__)

OBSERVATION_NAME: Final[str] = "srag_report"
"""Langfuse observation name for SRAG report spans."""


def _load_langfuse_env(settings: Settings) -> None:
    """Propagate Langfuse credentials from Settings to OS environment.

    The Langfuse SDK reads credentials from ``os.environ``. Pydantic Settings
    loads them from ``.env``; this helper ensures the SDK sees the latest
    values by unconditionally overwriting any stale environment variables.

    Idempotence is documented intentionally: repeated calls overwrite existing
    vars so that updated Settings (e.g., in tests or reloads) are reflected.
    ``isinstance(..., str)`` guards against ``MagicMock`` in tests.

    Args:
        settings: Validated application settings.
    """
    pk = settings.langfuse_public_key
    sk = settings.langfuse_secret_key
    host = settings.langfuse_host
    if pk and isinstance(pk, str):
        os.environ["LANGFUSE_PUBLIC_KEY"] = pk
    if sk and isinstance(sk, str):
        os.environ["LANGFUSE_SECRET_KEY"] = sk
    if host and isinstance(host, str):
        os.environ["LANGFUSE_HOST"] = host


def create_langfuse_handler() -> CallbackHandler | None:
    """Create a Langfuse CallbackHandler if tracing is configured.

    Returns:
        Configured handler or ``None`` when credentials are missing or init
        fails. Failures are logged as warnings and are non-blocking.
    """
    settings = get_settings()

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.info("Langfuse not configured — skipping tracing")
        return None

    _load_langfuse_env(settings)

    try:
        return CallbackHandler()
    except Exception as exc:
        logger.warning("Langfuse handler init failed (non-blocking): %s", exc)
        return None


def log_langfuse_trace(state: ReportState | dict[str, Any]) -> None:
    """Emit a Langfuse span for the current report run.

    Non-blocking: failures are logged as warnings and do not raise.

    Uses :data:`OBSERVATION_NAME` as the observation name and stores run
    metadata. Trace context is built with ``trace_id`` (Langfuse API) and
    includes ``id`` for backwards compatibility with existing tests.

    Args:
        state: Pipeline report state containing run metadata.
    """
    try:
        client = get_client()

        run_id = state.get("run_id", "")
        # Langfuse expects TraceContext with ``trace_id``; keep ``id`` for
        # backwards compatibility with unit tests asserting ``trace_context["id"]``.
        if run_id and isinstance(run_id, str):
            trace_context = cast(Any, {"trace_id": run_id, "id": run_id})
        elif run_id:
            trace_context = cast(Any, {"trace_id": str(run_id), "id": str(run_id)})
        else:
            trace_context = None

        data_mode = state.get("data_mode", "")
        if isinstance(data_mode, Enum):
            data_mode_str = str(data_mode.value)
        else:
            data_mode_str = str(data_mode)

        with client.start_as_current_observation(
            name=OBSERVATION_NAME,
            as_type="span",
            trace_context=trace_context,
            input=state.get("narrative_draft", ""),
            output=state.get("narrative_validated", ""),
            metadata={
                "data_mode": data_mode_str,
                "data_check_action": (state.get("data_check_result", {}).get("action")),
                "validation_passed": state.get("validation_passed", False),
                "retry_count": state.get("retry_count", 0),
            },
        ):
            pass

        client.flush()
    except Exception as exc:
        logger.warning("Langfuse trace failed (non-blocking): %s", exc)
