"""Framework-independent result returned by OperationsService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class OperationResult:
    operation_key: str
    success: bool
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    return_code: int | None
    message: str
    stdout: str = ""
    stderr: str = ""
    error_type: str | None = None
    exception_message: str | None = None
    season_id: str | None = None
    resolved_league_id: str | None = None
    failed_stage: str | None = None
    command: str | None = None
    status: str | None = None
    scoring_period: int | None = None
    rows_before: int | None = None
    rows_after: int | None = None
    changed: bool | None = None
    warning: str | None = None
    source: str | None = None

    def display_log(self) -> str:
        lines = [
            f"Operation: {self.operation_key}",
            (
                f"Exit code: {self.return_code}"
                if self.return_code is not None
                else f"Status: {self.message}"
            ),
            "",
        ]
        if self.stdout:
            lines.append(self.stdout)
        if self.stderr:
            lines.extend(("", "--- STDERR ---", self.stderr))
        if self.exception_message:
            lines.extend(
                (
                    "",
                    f"{self.error_type or 'OperationError'}: "
                    f"{self.exception_message}",
                )
            )
        return "\n".join(lines)
