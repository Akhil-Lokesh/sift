import pytest

from sift.pricing import call_cost, decision_cost


def test_opus_uncached():
    # 1M input + 1M output on Opus 5.5 = $4 + $20
    assert call_cost("claude-opus-5-5", 1_000_000, 0, 0, 1_000_000) == pytest.approx(24.0)


def test_cache_read_is_cheap_on_opus():
    # Cache read is 0.05x base input on Opus 5.5
    assert call_cost("claude-opus-5-5", 0, 1_000_000, 0, 0) == pytest.approx(0.20)


def test_cache_write_5m():
    assert call_cost("claude-sonnet-5-5", 0, 0, 1_000_000, 0) == pytest.approx(2.50)


def test_haiku_long_prompt_tier_counts_cached_tokens():
    # 60K fresh + 50K cache read = 110K prompt -> whole request at the higher tier
    cost = call_cost("claude-haiku-5-5", 60_000, 50_000, 0, 0)
    assert cost == pytest.approx((60_000 * 0.50 + 50_000 * 0.05) / 1_000_000)


def test_haiku_short_prompt_tier():
    assert call_cost("claude-haiku-5-5", 1_000_000 // 20, 0, 0, 0) == pytest.approx(0.005)


def test_decision_cost():
    assert decision_cost(1_000_000) == pytest.approx(0.042)
