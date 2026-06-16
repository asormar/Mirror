"""SEC EDGAR HTTP client.

Owns the SEC-mandated User-Agent format and the 8 req/s budget. All
requests are routed through a token bucket + a concurrency semaphore,
and a TTL cache deduplicates repeat fetches within a configurable window.

The User-Agent format `AppName contact@email` is REQUIRED by SEC EDGAR.
A missing or generic UA results in a 403/429 and risks the source IP
being banned.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any

import httpx
from cachetools import TTLCache

from app.core.config import settings
from app.pipeline.clients.rate_limiter import TokenBucket

logger = logging.getLogger(__name__)

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_ARCHIVES_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{filename}"
)


class SecEdgarClient:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        requests_per_second: float | None = None,
        max_concurrent: int = 4,
        cache_ttl_seconds: float = 300.0,
        cache_maxsize: int = 1024,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._user_agent = user_agent or settings.sec_edgar_user_agent
        rate = (
            requests_per_second
            if requests_per_second is not None
            else settings.sec_edgar_rate_limit_per_sec
        )
        self._rate_limiter = TokenBucket(rate=float(rate))
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._cache: TTLCache[str, bytes] = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl_seconds)
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout_seconds

    async def __aenter__(self) -> SecEdgarClient:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=self._timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _fetch(self, url: str) -> bytes:
        cached = self._cache.get(url)
        if cached is not None:
            return cached

        if self._client is None:
            raise RuntimeError("SecEdgarClient must be used as an async context manager")

        await self._rate_limiter.acquire()
        async with self._semaphore:
            logger.debug("SEC fetch url=%s", url)
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.content

        self._cache[url] = data
        return data

    async def get_submissions(self, cik: str) -> dict[str, Any]:
        padded = str(cik).zfill(10)
        url = EDGAR_SUBMISSIONS_URL.format(cik=padded)
        data = await self._fetch(url)
        result: dict[str, Any] = json.loads(data)
        return result

    async def get_filing_bytes(self, cik: str, accession_number: str, filename: str) -> bytes:
        accession_nodash = accession_number.replace("-", "")
        cik_int = str(int(cik))
        url = EDGAR_ARCHIVES_URL.format(
            cik_int=cik_int, accession_nodash=accession_nodash, filename=filename
        )
        return await self._fetch(url)

    async def get_filing_text(self, cik: str, accession_number: str, filename: str) -> str:
        data = await self.get_filing_bytes(cik, accession_number, filename)
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def find_new_13f_filings(
        submissions: Mapping[str, Any],
        *,
        known_accession_numbers: set[str],
    ) -> list[dict[str, Any]]:
        recent = submissions.get("filings", {}).get("recent", {})
        if not recent:
            return []
        forms: list[str] = recent.get("form", [])
        accessions: list[str] = recent.get("accessionNumber", [])
        primary_docs: list[str] = recent.get("primaryDocument", [])
        filing_dates: list[str] = recent.get("filingDate", [])
        report_dates: list[str] = recent.get("reportDate", [])

        results: list[dict[str, Any]] = []
        for i, form in enumerate(forms):
            if form not in {"13F-HR", "13F-HR/A"}:
                continue
            acc = accessions[i]
            if acc in known_accession_numbers:
                continue
            results.append(
                {
                    "form": form,
                    "accession_number": acc,
                    "primary_document": primary_docs[i],
                    "filing_date": filing_dates[i],
                    "report_date": report_dates[i] or None,
                }
            )
        return results
