"""Platform-neutral video acquisition contracts and adapters."""

from aios_work_system.acquisition.models import SelectionCriteria, VideoCandidate
from aios_work_system.acquisition.platforms import (
    AcquisitionDependencyError,
    AcquisitionPlatformError,
    BilibiliPlatformAdapter,
    PlatformAdapter,
    YouTubePlatformAdapter,
    YtDlpDownloader,
)
from aios_work_system.acquisition.selector import RuleBasedVideoSelector, VideoSelector

__all__ = [
    "AcquisitionDependencyError",
    "AcquisitionPlatformError",
    "BilibiliPlatformAdapter",
    "PlatformAdapter",
    "RuleBasedVideoSelector",
    "SelectionCriteria",
    "VideoCandidate",
    "VideoSelector",
    "YtDlpDownloader",
    "YouTubePlatformAdapter",
]
