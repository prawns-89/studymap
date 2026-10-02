"""A problem found in an input file, reported as file:line: message."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    file: str
    line: int
    msg: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.msg}" if self.line else f"{self.file}: {self.msg}"
