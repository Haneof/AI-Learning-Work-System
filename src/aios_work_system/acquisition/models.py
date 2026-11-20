"""Normalized contracts for platform-based resource discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref_src",
    "spm",
}


def canonicalize_url(url: str) -> str:
    """Normalize a resource URL without discarding platform access parameters."""
    value = url.strip()
    if not value:
        raise ValueError("url must not be empty")
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError("resource URL must be an absolute HTTP(S) URL")
    hostname = (parts.hostname or "").lower()
    if not hostname:
        raise ValueError("resource URL must contain a hostname")
    port = parts.port
    netloc = hostname
    if port and not ((parts.scheme.lower() == "http" and port == 80) or (
        parts.scheme.lower() == "https" and port == 443
    )):
        netloc = f"{hostname}:{port}"
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
    ]
    query.sort()
    return urlunsplit(
        (parts.scheme.lower(), netloc, parts.path or "/", urlencode(query), "")
    )


@dataclass(frozen=True)
class SearchRequest:
    platform: str
    keyword: str
    page: int = 1
    page_size: int = 20
    language: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.platform.strip():
            raise ValueError("platform must not be empty")
        if not self.keyword.strip():
            raise ValueError("keyword must not be empty")
        if self.page < 1:
            raise ValueError("page must be at least 1")
        if not 1 <= self.page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")


def _new_candidate_id() -> str:
    import uuid

    return str(uuid.uuid4())


@dataclass(frozen=True)
class ResourceCandidate:
    platform: str
    url: str
    title: str
    candidate_id: str = field(default_factory=_new_candidate_id)
    canonical_url: str = ""
    author_name: str | None = None
    author_url: str | None = None
    description: str | None = None
    published_at: str | None = None
    duration_seconds: float | None = None
    language: str | None = None
    thumbnail_url: str | None = None
    metrics: dict[str, int | float | str] = field(default_factory=dict)
    discovered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    search_keyword: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.platform.strip():
            raise ValueError("platform must not be empty")
        normalized = canonicalize_url(self.url)
        object.__setattr__(self, "canonical_url", self.canonical_url or normalized)
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("duration_seconds must not be negative")


@dataclass(frozen=True)
class SearchPage:
    platform: str
    keyword: str
    page: int
    candidates: tuple[ResourceCandidate, ...]
    has_more: bool | None = None
    next_page: int | None = None
    warnings: tuple[str, ...] = ()
    provider_name: str = ""
    provider_version: str = ""


def deduplicate_candidates(
    candidates: list[ResourceCandidate],
) -> list[ResourceCandidate]:
    """Keep the first candidate for each platform + canonical URL pair."""
    seen: set[tuple[str, str]] = set()
    unique: list[ResourceCandidate] = []
    for candidate in candidates:
        key = (candidate.platform.lower(), candidate.canonical_url)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique
