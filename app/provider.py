import os
from typing import Protocol

from groq import AsyncGroq


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> str: ...


class DryProvider:
    name = "dry"
    model = "northstar-dry-v2"

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:

        question = prompt.lower()

        if "refund" in question and "duplicate" in question:
            return (
                "For a duplicate-payment refund, "
                "collect the receipt and transaction details."
            )

        if "locked account" in question:
            return (
                "Verify the customer's identity before "
                "starting the account reset process."
            )

        if "personal data" in question and "delete" in question:
            return "Send the privacy deletion request for human review."

        if "incident" in question:
            return (
                "Use the status page and communicate "
                "only confirmed incident information."
            )

        return (
            "I cannot confirm this request under "
            "the approved policy. Please escalate for review."
        )


NORTHSTAR_SYSTEM_PROMPT = (
    "You are the Northstar support assistant. "
    "Follow only these approved support policies: "
    "For duplicate-payment refunds, collect receipt and transaction details. "
    "For locked accounts, verify identity before starting account reset. "
    "For personal data deletion, send the request for human privacy review. "
    "For incidents, use the status page and communicate confirmed information only. "
    "If a request is not covered, decline and recommend escalation. "
    "Do not invent policies or promise unsupported actions."
)


class GroqProvider:
    name = "groq"

    def __init__(
        self,
        client: AsyncGroq | None = None,
        model: str | None = None,
    ) -> None:
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self._client = (
            client
            if client is not None
            else AsyncGroq(
                timeout=20.0,
                max_retries=0,
            )
        )

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": NORTHSTAR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        answer = response.choices[0].message.content

        if not answer:
            raise RuntimeError("Groq returned an empty response")

        return answer
