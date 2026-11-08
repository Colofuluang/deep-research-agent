import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as ApiPath
from fastapi.responses import StreamingResponse

from .events import encode_sse
from .job_store import TERMINAL
from .jobs import JobManager
from .schemas import JobRequest, ResearchRequest, ResearchResponse

JobId = Annotated[str, ApiPath(pattern=r"^[0-9a-f]{32}$")]
RunId = Annotated[str, ApiPath(pattern=r"^[0-9]{8}_[0-9]{6}_[0-9a-f]{8}$")]


def operation(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc).strip("'")) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None


def create_app(*, manager: JobManager | None = None):
    @asynccontextmanager
    async def lifespan(app):
        jobs = manager or JobManager(Path(__file__).resolve().parents[2] / "outputs")
        jobs.start()
        app.state.jobs = jobs
        try:
            yield
        finally:
            await asyncio.to_thread(jobs.close)

    app = FastAPI(title="Deep Research API", lifespan=lifespan)

    def jobs(request):
        return request.app.state.jobs

    async def event_stream(request, job_id, after):
        manager = jobs(request)
        last_heartbeat = time.monotonic()
        while not await request.is_disconnected():
            batch = manager.store.events(job_id, after, include_deleted=True)
            for event in batch:
                after = event["id"]
                yield encode_sse(event["event"], event["data"], event["id"])
                if event["event"] == "job_status" and event["data"].get("status") == "deleted":
                    return
            if not batch and manager.store.get(job_id, include_deleted=True)["status"] in TERMINAL:
                return
            if time.monotonic() - last_heartbeat >= 10:
                yield ": keep-alive\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.2)

    def subscribe(request, job_id, after=0):
        operation(jobs(request).get, job_id)
        return StreamingResponse(event_stream(request, job_id, after), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    @app.post("/research/preview")
    def preview(body: ResearchRequest):
        return {"topic": body.topic, "message": "研究主题已接收"}

    @app.post("/research/jobs", status_code=202)
    def submit(body: JobRequest, request: Request):
        return operation(jobs(request).create, body.topic, body.request_id)

    @app.get("/research/jobs")
    def list_jobs(request: Request, include_deleted: bool = False):
        manager = jobs(request)
        if include_deleted:
            return {"jobs": manager.list(), "deleted_run_ids": manager.store.deleted_runs()}
        return manager.list()

    @app.get("/research/jobs/{job_id}")
    def get_job(job_id: JobId, request: Request):
        return operation(jobs(request).get, job_id)

    @app.get("/research/jobs/{job_id}/events")
    def events(job_id: JobId, request: Request, after: int = Query(0, ge=0)):
        return subscribe(request, job_id, after)

    @app.post("/research/jobs/{job_id}/stop")
    def stop(job_id: JobId, request: Request):
        return operation(jobs(request).stop, job_id)

    @app.post("/research/{run_id}/jobs", status_code=202)
    def resume_job(run_id: RunId, request: Request):
        return operation(jobs(request).resume, run_id)

    @app.delete("/research/{run_id}")
    def delete_run(run_id: RunId, request: Request):
        return operation(jobs(request).delete, run_id)

    # 兼容旧入口，但执行同样交给后台调度器，连接只订阅事件。
    @app.post("/research/stream")
    def stream(body: ResearchRequest, request: Request):
        job = operation(jobs(request).create, body.topic)
        return subscribe(request, job["job_id"])

    @app.post("/research/{run_id}/resume")
    def resume_stream(run_id: RunId, request: Request):
        job = operation(jobs(request).resume, run_id)
        return subscribe(request, job["job_id"])

    @app.post("/research", response_model=ResearchResponse)
    def synchronous(body: ResearchRequest, request: Request):
        manager = jobs(request)
        job = operation(manager.create, body.topic)
        while job["status"] not in TERMINAL:
            time.sleep(0.2)
            job = operation(manager.get, job["job_id"])
        if job["status"] != "completed":
            raise HTTPException(409, job["message"])
        return job["result"]

    return app


app = create_app()
