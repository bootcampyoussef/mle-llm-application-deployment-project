import asyncio
import os
from functools import lru_cache
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.cache import TTLCache, build_cache_key
from app.observability import record_cache_result, trace_generate_request
from app.provider import DryProvider, GroqProvider, LLMProvider

load_dotenv()
app = FastAPI(title="Northstar Support Assistant")

# Service configuration
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "4"))

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))

# Concurrency and caching
provider_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)

key_locks: dict[str, asyncio.Lock] = {}
key_lock_users: dict[str, int] = {}


# API schemas
class StatusResponse(BaseModel):
    status: str


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_tokens: int = Field(default=256, ge=1, le=2048)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt cannot be blank")
        return value


class GenerateResponse(BaseModel):
    answer: str
    provider: str
    cached: bool = False


# Provider configuration
def check_provider_config() -> None:
    provider = os.getenv("MODEL_PROVIDER", "dry").strip().lower()

    if provider == "dry":
        return

    if provider == "groq":
        if not os.getenv("GROQ_API_KEY", "").strip():
            raise HTTPException(
                status_code=503,
                detail="GROQ_API_KEY is required",
            )
        return

    raise HTTPException(
        status_code=503,
        detail=f"Unsupported MODEL_PROVIDER: {provider}",
    )


@lru_cache(maxsize=1)
def get_groq_provider() -> GroqProvider:
    return GroqProvider()


def get_provider() -> LLMProvider:
    check_provider_config()

    provider = os.getenv("MODEL_PROVIDER", "dry").strip().lower()

    if provider == "groq":
        return get_groq_provider()

    return DryProvider()


# Health and readiness
@app.get("/health", response_model=StatusResponse)
async def health():
    return StatusResponse(status="ok")


@app.get("/ready", response_model=StatusResponse)
async def ready():
    check_provider_config()
    return StatusResponse(status="ready")


# LLM generation
@app.post(
    "/generate",
    response_model=GenerateResponse,
    dependencies=[Depends(trace_generate_request)],
)
async def generate(
    request: GenerateRequest,
    provider: Annotated[LLMProvider, Depends(get_provider)],
):
    key = build_cache_key(
        provider=provider.name,
        model=provider.model,
        parameters=request.model_dump(),
    )

    # Fast path: existing cache entry
    cached_answer = cache.get(key)

    if cached_answer is not None:
        record_cache_result(
            status="hit",
            source="fast_path",
            provider=provider.name,
            model=provider.model,
        )
        return GenerateResponse(
            answer=cached_answer,
            provider=provider.name,
            cached=True,
        )

    async def call_provider() -> tuple[str, bool]:
        # One lock per unique cache key
        lock = key_locks.setdefault(key, asyncio.Lock())
        key_lock_users[key] = key_lock_users.get(key, 0) + 1

        try:
            async with lock:
                # Check again after acquiring the lock
                existing = cache.get(key)

                if existing is not None:
                    return existing, True

                # Limit concurrent provider calls
                async with provider_semaphore:
                    result = await provider.generate(
                        request.prompt,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                    )

                cache.set(key, result)
                return result, False

        finally:
            # Remove unused locks
            key_lock_users[key] -= 1

            if key_lock_users[key] == 0:
                del key_lock_users[key]
                key_locks.pop(key, None)

    # Execute with timeout and error handling
    try:
        answer, was_cached = await asyncio.wait_for(
            call_provider(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="LLM provider timed out",
        ) from None

    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail="LLM provider unavailable",
        ) from None

    # Record final cache result
    record_cache_result(
        status="hit" if was_cached else "miss",
        source="after_lock" if was_cached else "provider",
        provider=provider.name,
        model=provider.model,
    )

    return GenerateResponse(
        answer=answer,
        provider=provider.name,
        cached=was_cached,
    )
