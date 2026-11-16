import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app, cache, get_provider


@pytest.fixture(autouse=True)
def reset_cache():
    cache.clear()
    yield
    cache.clear()


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_generate():
    response = client.post(
        "/generate",
        json={"prompt": "How do refunds work?"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "dry"
    assert response.json()["cached"] is False


def test_blank_prompt_rejected_before_provider_call():
    class SpyProvider:
        name = "spy"
        calls = 0
        model = "test-model"

        async def generate(self, prompt, **kwargs) -> str:
            self.calls += 1
            return "Unexpected call"

    spy = SpyProvider()
    app.dependency_overrides[get_provider] = lambda: spy

    try:
        response = client.post(
            "/generate",
            json={"prompt": "   "},
        )
        assert response.status_code == 422
        assert spy.calls == 0
    finally:
        app.dependency_overrides.clear()


def test_provider_failure():
    class FailingProvider:
        name = "failing"
        model = "test-model"

        async def generate(self, prompt, **kwargs):
            raise RuntimeError("Provider unavailable")

    app.dependency_overrides[get_provider] = lambda: FailingProvider()

    try:
        response = client.post(
            "/generate",
            json={"prompt": "Test provider failure"},
        )

        assert response.status_code == 502
        assert response.json()["detail"] == "LLM provider unavailable"

    finally:
        app.dependency_overrides.clear()


def test_provider_timeout(monkeypatch):
    class SlowProvider:
        name = "slow"
        model = "test-model"

        async def generate(self, prompt, **kwargs):
            await asyncio.sleep(0.1)
            return "Too late"

    monkeypatch.setattr(
        main_module,
        "REQUEST_TIMEOUT_SECONDS",
        0.01,
    )

    app.dependency_overrides[get_provider] = lambda: SlowProvider()

    try:
        response = client.post(
            "/generate",
            json={"prompt": "Test timeout"},
        )

        assert response.status_code == 504
        assert response.json()["detail"] == "LLM provider timed out"

    finally:
        app.dependency_overrides.clear()


def test_cache_hit():
    cache.clear()

    payload = {"prompt": "Explain refund policy"}

    first = client.post("/generate", json=payload)
    second = client.post("/generate", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True


def test_cache_key_changes_with_parameters():
    cache.clear()

    first = client.post(
        "/generate",
        json={
            "prompt": "Explain refund policy",
            "temperature": 0.0,
        },
    )

    second = client.post(
        "/generate",
        json={
            "prompt": "Explain refund policy",
            "temperature": 0.7,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["cached"] is False


def test_cache_hit_skips_provider():
    class CountingProvider:
        name = "counting"
        model = "test-v1"
        calls = 0

        async def generate(self, prompt, **kwargs):
            self.calls += 1
            return "Test answer"

    provider = CountingProvider()
    app.dependency_overrides[get_provider] = lambda: provider

    try:
        payload = {"prompt": "Explain the refund process"}

        first = client.post("/generate", json=payload)
        second = client.post("/generate", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["cached"] is False
        assert second.json()["cached"] is True
        assert provider.calls == 1

    finally:
        app.dependency_overrides.clear()


def test_provider_concurrency_limit(monkeypatch):
    class SlowProvider:
        name = "slow"
        model = "test-v1"

        def __init__(self):
            self.active = 0
            self.peak = 0
            self.calls = 0

        async def generate(self, prompt, **kwargs):
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)

            try:
                await asyncio.sleep(0.05)
                return "Test answer"
            finally:
                self.active -= 1

    provider = SlowProvider()

    monkeypatch.setattr(
        main_module,
        "provider_semaphore",
        asyncio.Semaphore(2),
    )

    app.dependency_overrides[get_provider] = lambda: provider

    async def run_requests():
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as async_client:
            return await asyncio.gather(
                *(
                    async_client.post(
                        "/generate",
                        json={"prompt": f"Question {i}"},
                    )
                    for i in range(6)
                )
            )

    try:
        responses = asyncio.run(run_requests())

        assert all(r.status_code == 200 for r in responses)
        assert provider.calls == 6
        assert provider.peak == 2

    finally:
        app.dependency_overrides.clear()


def test_cache_expires():

    from app.cache import TTLCache

    short_cache = TTLCache(ttl_seconds=0)

    short_cache.set("test-key", "test-answer")

    assert short_cache.get("test-key") is None
