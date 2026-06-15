"""Shared LLM client used by all agent nodes.

Centralizes model construction so agents don't each configure their own
client, and so swapping providers/models only requires changes here.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from app.config import settings


@lru_cache(maxsize=1)
def get_llm(temperature: float = 0.3) -> ChatAnthropic:
    """Return a cached ChatAnthropic client.

    A single cached instance is reused across requests/agents since the
    client itself is stateless and thread-safe for our use case.
    """
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Configure it in your .env file."
        )

    return ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        temperature=temperature,
        max_tokens=2048,
    )


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """Make a single LLM call and return the text content of the response."""
    llm = get_llm(temperature=temperature)
    messages = [
        ("system", system_prompt),
        ("human", user_prompt),
    ]
    response = llm.invoke(messages)

    content = response.content
    if isinstance(content, str):
        return content

    # ChatAnthropic can return a list of content blocks; concatenate text blocks.
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts)
