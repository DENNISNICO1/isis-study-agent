"""Sync-Zustand (Manifest) als JSON, atomar gespeichert."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1


@dataclass
class Manifest:
    path: Path
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    discussions: dict[str, dict[str, Any]] = field(default_factory=dict)
    runs: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        if not path.is_file():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            path=path,
            files=data.get("files", {}),
            discussions=data.get("discussions", {}),
            runs=data.get("runs", []),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": MANIFEST_VERSION,
            "files": dict(sorted(self.files.items())),
            "discussions": dict(sorted(self.discussions.items())),
            "runs": self.runs[-50:],
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
