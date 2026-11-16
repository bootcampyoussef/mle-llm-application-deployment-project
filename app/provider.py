from typing import Protocol


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
            return (
                "Send the privacy deletion request "
                "for human review."
            )

        if "incident" in question:
            return (
                "Use the status page and communicate "
                "only confirmed incident information."
            )

        return (
            "I cannot confirm this request under "
            "the approved policy. Please escalate for review."
        )