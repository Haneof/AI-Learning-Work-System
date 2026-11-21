# Google Drive API: one-time authorization

## Important distinction

This repository uploads through the official Google Drive API using the user's own
Google OAuth desktop credentials. An existing ChatGPT Drive connection is separate
from API credentials used by this Python application; this code needs its own OAuth
desktop-client JSON and token file.

## One-time Google Cloud setup

1. Open the Google Cloud Console and create or select a project.
2. Enable **Google Drive API** for that project.
3. Configure the OAuth consent screen for the account that owns the Drive archive.
4. Create an OAuth Client ID with application type **Desktop app**.
5. Download the client JSON. Do not paste its contents into source code or commit it.
6. Put it outside the repository, for example:
   \`%USERPROFILE%\\.secrets\\google-drive-client.json\`.

The acquisition code requests the \`drive.file\` scope. This is narrower than full Drive
access: it lets this application create and manage files/folders it creates or the user
opens with it. On first run the installed-app OAuth flow opens a browser for consent.
The returned refresh token is saved locally for subsequent runs.

## Environment variables (PowerShell)

~~~powershell
$env:GOOGLE_DRIVE_CREDENTIALS = "$env:USERPROFILE\\.secrets\\google-drive-client.json"
$env:GOOGLE_DRIVE_TOKEN = "$env:USERPROFILE\\.secrets\\google-drive-token.json"
python -c "from aios_work_system.acquisition import GoogleDriveStorage; GoogleDriveStorage.from_environment(); print('Drive OAuth ready')"
~~~

If \`GOOGLE_DRIVE_TOKEN\` is omitted, the default is
\`.secrets/google-drive-token.json\` relative to the current working directory.
\`GOOGLE_DRIVE_CREDENTIALS\` is required and must point to the downloaded OAuth client
JSON. The credential file and token are never written into this repository by the
code. The token is created with owner-only file permissions where the OS supports it.

## Archive layout

The first upload creates and reuses this app-managed folder hierarchy:

~~~text
AI-Learning/
  youtube/
    <uploader>/
      <series>/
        <video-file>.mp4
      未分组/
        <video-file>.mp4
~~~

If playlist/series metadata is absent, the folder component is \`未分组\`. The record stores the
Drive file ID, webViewLink (when provided by Drive), and full path including filename.

## Security and operations

- Never add OAuth client JSON, token JSON, client secrets, or refresh tokens to Git.
- Do not share the token file. Revoke it in the Google Account security settings if
  the local machine is lost or the token is exposed.
- The API token is refreshed by Google auth libraries. If access is revoked, delete
  only the local token JSON and repeat the consent flow.
- CI deliberately has no Drive secret and tests the storage contract with a fake
  transport. This does not replace the production GoogleDriveApiTransport.
- The Drive archive is retained after extraction. Only the local Drive working copy
  and local downloader staging file are deleted and verified.
