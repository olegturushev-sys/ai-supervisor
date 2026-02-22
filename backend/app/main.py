from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .jobs import InMemoryJobStore
from .worker import run_job
from .debug_log import dlog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("backend.log"),
        logging.StreamHandler(),
    ],
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
store = InMemoryJobStore()


def _jobs_tmp_root() -> Path:
    return Path("/tmp/whisperx_gigaam_jobs")


def _output_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "output"


async def _save_upload(upload: UploadFile, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        await asyncio.to_thread(shutil.copyfileobj, upload.file, f)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs")
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, str]:
    # region agent log
    dlog(
        run_id="pre-fix",
        hypothesis_id="H5",
        location="backend/app/main.py:create_job",
        message="create_job called",
        data={
            "filename": file.filename,
            "content_type": file.content_type,
            "origin": request.headers.get("origin"),
            "host": request.headers.get("host"),
        },
    )
    # endregion
    job_id = uuid.uuid4().hex
    rec = store.create(job_id)
    store.update(job_id, stage="upload", progress=0.05)

    suffix = Path(file.filename or "").suffix
    if not suffix:
        suffix = ".bin"

    job_dir = _jobs_tmp_root() / job_id
    input_path = job_dir / f"input{suffix}"
    await _save_upload(file, input_path)
    store.set_input_path(job_id, input_path)
    store.update(job_id, stage="convert", progress=0.10)

    background_tasks.add_task(run_job, job_id, input_path, store)

    return {"job_id": rec.job_id}


@app.post("/transcribe")
async def transcribe(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict[str, str]:
    payload = await create_job(request=request, background_tasks=background_tasks, file=file)
    job_id = payload["job_id"]
    return {"task_id": job_id, "job_id": job_id}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="job not found")

    base_url = str(request.base_url).rstrip("/")
    payload = rec.public_dict(base_url=base_url)
    # region agent log
    dlog(
        run_id="pre-fix",
        hypothesis_id="H3",
        location="backend/app/main.py:get_job",
        message="get_job status",
        data={"job_id": job_id, "state": payload.get("state"), "stage": payload.get("stage")},
    )
    # endregion
    return payload


@app.get("/status/{task_id}")
async def get_status(task_id: str, request: Request) -> dict[str, Any]:
    payload = await get_job(job_id=task_id, request=request)
    payload["task_id"] = task_id
    return payload


@app.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str) -> FileResponse:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.state != "done" or not rec.markdown_path:
        raise HTTPException(status_code=404, detail="result not ready")

    md_path = Path(rec.markdown_path)
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="result missing")

    return FileResponse(
        path=str(md_path),
        media_type="text/markdown; charset=utf-8",
        filename=md_path.name,
    )


@app.get("/jobs/{job_id}/data")
async def get_job_data(job_id: str) -> FileResponse:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="job not found")
    # region agent log
    dlog(
        run_id="pre-fix",
        hypothesis_id="H3",
        location="backend/app/main.py:get_job_data",
        message="get_job_data called",
        data={"job_id": job_id, "state": rec.state, "has_json_path": bool(rec.json_path)},
    )
    # endregion
    if rec.state != "done" or not rec.json_path:
        raise HTTPException(status_code=404, detail="result not ready")

    json_path = Path(rec.json_path)
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="result missing")

    return FileResponse(
        path=str(json_path),
        media_type="application/json; charset=utf-8",
        filename=json_path.name,
    )


@app.get("/download/{filename}")
async def download_markdown(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    if not safe_name:
        raise HTTPException(status_code=404, detail="file not found")

    output_dir = _output_dir()
    output_dir_resolved = output_dir.resolve()
    path = (output_dir_resolved / safe_name).resolve()
    if output_dir_resolved not in path.parents:
        raise HTTPException(status_code=404, detail="file not found")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    return FileResponse(
        path=str(path),
        media_type="text/markdown; charset=utf-8",
        filename=path.name,
    )

