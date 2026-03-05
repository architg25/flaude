"""Tests for format_token_count and format_duration_seconds."""

import pytest

from flaude.formatting import format_duration_seconds, format_token_count


# ---------------------------------------------------------------------------
# format_token_count
# ---------------------------------------------------------------------------


class TestFormatTokenCount:
    def test_zero(self):
        assert format_token_count(0) == "0"

    def test_small_value(self):
        assert format_token_count(42) == "42"

    def test_just_below_1k(self):
        assert format_token_count(999) == "999"

    def test_exactly_1k(self):
        assert format_token_count(1000) == "1K"

    def test_mid_thousands(self):
        assert format_token_count(50_000) == "50K"

    def test_just_below_1m(self):
        # 999_999 // 1000 == 999
        assert format_token_count(999_999) == "999K"

    def test_exactly_1m(self):
        assert format_token_count(1_000_000) == "1.0M"

    def test_fractional_millions(self):
        assert format_token_count(1_500_000) == "1.5M"

    def test_large_millions(self):
        assert format_token_count(10_000_000) == "10.0M"

    def test_negative_stays_raw(self):
        # Negative tokens shouldn't happen, but the function returns str() for < 1000
        assert format_token_count(-1) == "-1"


# ---------------------------------------------------------------------------
# format_duration_seconds
# ---------------------------------------------------------------------------


class TestFormatDurationSeconds:
    def test_zero_seconds(self):
        assert format_duration_seconds(0) == "0m"

    def test_under_one_minute(self):
        assert format_duration_seconds(59) == "0m"

    def test_exactly_one_minute(self):
        assert format_duration_seconds(60) == "1m"

    def test_several_minutes(self):
        assert format_duration_seconds(300) == "5m"

    def test_59_minutes(self):
        assert format_duration_seconds(3540) == "59m"

    def test_exactly_one_hour(self):
        assert format_duration_seconds(3600) == "1h0m"

    def test_one_hour_one_minute_one_second(self):
        # 3661s -> 61 mins -> 1h1m (extra second is truncated)
        assert format_duration_seconds(3661) == "1h1m"

    def test_multi_hour(self):
        assert format_duration_seconds(7200) == "2h0m"

    def test_fractional_seconds_truncated(self):
        # 90.9s -> 1 min -> "1m"
        assert format_duration_seconds(90.9) == "1m"
