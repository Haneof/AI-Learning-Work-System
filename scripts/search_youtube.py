"""Print structured YouTube search results without downloading."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from aios_work_system.acquisition.platforms import YouTubePlatformAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--max-results", type=int, default=20)
    args = parser.parse_args()

    videos = YouTubePlatformAdapter().search(args.query, max_results=args.max_results)
    payload = [
        {
            key: value
            for key, value in asdict(video).items()
            if key != "metadata"
        }
        for video in videos
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
