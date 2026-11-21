"""Google Drive API storage with a small injectable transport boundary."""

from __future__ import annotations

import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class DriveConfigurationError(RuntimeError):
    """Raised when Google Drive OAuth configuration is incomplete."""


class DriveOperationError(RuntimeError):
    """Raised when a Google Drive API operation fails."""


@dataclass(frozen=True)
class DriveFileInfo:
    file_id: str
    name: str
    web_view_link: str | None
    size_bytes: int | None = None


@dataclass(frozen=True)
class DriveUploadResult:
    file: DriveFileInfo
    drive_path: str


class DriveTransport(Protocol):
    def find_folder(self, name: str, parent_id: str | None) -> str | None:
        """Find an existing direct child folder."""

    def create_folder(self, name: str, parent_id: str | None) -> str:
        """Create a direct child folder and return its file ID."""

    def upload_file(self, path: Path, parent_id: str) -> DriveFileInfo:
        """Upload a local file into a Drive folder."""

    def download_file(self, file_id: str, destination: Path) -> None:
        """Download a Drive file to a local path."""


class GoogleDriveApiTransport:
    """Real Google Drive v3 transport using official Google client libraries."""

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]

    def __init__(self, service: object) -> None:
        self.service = service

    @classmethod
    def from_environment(cls) -> GoogleDriveApiTransport:
        credentials_value = os.environ.get("GOOGLE_DRIVE_CREDENTIALS", "").strip()
        if not credentials_value:
            raise DriveConfigurationError(
                "GOOGLE_DRIVE_CREDENTIALS must point to a Google OAuth desktop-client "
                "JSON file. See docs/GOOGLE_DRIVE_SETUP.md."
            )
        credentials_path = Path(credentials_value).expanduser().resolve()
        if not credentials_path.is_file():
            raise DriveConfigurationError(
                f"Google Drive OAuth client file does not exist: {credentials_path}"
            )

        token_value = os.environ.get(
            "GOOGLE_DRIVE_TOKEN", ".secrets/google-drive-token.json"
        ).strip()
        token_path = Path(token_value).expanduser().resolve()
        token_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise DriveConfigurationError(
                "Google Drive API dependencies are missing. Install with: "
                'python -m pip install -e ".[acquisition]"'
            ) from exc

        credentials = None
        if token_path.is_file():
            credentials = Credentials.from_authorized_user_file(str(token_path), cls.SCOPES)
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), cls.SCOPES)
                credentials = flow.run_local_server(port=0)
            token_path.write_text(credentials.to_json(), encoding="utf-8")
            try:
                token_path.chmod(0o600)
            except OSError:
                # Windows ACLs are managed by the user account instead.
                pass

        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return cls(service)

    @staticmethod
    def _escape_query_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def find_folder(self, name: str, parent_id: str | None) -> str | None:
        safe_name = self._escape_query_value(name)
        parent_clause = f"'{parent_id}' in parents" if parent_id else "'root' in parents"
        query = (
            f"{parent_clause} and name = '{safe_name}' "
            "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        response = (
            self.service.files()
            .list(q=query, spaces="drive", pageSize=100, fields="files(id,name)")
            .execute()
        )
        files = response.get("files") or []
        return files[0]["id"] if files else None

    def create_folder(self, name: str, parent_id: str | None) -> str:
        body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            body["parents"] = [parent_id]
        request = self.service.files().create(body=body, fields="id,name,mimeType,webViewLink")
        response = request.execute()
        return response["id"]

    def upload_file(self, path: Path, parent_id: str) -> DriveFileInfo:
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise DriveConfigurationError(
                "Google Drive upload support is missing. Install with: "
                'python -m pip install -e ".[acquisition]"'
            ) from exc
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        media = MediaFileUpload(
            str(path),
            mimetype=mime_type,
            resumable=True,
            chunksize=8 * 1024 * 1024,
        )
        response = (
            self.service.files()
            .create(
                body={"name": path.name, "parents": [parent_id]},
                media_body=media,
                fields="id,name,webViewLink,size",
            )
            .execute()
        )
        return DriveFileInfo(
            file_id=response["id"],
            name=response.get("name", path.name),
            web_view_link=response.get("webViewLink"),
            size_bytes=int(response["size"]) if response.get("size") else path.stat().st_size,
        )

    def download_file(self, file_id: str, destination: Path) -> None:
        try:
            from googleapiclient.http import MediaIoBaseDownload
        except ImportError as exc:
            raise DriveConfigurationError(
                "Google Drive download support is missing. Install with: "
                'python -m pip install -e ".[acquisition]"'
            ) from exc

        request = self.service.files().get_media(fileId=file_id)
        temporary = destination.with_name(destination.name + ".part")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with temporary.open("wb") as output:
                downloader = MediaIoBaseDownload(output, request, chunksize=8 * 1024 * 1024)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


class DriveStorage(Protocol):
    def upload_video(self, local_video: str | Path, candidate: object) -> DriveUploadResult:
        """Store a video at AI-Learning/platform/uploader/series."""

    def download_file(self, file_id: str, destination: str | Path) -> Path:
        """Retrieve an archived video to a local working path."""


def _folder_component(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    if not text or text.casefold() in {"unknown", "none", "null"}:
        text = fallback
    text = re.sub(r'[\\/<>"|?*\x00-\x1f:]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return (text or fallback)[:120]


class GoogleDriveStorage:
    """Folder-aware storage backed by the Google Drive API transport."""

    def __init__(self, transport: DriveTransport) -> None:
        self.transport = transport

    @classmethod
    def from_environment(cls) -> GoogleDriveStorage:
        return cls(GoogleDriveApiTransport.from_environment())

    def _ensure_folder(self, name: str, parent_id: str | None) -> str:
        existing = self.transport.find_folder(name, parent_id)
        return existing or self.transport.create_folder(name, parent_id)

    def upload_video(self, local_video: str | Path, candidate: object) -> DriveUploadResult:
        path = Path(local_video).expanduser().resolve(strict=True)
        platform = _folder_component(getattr(candidate, "platform", None), "unknown")
        uploader = _folder_component(getattr(candidate, "uploader", None), "unknown")
        series_value = getattr(candidate, "series", None)
        series = _folder_component(series_value, "未分组")
        names = ["AI-Learning", platform, uploader, series]
        parent_id: str | None = None
        for name in names:
            parent_id = self._ensure_folder(name, parent_id)
        if parent_id is None:
            raise DriveOperationError("Could not resolve the destination Drive folder")
        uploaded = self.transport.upload_file(path, parent_id)
        return DriveUploadResult(
            file=uploaded,
            drive_path="/".join(names + [uploaded.name]),
        )

    def download_file(self, file_id: str, destination: str | Path) -> Path:
        output = Path(destination).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        self.transport.download_file(file_id, output)
        if not output.is_file():
            raise DriveOperationError(
                f"Google Drive download returned without creating local file: {output}"
            )
        return output
