"""Video acquisition and Drive-backed learning archive."""

from aios_work_system.acquisition.drive import (
    DriveFileInfo,
    DriveStorage,
    GoogleDriveApiTransport,
    GoogleDriveStorage,
)
from aios_work_system.acquisition.evidence import (
    EvidenceExtractionContext,
    EvidenceExtractor,
    PR26VideoLearningAdapter,
)
from aios_work_system.acquisition.models import (
    AcquisitionRecord,
    SelectionCriteria,
    VideoCandidate,
)
from aios_work_system.acquisition.pipeline import AcquisitionPipeline
from aios_work_system.acquisition.platforms import (
    AcquisitionDependencyError,
    AcquisitionPlatformError,
    BilibiliPlatformAdapter,
    PlatformAdapter,
    YouTubePlatformAdapter,
    YtDlpDownloader,
)
from aios_work_system.acquisition.records import JsonlRecordStore
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
