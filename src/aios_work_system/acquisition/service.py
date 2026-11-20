"""Search orchestration with bounded concurrency and partial-failure isolation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aios_work_system.acquisition.models import (
    ResourceCandidate,
    SearchRequest,
    deduplicate_candidates,
)
from aios_work_system.acquisition.registry import AdapterRegistry


@dataclass(frozen=True)
class PlatformSearchFailure:
    platform: str
    keyword: str
    error_type: str
    message: str


@dataclass(frozen=True)
class SearchBatchResult:
    keyword: str
    candidates: tuple[ResourceCandidate, ...]
    succeeded_platforms: tuple[str, ...]
    failures: tuple[PlatformSearchFailure, ...]


class SearchService:
    """Fan out one keyword to selected platforms without losing partial results."""

    def __init__(
        self,
        registry: AdapterRegistry,
        *,
        max_concurrency: int = 4,
        timeout_seconds: float = 20.0,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._registry = registry
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._timeout_seconds = timeout_seconds

    async def search(self, request: SearchRequest):
        adapter = self._registry.get(request.platform)
        async with self._semaphore:
            return await asyncio.wait_for(
                adapter.search(request), timeout=self._timeout_seconds
            )

    async def search_many(
        self,
        keyword: str,
        platforms: tuple[str, ...] | list[str],
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchBatchResult:
        if not keyword.strip():
            raise ValueError("keyword must not be empty")
        selected = tuple(dict.fromkeys(p.strip().lower() for p in platforms))
        if not selected or any(not p for p in selected):
            raise ValueError("at least one non-empty platform is required")
        for platform in selected:
            self._registry.get(platform)

        requests = [
            SearchRequest(platform=p, keyword=keyword, page=page, page_size=page_size)
            for p in selected
        ]
        results = await asyncio.gather(
            *(self._search_captured(request) for request in requests)
        )
        candidates: list[ResourceCandidate] = []
        succeeded: list[str] = []
        failures: list[PlatformSearchFailure] = []
        for platform, result in zip(selected, results, strict=True):
            if isinstance(result, PlatformSearchFailure):
                failures.append(result)
            else:
                succeeded.append(platform)
                candidates.extend(result.candidates)
        return SearchBatchResult(
            keyword=keyword,
            candidates=tuple(deduplicate_candidates(candidates)),
            succeeded_platforms=tuple(succeeded),
            failures=tuple(failures),
        )

    async def _search_captured(self, request: SearchRequest):
        try:
            return await self.search(request)
        except Exception as exc:
            return PlatformSearchFailure(
                platform=request.platform,
                keyword=request.keyword,
                error_type=type(exc).__name__,
                message=str(exc),
            )
