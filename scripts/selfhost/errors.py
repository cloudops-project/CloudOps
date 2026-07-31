from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SelfHostError(Exception):
    code: str
    cause: str
    correction: str
    exit_code: int = 2

    def __str__(self) -> str:
        return f"{self.code}: {self.cause}\nCorrection: {self.correction}"
