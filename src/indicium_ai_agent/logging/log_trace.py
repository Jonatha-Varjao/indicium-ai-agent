from __future__ import annotations

import logging
from typing import Any

from langfuse import get_client  # type: ignore[import-untyped]
from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]

from indicium_ai_agent.config.settings import get_settings

logger = logging.getLogger(__name__)


def create_langfuse_handler() -> CallbackHandler | None:
    settings = get_settings()

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.info("Langfuse not configured — skipping tracing")
        return None

    try:
        return CallbackHandler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse handler init failed (non-blocking): %s", exc)
        return None


def log_langfuse_trace(state: dict[str, Any]) -> None:
    try:
        client = get_client()

        run_id = state.get("run_id", "")

        with client.start_as_current_observation(  # type: ignore[call-overload]
            name="srag_report",
            as_type="span",
            trace_context={"id": run_id} if run_id else None,
            input=state.get("narrative_draft", ""),
            output=state.get("narrative_validated", ""),
            metadata={
                "data_mode": str(state.get("data_mode", "")),
                "data_check_action": (
                    state.get("data_check_result", {}).get("action")
                ),
                "validation_passed": state.get("validation_passed", False),
                "retry_count": state.get("retry_count", 0),
            },
        ):
            pass

        client.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse trace failed (non-blocking): %s", exc)
