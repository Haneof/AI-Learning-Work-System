"""Atomic JSONL record store; one current record per acquired video."""

from __future__ import annotations

import json
from pathlib import Path

from aios_work_system.acquisition.models import AcquisitionRecord


class JsonlRecordStore:
    def __init__(self, path: str | Path = "artifacts/acquisition/records.jsonl") -> None:
        self.path = Path(path).expanduser().resolve()

    def list_records(self) -> list[dict[str, object]]:
        if not self.path.is_file():
            return []
        rows: list[dict[str, object]] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL record at {self.path}:{line_number}"
                ) from exc
        return rows

    def upsert(self, record: AcquisitionRecord) -> None:
        rows = self.list_records()
        payload = record.to_dict()
        replaced = False
        for index, existing in enumerate(rows):
            if existing.get("record_id") == record.record_id:
                rows[index] = payload
                replaced = True
                break
        if not replaced:
            rows.append(payload)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        content = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        )
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(self.path)
