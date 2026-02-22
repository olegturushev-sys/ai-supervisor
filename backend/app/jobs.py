from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal, Optional


JobState = Literal["queued", "running", "done", "error"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobResult:
    markdown_path: str
    markdown_url: str
    json_path: str
    json_url: str


@dataclass
class JobRecord:
    job_id: str
    state: JobState = "queued"
    stage: str = "upload"
    progress: float = 0.0
    error: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    input_path: Optional[str] = None
    markdown_path: Optional[str] = None
    json_path: Optional[str] = None
    message: Optional[str] = None

    def public_dict(self, *, base_url: str = "") -> dict:
        result: Optional[JobResult] = None
        if self.state == "done" and self.markdown_path and self.json_path:
            markdown_url = f"{base_url}/jobs/{self.job_id}/result" if base_url else ""
            json_url = f"{base_url}/jobs/{self.job_id}/data" if base_url else ""
            result = JobResult(
                markdown_path=self.markdown_path,
                markdown_url=markdown_url,
                json_path=self.json_path,
                json_url=json_url,
            )

        payload = {
            "job_id": self.job_id,
            "state": self.state,
            "stage": self.stage,
            "progress": float(self.progress),
            "error": self.error,
            "result": asdict(result) if result else None,
            "message": self.message,
        }
        return payload


class InMemoryJobStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, JobRecord] = {}

    def create(self, job_id: str) -> JobRecord:
        with self._lock:
            rec = JobRecord(job_id=job_id)
            self._jobs[job_id] = rec
            return rec

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_input_path(self, job_id: str, input_path: Path) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.input_path = str(input_path)
            rec.updated_at = _utcnow()

    def set_markdown_path(self, job_id: str, markdown_path: Path) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.markdown_path = str(markdown_path)
            rec.updated_at = _utcnow()

    def set_json_path(self, job_id: str, json_path: Path) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.json_path = str(json_path)
            rec.updated_at = _utcnow()

    def update(
        self,
        job_id: str,
        *,
        state: Optional[JobState] = None,
        stage: Optional[str] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            if state is not None:
                rec.state = state
            if stage is not None:
                rec.stage = stage
            if progress is not None:
                rec.progress = max(0.0, min(1.0, float(progress)))
            if error is not None:
                rec.error = error
            if message is not None:
                rec.message = message
            rec.updated_at = _utcnow()

