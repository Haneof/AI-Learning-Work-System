"""Machine-readable platform and adapter capability catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformDescriptor:
    platform: str
    display_name: str
    capabilities: tuple[str, ...]
    adapter_name: str | None = None
    adapter_version: str | None = None
    verified_live: bool = False
    status: str = "not_configured"
    notes: str = ""


class PlatformCatalog:
    """Catalog descriptors separately from adapter registration and runtime health."""

    def __init__(self, descriptors: tuple[PlatformDescriptor, ...] = ()) -> None:
        self._items: dict[str, PlatformDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: PlatformDescriptor) -> None:
        key = descriptor.platform.strip().lower()
        if not key:
            raise ValueError("platform must not be empty")
        if key in self._items:
            raise ValueError(f"platform already cataloged: {key}")
        self._items[key] = descriptor

    def get(self, platform: str) -> PlatformDescriptor:
        try:
            return self._items[platform.strip().lower()]
        except KeyError as exc:
            raise KeyError(f"platform not cataloged: {platform}") from exc

    def list(self) -> tuple[PlatformDescriptor, ...]:
        return tuple(self._items[key] for key in sorted(self._items))
