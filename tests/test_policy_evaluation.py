import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, cache, get_provider

CASES_PATH = Path(__file__).resolve().parents[1] / "data/evaluation/cases.json"

cases = json.loads(CASES_PATH.read_text())

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.parametrize(
    "case",
    cases,
    ids=[case["case_id"] for case in cases],
)
def test_policy_case(case):

    for attempt in range(case["repeat"]):
        response = client.post(
            "/generate",
            json={"prompt": case["prompt"]},
        )

        assert response.status_code == 200

        data = response.json()
        answer = data["answer"].lower()

        for term in case["expected_terms"]:
            assert term.lower() in answer

        assert data["cached"] is (attempt > 0)


@pytest.mark.parametrize("provider", ["groq", "unknown"])
def test_unavailable_provider_not_ready(monkeypatch, provider):
    monkeypatch.setenv("MODEL_PROVIDER", provider)

    health = client.get("/health")
    ready = client.get("/ready")
    generation = client.post(
        "/generate",
        json={"prompt": "Explain refund policy"},
    )

    assert health.status_code == 200
    assert ready.status_code == 503
    assert generation.status_code == 503


def test_unknown_policy_is_declined():

    response = client.post(
        "/generate",
        json={"prompt": "Can Northstar guarantee free products forever?"},
    )

    assert response.status_code == 200

    answer = response.json()["answer"].lower()

    assert "cannot confirm" in answer
    assert "approved policy" in answer


def test_concurrent_identical_requests():
    class CountingProvider:
        name = "counting"
        model = "concurrent-test"
        calls = 0

        async def generate(self, prompt, **kwargs):
            self.calls += 1
            await asyncio.sleep(0.05)
            return "Shared response"

    provider = CountingProvider()
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
                        json={"prompt": "Same question"},
                    )
                    for _ in range(5)
                )
            )

    try:
        responses = asyncio.run(run_requests())

        assert all(r.status_code == 200 for r in responses)
        assert provider.calls == 1

        cache_flags = [r.json()["cached"] for r in responses]
        assert cache_flags.count(False) == 1
        assert cache_flags.count(True) == 4

    finally:
        app.dependency_overrides.clear()
