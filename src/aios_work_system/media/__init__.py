"""Offline media ingestion primitives."""

from aios_work_system.media.adapters_faster_whisper import FasterWhisperASRAdapter
from aios_work_system.media.adapters_paddleocr import PaddleOCRAdapter
from aios_work_system.media.analysis import (
    AnalysisArtifact,
    AnalysisStatus,
    MediaAnalysisPipeline,
    MediaAnalysisRepository,
    MediaAnalysisResult,
)
from aios_work_system.media.assets import MediaAsset, MediaAssetRepository
from aios_work_system.media.download import (
    Aria2Adapter,
    DownloadError,
    DownloadRequest,
    DownloadResult,
    DownloadService,
    DownloadVerifier,
    YtDlpAdapter,
)
from aios_work_system.media.download_jobs import (
    DownloadJob,
    DownloadJobRepository,
    DownloadJobStatus,
)
from aios_work_system.media.download_progress import DownloadProgress
from aios_work_system.media.download_runner import DownloadJobExecutor
from aios_work_system.media.ffmpeg import (
    FFmpegProcessor,
    MediaProcessingError,
    NoAudioStreamError,
)
from aios_work_system.media.source import SegmentRecord, SourceManifest, register_source
from aios_work_system.media.tasks import MediaTaskError, TaskJournal

__all__ = [
    "AnalysisArtifact",
    "AnalysisStatus",
    "Aria2Adapter",
    "MediaAsset",
    "MediaAssetRepository",
    "MediaAnalysisPipeline",
    "MediaAnalysisRepository",
    "MediaAnalysisResult",
    "DownloadError",
    "DownloadJob",
    "DownloadJobExecutor",
    "DownloadJobRepository",
    "DownloadJobStatus",
    "DownloadProgress",
    "DownloadRequest",
    "DownloadResult",
    "DownloadService",
    "DownloadVerifier",
    "FasterWhisperASRAdapter",
    "PaddleOCRAdapter",
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
