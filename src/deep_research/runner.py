import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from .graph import build_graph
from .models import ResearchTask, SearchResult, TaskResearch, ClaimToCheck
from .storage import save_outputs
import logging
import re 

logger = logging.getLogger(__name__)

@contextmanager
def research_session(run_id: str, output_dir: Path):
    """打开研究执行环境，退出时关闭数据库连接"""
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "checkpoints.sqlite"

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ResearchTask,
            SearchResult,
            TaskResearch,
            ClaimToCheck,
        ]
    )
    
    with closing(
        sqlite3.connect(str(db_path), check_same_thread=False)
    ) as conn:
        checkpointer = SqliteSaver(conn, serde=serde)
        graph = build_graph(checkpointer=checkpointer)
        
        config = {
            "configurable": {
                "thread_id": run_id,
            }
        }
        
        yield graph, config

def run_research(topic: str) -> dict:
    topic = topic.strip()
    if not topic:
        raise ValueError("研究主题不能为空")

    run_id = (
        f"{datetime.now():%Y%m%d_%H%M%S}_"
        f"{uuid4().hex[:8]}"    
    )

    output_dir = (
        Path(__file__).resolve().parents[2]
        / "outputs"
        / run_id
    )

    initial_state = {
        "topic": topic,
        "task_index": 0,
        "completed_research": [],
        "output_dir": str(output_dir),
    }

    with research_session(run_id, output_dir) as (graph, config):
        result = graph.invoke(initial_state, config=config)
        save_outputs(result, output_dir)
    
    return {
        "run_id": run_id,
        "topic": result["topic"],
        "completed_tasks": len(result["completed_research"]),
        "report": result["final_report"],
        "evaluation_results": result.get("evaluation_results", []),
    }

def stream_research(
    topic: str = "",
    *,
    run_id: str | None = None,
):
    is_resume = run_id is not None

    if not is_resume:
        topic = topic.strip()
        if not topic:
            raise ValueError("研究主题不能为空")

        run_id = (
            f"{datetime.now():%Y%m%d_%H%M%S}_"
            f"{uuid4().hex[:8]}"
        )

    output_dir = (
        Path(__file__).resolve().parents[2]
        / "outputs"
        / run_id
    )

    # 恢复时保持 None，让 LangGraph 从检查点继续。
    initial_state = None

    if not is_resume:
        initial_state = {
            "topic": topic,
            "task_index": 0,
            "completed_research": [],
            "output_dir": str(output_dir),
        }

    try:
        if is_resume:
            if not re.fullmatch(
                r"[0-9]{8}_[0-9]{6}_[0-9a-f]{8}",
                run_id,
            ):
                raise ValueError("研究编号格式错误")

            if not (output_dir / "checkpoints.sqlite").is_file():
                raise FileNotFoundError("研究检查点不存在")

        with research_session(run_id, output_dir) as (graph, config):
            if is_resume:
                snapshot = graph.get_state(config)

                if not snapshot.values:
                    raise ValueError("未找到该研究的执行状态")

                topic = snapshot.values["topic"]

            yield {
                "event": "started",
                "data": {
                    "run_id": run_id,
                    "topic": topic,
                    "mode": "resume" if is_resume else "new",
                },
            }
            for stream_type, data in graph.stream(
                initial_state,
                config=config,
                stream_mode=["updates", "custom"],
                version="v1",
            ):
                if stream_type == "custom":
                    yield {"event": "progress", "data": data}

                elif stream_type == "updates":
                    for node_name in data:
                        yield {
                            "event": "progress",
                            "data": {
                                "node": node_name,
                                "message": f"{node_name} 已完成",
                            },
                        }

            result = graph.get_state(config).values
            save_outputs(result, output_dir)


        yield {
            "event": "completed",
            "data": {
                "run_id": run_id,
                "topic": result["topic"],
                "completed_tasks": len(result["completed_research"]),
                "report": result["final_report"],
                "evaluation_results": result.get(
                    "evaluation_results", []
                ),
            },
        }

    except Exception as exc:
        logger.exception("研究中断，运行编号：%s", run_id)

        yield {
            "event": "error",
            "data": {
                "run_id": run_id,
                "error_type": type(exc).__name__,
                "message": "研究中断，请查看服务端日志",
            },
        }