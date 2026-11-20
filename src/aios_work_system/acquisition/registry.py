"""Platform search adapter contracts and registry."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aios_work_system.acquisition.models import SearchPage, SearchRequest


@runtime_checkable
class SourceSearchAdapter(Protocol):
    """One platform integration; implementations own platform-specific behavior."""

    platform: str
    name: str
    version: str

    async def search(self, request: SearchRequest) -> SearchPage:
        """Return normalized candidates for one platform and one page."""


class AdapterRegistry:
    """Explicit registry; adapters are injected and never imported implicitly."""

    def __init__(self) -> None:
        self._adapters: dict[str, SourceSearchAdapter] = {}

    def register(self, adapter: SourceSearchAdapter) -> None:
        platform = adapter.platform.strip().lower()
        if not platform:
            raise ValueError("adapter platform must not be empty")
        if platform in self._adapters:
            raise ValueError(f"search adapter already registered for {platform}")
        self._adapters[platform] = adapter

    def get(self, platform: str) -> SourceSearchAdapter:
        key = platform.strip().lower()
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise KeyError(f"no search adapter registered for platform: {key}") from exc

    def platforms(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))
