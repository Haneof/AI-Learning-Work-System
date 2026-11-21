"""Platform discovery and normalized resource candidate contracts."""

from aios_work_system.acquisition.bilibili import BilibiliSearchAdapter
from aios_work_system.acquisition.catalog import PlatformCatalog, PlatformDescriptor
from aios_work_system.acquisition.pipeline import AcquisitionDownloadPipeline
from aios_work_system.acquisition.models import (
    ResourceCandidate,
    SearchPage,
    SearchRequest,
    canonicalize_url,
    deduplicate_candidates,
)
from aios_work_system.acquisition.registry import AdapterRegistry, SourceSearchAdapter
from aios_work_system.acquisition.repository import CandidateRepository, CandidateStatus
from aios_work_system.acquisition.service import (
    PlatformSearchFailure,
    SearchBatchResult,
    SearchService,
)

__all__ = [
    "AcquisitionDownloadPipeline",
    "AdapterRegistry",
    "BilibiliSearchAdapter",
    "CandidateRepository",
    "CandidateStatus",
    "PlatformCatalog",
    "PlatformDescriptor",
    "PlatformSearchFailure",
    "ResourceCandidate",
    "SearchBatchResult",
    "SearchPage",
    "SearchRequest",
    "SearchService",
    "SourceSearchAdapter",
    "canonicalize_url",
    "deduplicate_candidates",
]
