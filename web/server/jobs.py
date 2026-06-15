"""A tiny in-process job registry.

This is a single-user local app, so there is no need for a real queue. Each job
runs in a thread (the pipeline blocks on whisper/praat/f5), reports progress
into a shared dict, and the frontend polls GET /api/jobs/{id}. The model loads
are the slow part, so jobs run one at a time on a single worker thread to keep
MLX from thrashing the GPU.
"""

import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"          # queued | running | done | error
    progress: float = 0.0           # 0.0 - 1.0
    message: str = ""
    result: Any = None
    error: str | None = None
    log: list[str] = field(default_factory=list)

    def public(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "status": self.status,
            "progress": round(self.progress, 3), "message": self.message,
            "result": self.result, "error": self.error, "log": self.log[-12:],
        }


class Progress:
    """Handed to a job body so it can report progress and log lines."""

    def __init__(self, job: Job, lock: Lock):
        self._job, self._lock = job, lock

    def set(self, progress: float, message: str = "") -> None:
        with self._lock:
            self._job.progress = max(0.0, min(1.0, progress))
            if message:
                self._job.message = message
                self._job.log.append(message)


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        # One worker: the pipeline is GPU-bound and parallel f5 runs thrash MLX.
        self._pool = ThreadPoolExecutor(max_workers=1)

    def submit(self, kind: str, body: Callable[[Progress], Any]) -> str:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)
        with self._lock:
            self._jobs[job.id] = job
        prog = Progress(job, self._lock)

        def run() -> None:
            with self._lock:
                job.status = "running"
            try:
                result = body(prog)
                with self._lock:
                    job.result = result
                    job.status = "done"
                    job.progress = 1.0
                    job.message = "done"
            except Exception as e:  # surface the failure, never crash the worker
                with self._lock:
                    job.status = "error"
                    job.error = f"{type(e).__name__}: {e}"
                    job.log.append("ERROR " + job.error)
                traceback.print_exc()

        self._pool.submit(run)
        return job.id

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)


REGISTRY = JobRegistry()
