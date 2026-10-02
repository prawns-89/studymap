"""_studymap/state.json: which stage ran on which inputs, so runs resume and re-runs redo only what changed."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from . import __version__

SCHEMA = 1


class SourceEntry(BaseModel):
    sid: str
    kind: str
    type: str
    sha256: str
    size: int
    mtime_ns: int
    extractor: str
    units: int = 0
    outputs: list[str] = []      # paths relative to _studymap/, removed when the source goes away


class StageEntry(BaseModel):
    status: Literal["running", "done", "failed"]
    started_at: str
    finished_at: str | None = None
    inputs: str = ""             # digest of everything the stage read
    summary: dict[str, Any] = {}


class Manifest(BaseModel):
    schema_version: int = SCHEMA
    tool_version: str = __version__
    stages: dict[str, StageEntry] = {}
    sources: dict[str, SourceEntry] = {}

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        if not path.exists():
            return cls()
        try:
            m = cls.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return cls()  # unreadable or from an incompatible version: start clean, outputs get rebuilt
        if m.schema_version != SCHEMA:
            return cls()
        return m

    def save(self, path: Path) -> None:
        self.tool_version = __version__
        write_atomic(path, self.model_dump_json(indent=1) + "\n")

    def begin(self, stage: str) -> bool:
        """Mark a stage running. Returns True if the previous run of it was interrupted."""
        prev = self.stages.get(stage)
        self.stages[stage] = StageEntry(status="running", started_at=now())
        return bool(prev and prev.status == "running")

    def finish(self, stage: str, inputs: str = "", ok: bool = True, **summary: Any) -> None:
        st = self.stages[stage]
        st.status = "done" if ok else "failed"
        st.finished_at = now()
        st.inputs = inputs
        st.summary = summary


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(items: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()


def write_atomic(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data.encode("utf-8") if isinstance(data, str) else data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_if_changed(path: Path, data: str) -> bool:
    """Write only when the content differs, so unchanged outputs keep their mtime and git stays quiet."""
    if path.exists() and path.read_text(encoding="utf-8") == data:
        return False
    write_atomic(path, data)
    return True
