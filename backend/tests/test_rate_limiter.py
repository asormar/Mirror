"""Unit tests for the rate-limiter token bucket."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.pipeline.clients.rate_limiter import TokenBucket


@pytest.mark.asyncio
async def test_acquire_does_not_block_within_capacity() -> None:
    bucket = TokenBucket(rate=10.0, capacity=10.0)
    start = time.monotonic()
    for _ in range(5):
        await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.2


@pytest.mark.asyncio
async def test_acquire_blocks_when_capacity_exhausted() -> None:
    bucket = TokenBucket(rate=5.0, capacity=1.0)
    await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15


def test_rejects_zero_or_negative_rate() -> None:
    with pytest.raises(ValueError):
        TokenBucket(rate=0)
    with pytest.raises(ValueError):
        TokenBucket(rate=-1)


@pytest.mark.asyncio
async def test_refills_over_time() -> None:
    bucket = TokenBucket(rate=100.0, capacity=1.0)
    await bucket.acquire()
    await asyncio.sleep(0.05)
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05
