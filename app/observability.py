import logging
import os
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse, get_client

logger = logging.getLogger(__name__)


def get_langfuse_client() -> Langfuse | None:
    """Return the Langfuse client only when tracing is configured."""

    enabled = os.getenv("LANGFUSE_TRACING_ENABLED", "false").strip().lower() == "true"

    if not enabled:
        return None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()

    if not public_key or not secret_key:
        logger.warning("Langfuse credentials missing; tracing disabled")
        return None

    try:
        return get_client()
    except Exception:
        logger.exception("Langfuse initialization failed; tracing disabled")
        return None


async def trace_generate_request():
    """Trace requests without affecting API availability."""

    client = get_langfuse_client()

    if client is None:
        yield
        return

    try:
        context = client.start_as_current_observation(
            as_type="span",
            name="northstar.generate",
        )
        context.__enter__()

    except Exception:
        logger.exception("Langfuse trace initialization failed")
        yield
        return

    try:
        yield

    except BaseException as exc:
        try:
            context.__exit__(type(exc), exc, exc.__traceback__)
        except Exception:
            logger.exception("Langfuse trace cleanup failed")
        raise

    else:
        try:
            context.__exit__(None, None, None)
        except Exception:
            logger.exception("Langfuse trace cleanup failed")


def record_cache_result(
    *,
    status: str,
    source: str,
    provider: str,
    model: str,
) -> None:
    """Attach cache metadata to the active request trace."""

    client = get_langfuse_client()

    if client is None:
        return

    try:
        client.update_current_span(
            metadata={
                "cache_status": status,
                "cache_source": source,
                "provider": provider,
                "model": model,
            }
        )
    except Exception:
        logger.exception("Langfuse cache telemetry failed")


@contextmanager
def trace_llm_generation(
    *,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
):
    """Track an LLM call without affecting provider execution."""

    client = get_langfuse_client()
    generation = None

    if client is not None:
        try:
            generation = client.start_observation(
                name="northstar.llm_generation",
                as_type="generation",
                model=model,
                model_parameters={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                metadata={"provider": provider},
            )
        except Exception:
            logger.exception("Langfuse generation start failed")

    try:
        yield generation
    finally:
        if generation is not None:
            try:
                generation.end()
            except Exception:
                logger.exception("Langfuse generation end failed")


def record_generation_usage(generation: Any, usage: Any) -> None:
    """Record actual provider token usage when available."""

    if generation is None or usage is None:
        return

    try:
        values = {
            "input": getattr(usage, "prompt_tokens", None),
            "output": getattr(usage, "completion_tokens", None),
            "total": getattr(usage, "total_tokens", None),
        }

        details = {
            key: value
            for key, value in values.items()
            if isinstance(value, int) and value >= 0
        }

        if details:
            generation.update(usage_details=details)

    except Exception:
        logger.exception("Langfuse usage telemetry failed")
