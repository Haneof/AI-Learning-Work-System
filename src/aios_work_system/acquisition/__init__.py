"""Platform discovery and normalized resource candidate contracts."""

from aios_work_system.acquisition.models import (
    ResourceCandidate,
    SearchPage,
    SearchRequest,
    canonicalize_url,
    deduplicate_candidates,
)
from aios_work_system.acquisition.registry import AdapterRegistry, SourceSearchAdapter
from aios_work_system.acquisition.service import (
    PlatformSearchFailure,
    SearchBatchResult,
    SearchService,
)
from aios_work_system.acquisition.catalog import PlatformCatalog, PlatformDescriptor
from aios_work_system.acquisition.bilibili import BilibiliSearchAdapter

__all__ = [
    "AdapterRegistry",
    "BilibiliSearchAdapter",
    "PlatformCatalog",
    "PlatformDescriptor",
    "PlatformSearchFailure",
    "ResourceCandidate",
    "SearchBatchResult",
    "SearchPage",
    "SearchService",
    "SearchRequest",
    "SourceSearchAdapter",
    "canonicalize_url",
    "deduplicate_candidates",
]
