"""Video acquisition and Drive-backed learning archive.

Drive-backed exports are resolved lazily so the package stays importable
where the Drive/evidence modules are not present; the names below are
still part of the public package API.
"""

from aios_work_system.acquisition.models import (
    AcquisitionRecord,
    SelectionCriteria,
    VideoCandidate,
)
from aios_work_system.acquisition.platforms import (
    AcquisitionDependencyError,
    AcquisitionPlatformError,
    BilibiliPlatformAdapter,
    PlatformAdapter,
    YouTubePlatformAdapter,
    YtDlpDownloader,
)
from aios_work_system.acquisition.selector import (
    RuleBasedVideoSelector,
    VideoSelector,
)

__all__ = [
    "AcquisitionDependencyError",
    "AcquisitionPipeline",
    "AcquisitionPlatformError",
    "AcquisitionRecord",
    "BilibiliPlatformAdapter",
    "DriveFileInfo",
    "DriveStorage",
    "EvidenceExtractionContext",
    "EvidenceExtractor",
    "GoogleDriveApiTransport",
    "GoogleDriveStorage",
    "JsonlRecordStore",
    "PlatformAdapter",
    "PR26VideoLearningAdapter",
    "RuleBasedVideoSelector",
    "SelectionCriteria",
    "VideoCandidate",
    "VideoSelector",
    "YtDlpDownloader",
    "YouTubePlatformAdapter",
]

_LAZY_EXPORTS = {
    "AcquisitionPipeline": (".pipeline", "AcquisitionPipeline"),
    "DriveFileInfo": (".drive", "DriveFileInfo"),
    "DriveStorage": (".drive", "DriveStorage"),
    "EvidenceExtractionContext": (".evidence", "EvidenceExtractionContext"),
    "EvidenceExtractor": (".evidence", "EvidenceExtractor"),
    "GoogleDriveApiTransport": (".drive", "GoogleDriveApiTransport"),
    "GoogleDriveStorage": (".drive", "GoogleDriveStorage"),
    "JsonlRecordStore": (".records", "JsonlRecordStore"),
    "PR26VideoLearningAdapter": (".evidence", "PR26VideoLearningAdapter"),
}


def __getattr__(name):
    """Lazily resolve Drive/evidence-backed exports (PEP 562)."""
    if name in _LAZY_EXPORTS:
        import importlib

        module_name, attribute = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_name, __package__)
        value = getattr(module, attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
