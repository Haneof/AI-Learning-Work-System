"""Download open model weights for local tutorial-video extraction (no inference/API calls)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MODELS = {
    "showui_2b": {
        "repo_id": "showlab/ShowUI-2B",
        "license": "MIT",
        "local_path": "showui-2b",
        "kind": "transformers_snapshot",
        "role": "primary_ui_grounding",
    },
    "ui_tars_2b": {
        "repo_id": "ByteDance-Seed/UI-TARS-2B-SFT",
        "license": "Apache-2.0",
        "local_path": "ui-tars-2b",
        "kind": "transformers_snapshot",
        "role": "secondary_small_ui_grounding",
    },
    "aurum_4b": {
        "repo_id": "2Beyes/Aurum-4B-Uncensored-GGUF",
        "filename": "Aurum-4B-Q4_K_M.gguf",
        "license": "Apache-2.0",
        "local_path": "aurum-4b-q4.gguf",
        "kind": "gguf_file",
        "role": "primary_decision_episode_json",
    },
    "ui_tars_7b": {
        "repo_id": "ByteDance-Seed/UI-TARS-7B-SFT",
        "license": "Apache-2.0",
        "local_path": "ui-tars-7b",
        "kind": "transformers_snapshot",
        "role": "large_ui_grounding_fallback",
    },
    "deepseek_9b": {
        "repo_id": "yan2026/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF",
        "filename": "DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-Q4_K_M.gguf",
        "license": "Apache-2.0",
        "local_path": "deepseek-v4-pro-9b-q4.gguf",
        "kind": "gguf_file",
        "role": "large_decision_episode_fallback",
    },
}


def _download_snapshot(repo_id: str, destination: Path) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(destination),
        local_files_only=False,
    )
    if not destination.is_dir() or not any(destination.iterdir()):
        raise RuntimeError(f"no weight files were downloaded for {repo_id}")
    return {"status": "downloaded", "path": str(destination.resolve())}


def _download_gguf(repo_id: str, filename: str, destination: Path) -> dict[str, Any]:
    from huggingface_hub import hf_hub_download

    destination.parent.mkdir(parents=True, exist_ok=True)
    downloaded = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(destination.parent),
        local_files_only=False,
    )
    source = Path(downloaded)
    if source.resolve() != destination.resolve():
        destination.write_bytes(source.read_bytes())
    if not destination.is_file() or destination.stat().st_size < 1024:
        raise RuntimeError(f"GGUF weight download is missing or too small: {destination}")
    return {
        "status": "downloaded",
        "path": str(destination.resolve()),
        "size_bytes": destination.stat().st_size,
    }


def download_models(
    model_dir: Path,
    *,
    include_large_fallbacks: bool = False,
) -> dict[str, Any]:
    """Download small primary models and Aurum 4B; optional large fallbacks are opt-in."""
    try:
        import huggingface_hub
    except ImportError as exc:
        raise RuntimeError(
            "Install video-open-models dependencies before downloading model weights."
        ) from exc

    model_dir.mkdir(parents=True, exist_ok=True)
    selected = ["showui_2b", "ui_tars_2b", "aurum_4b"]
    if include_large_fallbacks:
        selected.extend(["ui_tars_7b", "deepseek_9b"])

    report: dict[str, Any] = {
        "schema_version": "local-open-model-manifest-v1",
        "download_only": True,
        "inference_performed": False,
        "model_inference_provider_calls": 0,
        "model_dir": str(model_dir.resolve()),
        "huggingface_hub_version": huggingface_hub.__version__,
        "models": {},
    }
    for key in selected:
        metadata = MODELS[key]
        destination = model_dir / metadata["local_path"]
        if metadata["kind"] == "transformers_snapshot":
            result = _download_snapshot(metadata["repo_id"], destination)
        else:
            result = _download_gguf(
                metadata["repo_id"],
                metadata["filename"],
                destination,
            )
        report["models"][key] = {
            **metadata,
            **result,
        }

    manifest_path = model_dir / "model-manifest.json"
    manifest_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report["manifest_path"] = str(manifest_path.resolve())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("artifacts/models"),
    )
    parser.add_argument(
        "--include-large-fallbacks",
        action="store_true",
        help=(
            "Also download the 7B UI grounding and 9B episode fallback weights. "
            "The pipeline only loads a fallback after its small-model quality gate fails."
        ),
    )
    args = parser.parse_args()
    report = download_models(
        args.model_dir,
        include_large_fallbacks=args.include_large_fallbacks,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
