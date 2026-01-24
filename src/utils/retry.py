"""Retry utilities with exponential backoff and jitter.

Provides decorators and utilities for handling transient failures
in MCP API calls and token exchanges.
"""

import functools
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Set, Tuple, Type, TypeVar, Union

import requests

logger = logging.getLogger(__name__)

# Type variable for generic function return type
T = TypeVar("T")


class RetryableError(Exception):
    """Error that can be retried."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0
    jitter_factor: float = 0.1  # ±10% jitter
    retryable_status_codes: Set[int] = field(
        default_factory=lambda: {429, 500, 502, 503, 504}
    )
    retryable_exceptions: Tuple[Type[Exception], ...] = field(
        default_factory=lambda: (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            RetryableError,
        )
    )

    def get_delay_with_jitter(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """
        Calculate delay for a given retry attempt.

        Uses exponential backoff with jitter, respecting Retry-After header if present.

        Args:
            attempt: Current retry attempt (0-indexed)
            retry_after: Optional Retry-After value from server

        Returns:
            Delay in seconds before next retry
        """
        if retry_after is not None:
            # Respect server's Retry-After, but add small jitter
            base = retry_after
        else:
            # Exponential backoff: base_delay * 2^attempt
            base = self.base_delay * (2 ** attempt)

        # Apply jitter (±jitter_factor)
        jitter = base * self.jitter_factor * (2 * random.random() - 1)
        delay = base + jitter

        # Clamp to max_delay
        return min(delay, self.max_delay)


# Pre-configured retry configs for common use cases
MCP_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=2.0,
    max_delay=60.0,
    jitter_factor=0.1,
    retryable_status_codes={429, 500, 502, 503, 504},
)

TOKEN_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    jitter_factor=0.1,
    retryable_status_codes={429, 500, 502, 503, 504},
)


def extract_retry_after(response: Optional[requests.Response]) -> Optional[float]:
    """
    Extract Retry-After header value from response.

    Args:
        response: HTTP response object

    Returns:
        Retry-After value in seconds, or None if not present
    """
    if response is None:
        return None

    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return None

    try:
        # Retry-After can be seconds (integer) or HTTP date
        # We only handle seconds format for simplicity
        return float(retry_after)
    except (ValueError, TypeError):
        return None


def with_retry(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that adds retry logic with exponential backoff.

    Args:
        config: Retry configuration (uses MCP_RETRY_CONFIG if not provided)
        on_retry: Optional callback called before each retry with
                  (attempt, exception, delay) arguments

    Returns:
        Decorated function with retry behavior

    Example:
        @with_retry(config=MCP_RETRY_CONFIG)
        def call_api():
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
    """
    if config is None:
        config = MCP_RETRY_CONFIG

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except config.retryable_exceptions as e:
                    last_exception = e

                    # Check if we've exhausted retries
                    if attempt >= config.max_retries:
                        logger.warning(
                            f"Retry exhausted for {func.__name__} after "
                            f"{config.max_retries + 1} attempts: {e}"
                        )
                        raise

                    # Extract retry-after if available
                    retry_after = None
                    if isinstance(e, RetryableError):
                        retry_after = e.retry_after

                    # Calculate delay
                    delay = config.get_delay_with_jitter(attempt, retry_after)

                    logger.info(
                        f"Retrying {func.__name__} (attempt {attempt + 1}/{config.max_retries + 1}) "
                        f"after {delay:.2f}s due to: {e}"
                    )

                    # Call on_retry callback if provided
                    if on_retry:
                        on_retry(attempt, e, delay)

                    time.sleep(delay)

                except requests.exceptions.HTTPError as e:
                    # Check if status code is retryable
                    if hasattr(e, "response") and e.response is not None:
                        status_code = e.response.status_code
                        if status_code in config.retryable_status_codes:
                            last_exception = e

                            if attempt >= config.max_retries:
                                logger.warning(
                                    f"Retry exhausted for {func.__name__} after "
                                    f"{config.max_retries + 1} attempts: HTTP {status_code}"
                                )
                                raise

                            retry_after = extract_retry_after(e.response)
                            delay = config.get_delay_with_jitter(attempt, retry_after)

                            logger.info(
                                f"Retrying {func.__name__} (attempt {attempt + 1}/{config.max_retries + 1}) "
                                f"after {delay:.2f}s due to HTTP {status_code}"
                            )

                            if on_retry:
                                on_retry(attempt, e, delay)

                            time.sleep(delay)
                            continue

                    # Non-retryable HTTP error
                    raise

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Unexpected state in retry loop for {func.__name__}")

        return wrapper

    return decorator


def is_retryable_status_code(
    status_code: int, config: Optional[RetryConfig] = None
) -> bool:
    """
    Check if a status code is retryable.

    Args:
        status_code: HTTP status code
        config: Retry configuration (uses MCP_RETRY_CONFIG if not provided)

    Returns:
        True if the status code should trigger a retry
    """
    if config is None:
        config = MCP_RETRY_CONFIG
    return status_code in config.retryable_status_codes


def create_retryable_error_from_response(
    response: requests.Response, message: Optional[str] = None
) -> RetryableError:
    """
    Create a RetryableError from an HTTP response.

    Args:
        response: HTTP response that triggered the error
        message: Optional custom error message

    Returns:
        RetryableError with status code and retry-after info
    """
    retry_after = extract_retry_after(response)
    error_message = message or f"HTTP {response.status_code}: {response.reason}"

    return RetryableError(
        message=error_message,
        status_code=response.status_code,
        retry_after=retry_after,
    )
