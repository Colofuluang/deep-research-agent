from fastapi import FastAPI, HTTPException, Path as ApiPath
from .schemas import ResearchRequest, ResearchResponse
from .runner import run_research
from fastapi.responses import StreamingResponse
from .events import encode_sse
from .runner import stream_research
from pathlib import Path


app = FastAPI(title="Deep Research API")

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}

@app.post("/research/preview")
def preiew_research(
    request: ResearchRequest,
) -> dict[str, str]:
    return {
        "topic": request.topic,
        "message": "研究主题已接收",
    }

@app.post("/research", response_model=ResearchResponse)
def start_research(request: ResearchRequest) -> dict:
    return run_research(request.topic)

@app.post("/research/stream")
def start_research_stream(
    request: ResearchRequest,
) -> StreamingResponse:
    def generate():
        for event in stream_research(request.topic):
            yield encode_sse(event["event"], event["data"])

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )

@app.post("/research/{run_id}/resume")
def resume_research(
    run_id: str = ApiPath(
        pattern=r"^[0-9]{8}_[0-9]{6}_[0-9a-f]{8}$",
    ),
) -> StreamingResponse:
    db_path = (
        Path(__file__).resolve().parents[2]
        / "outputs"
        / run_id
        / "checkpoints.sqlite"
    )

    if not db_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="研究检查点不存在",
        )

    def generate():
        for event in stream_research(run_id=run_id):
            yield encode_sse(event["event"], event["data"])

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )