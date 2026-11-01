"""Pinned model IDs and per-token prices.

Source and read date are in docs/providers.md. Keep the two in sync.
"""

from dataclasses import dataclass

PRICES_READ_ON = "2026-11-01"

DECISION_MODEL = "jev-1.14.0"  # pinned; never use the jev-latest alias in experiments
DECISION_INPUT_PER_MTOK = 0.042  # output is free


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float
    output: float


# Answering-model menu, small -> large.
MENU = {
    "small": "claude-haiku-5-5",
    "medium": "claude-sonnet-5-5",
    "large": "claude-opus-5-5",
}

PRICES = {
    "claude-haiku-5-5": Price(0.10, 0.125, 0.20, 0.01, 0.50),
    "claude-sonnet-5-5": Price(2.00, 2.50, 4.00, 0.10, 10.00),
    "claude-opus-5-5": Price(4.00, 5.00, 8.00, 0.20, 20.00),
}

# Haiku 5.5 bills the whole request at a higher rate once its prompt
# (input + cache reads + cache writes) exceeds 100K tokens.
HAIKU_LONG_PROMPT_THRESHOLD = 100_000
HAIKU_LONG_PROMPT_PRICE = Price(0.50, 0.625, 1.00, 0.05, 2.50)

MIN_CACHEABLE_TOKENS = {model: 512 for model in PRICES}


def price_for(model: str, prompt_tokens: int) -> Price:
    if model == "claude-haiku-5-5" and prompt_tokens > HAIKU_LONG_PROMPT_THRESHOLD:
        return HAIKU_LONG_PROMPT_PRICE
    return PRICES[model]


def call_cost(
    model: str,
    input_tokens: int,
    cache_read_tokens: int,
    cache_write_5m_tokens: int,
    output_tokens: int,
    cache_write_1h_tokens: int = 0,
) -> float:
    """USD cost of one answering call, from the usage fields the API reports.

    input_tokens is the API's `input_tokens` (tokens after the last cache
    breakpoint), not the total prompt length.
    """
    prompt = input_tokens + cache_read_tokens + cache_write_5m_tokens + cache_write_1h_tokens
    p = price_for(model, prompt)
    return (
        input_tokens * p.input
        + cache_read_tokens * p.cache_read
        + cache_write_5m_tokens * p.cache_write_5m
        + cache_write_1h_tokens * p.cache_write_1h
        + output_tokens * p.output
    ) / 1_000_000


def decision_cost(input_tokens: int) -> float:
    return input_tokens * DECISION_INPUT_PER_MTOK / 1_000_000
