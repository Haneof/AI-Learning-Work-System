[CmdletBinding()]
param(
    [ValidateSet("4B", "9B")]
    [string]$ModelSize = "4B",

    [string]$ModelDirectory = (Join-Path $PSScriptRoot "..\models\qwen35"),

    [string]$ServerExe = "",

    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [ValidateRange(512, 131072)]
    [int]$ContextLength = 4096,

    [string]$GpuLayers = "auto",

    [switch]$SkipDownload
)

$ErrorActionPreference = "Stop"

$models = @{
    "4B" = @{
        Repo = "ggml-org/Qwen3.5-4B-GGUF"
        File = "Qwen3.5-4B-Q4_K_M.gguf"
        Sha256 = "217002fa8008ef4fc6d548353a3aebef055a96e6ff8e0e2c0953ef8254a89c14"
        Alias = "Qwen3.5-4B"
    }
    "9B" = @{
        Repo = "gguf/Qwen3.5-9B-GGUF"
        File = "qwen3.5-9b-Q4_K_M.gguf"
        Sha256 = "d784ce9eda1a5a7b51e8f705a9e6310844bf4f173654d115823c775fdea56d43"
        Alias = "Qwen3.5-9B"
    }
}

$model = $models[$ModelSize]
$modelDirectoryFull = [System.IO.Path]::GetFullPath($ModelDirectory)
$modelPath = Join-Path $modelDirectoryFull $model.File
$downloadUrl = "https://huggingface.co/$($model.Repo)/resolve/main/$($model.File)"

New-Item -ItemType Directory -Path $modelDirectoryFull -Force | Out-Null

if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
    if ($SkipDownload) {
        throw "Model file not found and -SkipDownload was specified: $modelPath"
    }

    $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
    if (-not $curl) {
        throw "curl.exe is required for resumable model downloads. Install/enable Windows curl first."
    }

    Write-Host "Downloading $($model.Repo) / $($model.File)"
    Write-Host "The model is several GB; the download is resumable."
    & $curl.Source --location --fail --retry 5 --retry-delay 2 --continue-at - --output $modelPath $downloadUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Model download failed (curl exit code $LASTEXITCODE). Re-run the script to resume."
    }
}

Write-Host "Verifying SHA-256..."
$actualHash = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $model.Sha256) {
    Remove-Item -LiteralPath $modelPath -Force
    throw "SHA-256 mismatch. The incomplete/corrupt model file was removed. Expected $($model.Sha256), got $actualHash."
}
Write-Host "Model checksum OK: $actualHash"

if (-not $ServerExe) {
    $command = Get-Command "llama-server.exe" -ErrorAction SilentlyContinue
    if (-not $command) {
        $command = Get-Command "llama-server" -ErrorAction SilentlyContinue
    }
    if ($command) {
        $ServerExe = $command.Source
    }
}

if (-not $ServerExe) {
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "llama-server was not found. Install llama.cpp (winget install --id ggml.llamacpp --exact) or pass -ServerExe <path>."
    }

    Write-Host "llama-server not found. Installing the llama.cpp Windows package with WinGet..."
    & $winget.Source install --id ggml.llamacpp --exact --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "WinGet could not install ggml.llamacpp. Install llama.cpp manually or pass -ServerExe."
    }

    $command = Get-Command "llama-server.exe" -ErrorAction SilentlyContinue
    if ($command) {
        $ServerExe = $command.Source
    } else {
        $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        if (Test-Path -LiteralPath $packageRoot) {
            $installedServer = Get-ChildItem -LiteralPath $packageRoot -Filter "llama-server.exe" -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match "ggml\.llamacpp" } |
                Select-Object -First 1
            if ($installedServer) {
                $ServerExe = $installedServer.FullName
            }
        }
    }
}

if (-not $ServerExe -or -not (Test-Path -LiteralPath $ServerExe -PathType Leaf)) {
    throw "llama-server executable not found. Install llama.cpp or pass its full path with -ServerExe."
}

$serverArguments = @(
    "--model", $modelPath,
    "--alias", $model.Alias,
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--ctx-size", "$ContextLength",
    "--n-gpu-layers", $GpuLayers,
    "--parallel", "1"
)

Write-Host ""
Write-Host "Starting llama-server:"
Write-Host "  Model:   $ModelSize / Q4_K_M"
Write-Host "  Context: $ContextLength"
Write-Host "  GPU:     $GpuLayers layer(s) (llama.cpp automatic fit)"
Write-Host "  API:     http://127.0.0.1:$Port/v1"
Write-Host "  Weights: $modelPath"
Write-Host "  Note:    loopback only; this script loads text GGUF weights (no mmproj vision file)."
Write-Host "Stop the server with Ctrl+C."
Write-Host ""

& $ServerExe @serverArguments
if ($LASTEXITCODE -ne 0) {
    throw "llama-server exited with code $LASTEXITCODE."
}
