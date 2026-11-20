# Offline tutorial media preparation

The tutorial media preparation command supports two modes.

## Automatic download

    python scripts/prepare_tutorial_media.py --output-dir artifacts/tutorial-media

The script downloads the pinned Wikimedia Commons WebM, then verifies the published byte size and SHA-1 before extracting frames.

## Manually downloaded file

If the machine running the script cannot access Wikimedia Commons, download the original file from the [Commons source page](https://commons.wikimedia.org/wiki/File:Content_Translation_Screencast_(English).webm) using a browser on a machine with access. Copy the original WebM to the project machine and run:

    python scripts/prepare_tutorial_media.py --media-file "/path/to/Content_Translation_Screencast_(English).webm" --output-dir artifacts/tutorial-media

The local file is accepted only if it matches both pinned source checks:

- Expected size: 16,599,498 bytes
- Expected SHA-1: `8eb92107393e1896ddb2c03f0c6cfd96bd2cb41a`

A size or checksum mismatch stops processing. The script records the input filename, source URL, SHA-1 and SHA-256 in `frame_manifest.json`.

## Review boundary

FFmpeg extraction only produces timestamped frame files. It does not prove that a frame shows the claimed action. The manifest remains `pending_human_visual_review` until a reviewer checks each frame against the annotation. Do not mark steps `frame_verified` merely because extraction succeeded.

The source is by Pau Giner (13 January 2015), licensed CC BY-SA 4.0. Any redistributed derivatives must retain attribution and comply with the license's share-alike terms.