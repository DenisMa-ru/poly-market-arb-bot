from __future__ import annotations

import logging

import httpx
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

logger = logging.getLogger(__name__)


def _log_retry(state: RetryCallState) -> None:
    if state.outcome and state.outcome.failed:
        exc = state.outcome.exception()
        logger.warning("retry", extra={"attempt": state.attempt_number, "exc": str(exc) if exc else None})


retry_api_call = retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)),
    wait=wait_exponential_jitter(initial=0.25, max=4.0, jitter=0.5),
    stop=stop_after_attempt(4),
    before_sleep=_log_retry,
    reraise=True,
)

