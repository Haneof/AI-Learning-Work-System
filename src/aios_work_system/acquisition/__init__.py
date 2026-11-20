"""Platform discovery and normalized resource candidate contracts."""

from aios_work_system.acquisition.models import (
    ResourceCandidate,
    SearchPage,
    SearchRequest,
    canonicalize_url,
    deduplicate_candidates,
)
from aios_work_system.acquisition.registry import AdapterRegistry, SourceSearchAdapter

__all__ = [
    "AdapterRegistry",
    "ResourceCandidate",
    "SearchPage",
    "SearchRequest",
    "SourceSearchAdapter",
    "canonicalize_url",
    "deduplicate_candidates",
]
