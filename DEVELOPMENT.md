# Local Development Quickstart

## Requirements

- Python 3.11 or 3.12
- Git
- Windows PowerShell, macOS, or Linux shell

The bootstrap has no runtime third-party dependencies. The health endpoint uses the Python standard library.

## Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m aios_work_system serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/health`. Stop the server with Ctrl+C.

## macOS / Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m aios_work_system serve --host 127.0.0.1 --port 8000
```

## Scope and limitations

This is an engineering bootstrap, not the complete AIOS application. It deliberately has no model, database, vector store, browser automation, media parser, or agent framework dependency. The `/health` endpoint reports process liveness only; it does not yet verify downstream dependencies. Do not expose the development server to the public internet.

The repository license has not yet been selected. Do not add a license grant or redistribute this code under an assumed license until the owner confirms the choice.
