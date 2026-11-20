"""Offline media ingestion primitives."""

from aios_work_system.media.download import (
    Aria2Adapter,
    DownloadError,
    DownloadRequest,
    DownloadResult,
    DownloadService,
    DownloadVerifier,
    YtDlpAdapter,
)
from aios_work_system.media.ffmpeg import FFmpegProcessor, MediaProcessingError, NoAudioStreamError
from aios_work_system.media.source import SegmentRecord, SourceManifest, register_source
from aios_work_system.media.tasks import MediaTaskError, TaskJournal

__all__ = [
    "Aria2Adapter",
    "DownloadError",
    "DownloadRequest",
    "DownloadResult",
    "DownloadService",
    "DownloadVerifier",
    "FFmpegProcessor",
    "MediaProcessingError",
    "MediaTaskError",
    "NoAudioStreamError",
    "SegmentRecord",
    "SourceManifest",
    "TaskJournal",
    "YtDlpAdapter",
    "register_source",
]
