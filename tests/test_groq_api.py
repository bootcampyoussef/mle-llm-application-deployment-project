import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import app.main as main_module
from app.cache import TTLCache
from app.main import app, get_groq_provider, get_provider
from app.provider import GroqProvider


def test_groq_readiness_without_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "GROQ_API_KEY is required"}


def test_groq_readiness_with_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-only-key")

    get_groq_provider.cache_clear()

    try:
        client = TestClient(app)

        response = client.get("/ready")
        provider = get_provider()

        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

        assert isinstance(provider, GroqProvider)
        assert provider.name == "groq"

    finally:
        get_groq_provider.cache_clear()


def test_groq_failure_returns_502(monkeypatch):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("Simulated Groq outage")
    )

    provider = GroqProvider(client=client)

    # Inject mocked provider into FastAPI
    monkeypatch.setitem(
        app.dependency_overrides,
        get_provider,
        lambda: provider,
    )

    api = TestClient(app)

    payload = {
        "prompt": "Simulate a Groq outage for error handling",
        "temperature": 0.0,
        "max_tokens": 128,
    }

    response = api.post("/generate", json=payload)

    assert response.status_code == 502
    assert response.json() == {"detail": "LLM provider unavailable"}

    # Failed responses must not be cached
    second_response = api.post("/generate", json=payload)

    assert second_response.status_code == 502
    assert client.chat.completions.create.await_count == 2


def test_groq_timeout_returns_504(monkeypatch):
    async def slow_response(**kwargs):
        # Simulate a provider that never responds
        await asyncio.Event().wait()

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=slow_response)

    provider = GroqProvider(client=client)

    # Use a short timeout for testing
    monkeypatch.setattr(
        main_module,
        "REQUEST_TIMEOUT_SECONDS",
        0.02,
    )

    # Inject mocked provider
    monkeypatch.setitem(
        app.dependency_overrides,
        get_provider,
        lambda: provider,
    )

    api = TestClient(app)

    payload = {
        "prompt": "Test Groq timeout handling",
        "temperature": 0.0,
        "max_tokens": 128,
    }

    response = api.post("/generate", json=payload)

    assert response.status_code == 504
    assert response.json() == {"detail": "LLM provider timed out"}

    # Timeout responses must not be cached
    second_response = api.post("/generate", json=payload)

    assert second_response.status_code == 504
    assert client.chat.completions.create.await_count == 2


def test_groq_cache_hit_avoids_second_provider_call(monkeypatch):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Collect the receipt and transaction details."
                )
            )
        ]
    )

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    provider = GroqProvider(client=client)

    # Isolate cache from other tests
    monkeypatch.setattr(
        main_module,
        "cache",
        TTLCache(ttl_seconds=300),
    )

    # Inject mocked Groq provider
    monkeypatch.setitem(
        app.dependency_overrides,
        get_provider,
        lambda: provider,
    )

    api = TestClient(app)

    payload = {
        "prompt": "How do I request a duplicate-payment refund?",
        "temperature": 0.0,
        "max_tokens": 128,
    }

    first = api.post("/generate", json=payload)
    second = api.post("/generate", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True

    assert first.json()["answer"] == second.json()["answer"]
    assert first.json()["provider"] == "groq"

    # Groq must be called only once
    client.chat.completions.create.assert_awaited_once()
