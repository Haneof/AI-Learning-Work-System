# Google Drive: Archive Layout and API Authorization

## Archive target

The tutorial collection is intended to live in the user's 5TB Google Drive. The target downloader is a cloud downloader that writes directly to Drive; bulk videos should not be scattered among local workstation folders or downloaded as ungrouped singles.

Organize videos by platform, creator, and series/course:

```text
AI-Learning/
  <platform>/
    <creator>/
      <series-or-course>/
        <video-file>
```

Each video must also have a download record containing at least its original source link and platform. Keep creator, series/course, title, download time, Drive file ID/link/path, content SHA-256, size, and license metadata when available. A missing series may use an explicit `unassigned` folder, but the record should preserve the unknown value rather than inventing a course name.

## Current API authorization helper

The repository's current Google Drive storage adapter uses the official Google Drive API with the user's own Google OAuth desktop credentials. An existing ChatGPT Drive connection is separate from API credentials used by this Python application; the code requires its own OAuth desktop-client JSON and token file.

The Drive API helper is an existing storage integration component. It does **not** by itself implement the target cloud-downloader workflow or prove that a cloud downloader can stream files directly into the 5TB archive.

## One-time Google Cloud setup for the API adapter

1. Open Google Cloud Console and create or select a project.
2. Enable Google Drive API.
3. Configure the OAuth consent screen for the archive-owning account.
4. Create an OAuth Client ID with application type Desktop app.
5. Download the client JSON and keep it outside the repository.
6. Store it, for example, at `%USERPROFILE%\\.secrets\\google-drive-client.json`.

The acquisition code requests the `drive.file` scope. On first run, the installed-app OAuth flow opens a browser for consent and saves a refresh token locally.

## Environment variables (PowerShell)

```powershell
$env:GOOGLE_DRIVE_CREDENTIALS = "$env:USERPROFILE\\.secrets\\google-drive-client.json"
$env:GOOGLE_DRIVE_TOKEN = "$env:USERPROFILE\\.secrets\\google-drive-token.json"
python -c "from aios_work_system.acquisition import GoogleDriveStorage; GoogleDriveStorage.from_environment(); print('Drive OAuth ready')"
```

If `GOOGLE_DRIVE_TOKEN` is omitted, the default is `.secrets/google-drive-token.json` relative to the current working directory. `GOOGLE_DRIVE_CREDENTIALS` must point to the downloaded OAuth client JSON.

## Security and operations

- Never add OAuth client JSON, token JSON, client secrets, or refresh tokens to Git.
- Do not share the token file. Revoke it in Google Account security settings if the local machine is lost or the token is exposed.
- CI deliberately has no Drive secret and tests storage through a fake transport.
- Keep the original Drive archive; do not delete source videos after extraction.
- Preserve the creator/series hierarchy when moving, copying, or reprocessing the archive.
