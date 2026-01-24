"""Tests for rate limiting and human behavior patterns."""

import time
import unittest
from datetime import datetime, time as dt_time
from unittest.mock import Mock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.retry import (
    RetryConfig,
    RetryableError,
    with_retry,
    MCP_RETRY_CONFIG,
    extract_retry_after,
)
from src.behaviors.human_patterns import (
    HumanBehaviorSimulator,
    HumanActivityPattern,
    AvailabilityStatus,
    TimeWindow,
    get_default_pattern_for_role,
)
from src.behaviors.rate_limiter import (
    AgentRateLimiter,
    RateLimitedMCPClient,
    RateLimitExceededError,
    RateLimitReason,
    DailyQuota,
    get_quota_for_role,
)


class TestRetryDecorator(unittest.TestCase):
    """Test retry decorator."""

    def test_successful_call_no_retry(self):
        """Test that successful calls don't trigger retries."""
        call_count = 0

        @with_retry(config=MCP_RETRY_CONFIG)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 1)

    def test_retry_on_retryable_error(self):
        """Test that RetryableError triggers retries."""
        call_count = 0

        config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.1)

        @with_retry(config=config)
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("Transient error")
            return "success"

        result = failing_func()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)

    def test_exhausted_retries_raises(self):
        """Test that exhausted retries raise the exception."""
        config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.1)

        @with_retry(config=config)
        def always_fails():
            raise RetryableError("Always fails")

        with self.assertRaises(RetryableError):
            always_fails()

    def test_non_retryable_exception_not_retried(self):
        """Test that non-retryable exceptions are not retried."""
        call_count = 0

        @with_retry(config=MCP_RETRY_CONFIG)
        def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with self.assertRaises(ValueError):
            raises_value_error()

        self.assertEqual(call_count, 1)


class TestRetryAfterExtraction(unittest.TestCase):
    """Test Retry-After header extraction."""

    def test_extract_retry_after_seconds(self):
        """Test extracting Retry-After as seconds."""
        mock_response = Mock()
        mock_response.headers = {"Retry-After": "30"}

        result = extract_retry_after(mock_response)
        self.assertEqual(result, 30.0)

    def test_extract_retry_after_none(self):
        """Test when Retry-After header is missing."""
        mock_response = Mock()
        mock_response.headers = {}

        result = extract_retry_after(mock_response)
        self.assertIsNone(result)

    def test_extract_retry_after_invalid(self):
        """Test when Retry-After is not a valid number."""
        mock_response = Mock()
        mock_response.headers = {"Retry-After": "invalid"}

        result = extract_retry_after(mock_response)
        self.assertIsNone(result)


class TestHumanBehaviorSimulator(unittest.TestCase):
    """Test human behavior simulation."""

    def test_default_work_hours(self):
        """Test default work hours check."""
        sim = HumanBehaviorSimulator()

        # During work hours (10am)
        work_time = datetime.now().replace(hour=10, minute=0, second=0)
        self.assertTrue(sim.is_work_hours(work_time))

        # Before work hours (7am)
        early_time = datetime.now().replace(hour=7, minute=0, second=0)
        self.assertFalse(sim.is_work_hours(early_time))

        # After work hours (8pm)
        late_time = datetime.now().replace(hour=20, minute=0, second=0)
        self.assertFalse(sim.is_work_hours(late_time))

    def test_thinking_delay_range(self):
        """Test thinking delay is within expected range."""
        sim = HumanBehaviorSimulator()

        delays = [sim.get_thinking_delay() for _ in range(100)]

        self.assertTrue(all(d >= 1.0 for d in delays))  # Minimum 1 second
        self.assertTrue(any(d > 3.0 for d in delays))  # Should have some > 3s
        self.assertTrue(all(d < 30.0 for d in delays))  # Max should be reasonable

    def test_availability_outside_hours(self):
        """Test availability returns unavailable outside work hours."""
        sim = HumanBehaviorSimulator()

        # Before work (7am)
        early_time = datetime.now().replace(hour=7, minute=0, second=0)
        result = sim.check_availability(early_time)
        self.assertFalse(result.available)
        self.assertEqual(result.status, AvailabilityStatus.OUTSIDE_HOURS)

    def test_role_specific_patterns(self):
        """Test that different roles get different patterns."""
        dev_pattern = get_default_pattern_for_role("Software Developer")
        exec_pattern = get_default_pattern_for_role("CEO")
        sales_pattern = get_default_pattern_for_role("Key Account Manager")

        # Developer has longer thinking time
        self.assertGreater(dev_pattern.max_thinking_seconds, sales_pattern.max_thinking_seconds)

        # Executive starts earlier
        self.assertLess(exec_pattern.work_start, dev_pattern.work_start)


class TestAgentRateLimiter(unittest.TestCase):
    """Test agent rate limiter."""

    def test_api_call_allowed_initially(self):
        """Test that API calls are allowed initially."""
        limiter = AgentRateLimiter(
            "test@example.com",
            role="Developer",
            enable_human_patterns=False,
        )

        result = limiter.check_api_call()
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, RateLimitReason.ALLOWED)

    def test_daily_quota_enforcement(self):
        """Test that daily quota is enforced."""
        quota = DailyQuota(max_emails_per_day=2)
        limiter = AgentRateLimiter(
            "test@example.com",
            quota=quota,
            enable_human_patterns=False,
        )

        # Send 2 emails (within quota)
        limiter.record_email_sent()
        limiter.record_email_sent()

        # Third email should be blocked
        result = limiter.check_email_send()
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, RateLimitReason.DAILY_QUOTA_EXCEEDED)

    def test_minimum_interval_enforcement(self):
        """Test minimum interval between actions."""
        quota = DailyQuota(min_seconds_between_api_calls=10.0)
        limiter = AgentRateLimiter(
            "test@example.com",
            quota=quota,
            enable_human_patterns=False,
        )

        # First call
        result1 = limiter.check_api_call()
        self.assertTrue(result1.allowed)
        limiter.record_api_call()

        # Immediate second call should have delay
        result2 = limiter.check_api_call()
        self.assertTrue(result2.allowed)  # Allowed but with delay
        self.assertEqual(result2.reason, RateLimitReason.MIN_INTERVAL_NOT_MET)
        self.assertGreater(result2.delay_seconds, 0)

    def test_role_quota_selection(self):
        """Test that role-specific quotas are selected correctly."""
        kam_quota = get_quota_for_role("Key Account Manager")
        dev_quota = get_quota_for_role("Software Developer")
        default_quota = get_quota_for_role("Unknown Role")

        # KAM has higher email quota
        self.assertGreater(kam_quota.max_emails_per_day, dev_quota.max_emails_per_day)

        # Default quota is used for unknown roles
        self.assertEqual(default_quota.max_emails_per_day, 50)

    def test_status_reporting(self):
        """Test that status is reported correctly."""
        limiter = AgentRateLimiter(
            "test@example.com",
            role="Developer",
            enable_human_patterns=False,
        )

        # Record some activity
        limiter.record_api_call()
        limiter.record_api_call()
        limiter.record_email_sent()

        status = limiter.get_status()

        self.assertEqual(status["agent_email"], "test@example.com")
        self.assertEqual(status["api_calls"]["today"], 2)
        self.assertEqual(status["emails"]["sent_today"], 1)


class TestRateLimitedMCPClient(unittest.TestCase):
    """Test rate-limited MCP client wrapper."""

    def test_wraps_email_methods(self):
        """Test that email methods are rate limited."""
        mock_client = Mock()
        mock_client.send_mail = Mock(return_value={"success": True})

        quota = DailyQuota(max_emails_per_day=1, min_seconds_between_emails=0)
        limiter = AgentRateLimiter(
            "test@example.com",
            quota=quota,
            enable_human_patterns=False,
        )

        wrapped = RateLimitedMCPClient(mock_client, limiter)

        # First email succeeds
        result = wrapped.send_mail(to="a@b.com", subject="Test", body="Hello")
        self.assertEqual(result["success"], True)

        # Second email should be rate limited
        with self.assertRaises(RateLimitExceededError):
            wrapped.send_mail(to="a@b.com", subject="Test 2", body="Hello 2")

    def test_wraps_api_methods(self):
        """Test that API methods are rate limited."""
        mock_client = Mock()
        mock_client.get_inbox = Mock(return_value=[])

        quota = DailyQuota(max_api_calls_per_day=1, min_seconds_between_api_calls=0)
        limiter = AgentRateLimiter(
            "test@example.com",
            quota=quota,
            enable_human_patterns=False,
        )

        wrapped = RateLimitedMCPClient(mock_client, limiter)

        # First call succeeds
        wrapped.get_inbox()

        # Second call should be rate limited
        with self.assertRaises(RateLimitExceededError):
            wrapped.get_inbox()


if __name__ == "__main__":
    unittest.main()
