import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.provider import GroqProvider


def test_groq_provider_generates_answer():
    # Simulated Groq response
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Please provide your transaction details."
                )
            )
        ]
    )

    # Mock Groq client
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    provider = GroqProvider(
        client=client,
        model="openai/gpt-oss-20b",
    )

    # Generate answer without a real API call
    answer = asyncio.run(
        provider.generate(
            "How can I request a duplicate payment refund?",
            temperature=0.0,
            max_tokens=128,
        )
    )

    assert answer == "Please provide your transaction details."

    client.chat.completions.create.assert_awaited_once()

    kwargs = client.chat.completions.create.await_args.kwargs

    assert kwargs["model"] == "openai/gpt-oss-20b"
    assert kwargs["temperature"] == 0.0
    assert kwargs["max_tokens"] == 128
    assert kwargs["messages"][1]["role"] == "user"


def test_groq_provider_rejects_empty_answer():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
    )

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    provider = GroqProvider(client=client)

    with pytest.raises(
        RuntimeError,
        match="Groq returned an empty response",
    ):
        asyncio.run(
            provider.generate(
                "Explain the refund policy",
                temperature=0.0,
                max_tokens=128,
            )
        )

    client.chat.completions.create.assert_awaited_once()


def test_groq_provider_handles_upstream_failure():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("Groq service unavailable")
    )

    provider = GroqProvider(client=client)

    with pytest.raises(RuntimeError, match="Groq service unavailable"):
        asyncio.run(
            provider.generate(
                "How can I request a refund?",
                temperature=0.0,
                max_tokens=128,
            )
        )

    client.chat.completions.create.assert_awaited_once()
