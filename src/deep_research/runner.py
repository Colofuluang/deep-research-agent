import logging
import fcntl
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from .graph import build_graph
from .models import ClaimToCheck, ResearchTask, SearchResult, TaskMaterials, TaskResearch
from .storage import save_outputs

logger = logging.getLogger(__name__)


@contextmanager
def research_lock(output_dir):
    with (output_dir / "run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("该研究正在执行，不能重复恢复") from None
        yield


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
            TaskMaterials,
            ClaimToCheck,
        ]
    )

    with research_lock(output_dir), closing(sqlite3.connect(str(db_path), check_same_thread=False)) as conn:
        checkpointer = SqliteSaver(conn, serde=serde)
        config = {
            "configurable": {
                "thread_id": run_id,
            },
            # 最多5个研究分支；同步进度流的等待任务也使用执行池，另预留1个槽。
            "max_concurrency": 6,
        }

        checkpoint = checkpointer.get(config)
        # 旧检查点保留原节点与边，新任务使用子图筛选流程。
        legacy = checkpoint is not None and checkpoint["channel_values"].get("workflow_version") != 2
        graph = build_graph(checkpointer=checkpointer, legacy=legacy)

        yield graph, config


def run_research(topic: str) -> dict:
    topic = topic.strip()
    if not topic:
        raise ValueError("研究主题不能为空")

    run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"

    output_dir = Path(__file__).resolve().parents[2] / "outputs" / run_id

    initial_state = {
        "workflow_version": 2,
        "topic": topic,
        "completed_research": [],
        "output_dir": str(output_dir),
        "task_results": {},
    }

    with research_session(run_id, output_dir) as (graph, config):
        result = graph.invoke(initial_state, config=config)
        save_outputs(result, output_dir)

    return {
        "run_id": run_id,
        "topic": result["topic"],
        "completed_tasks": len(result["completed_research"]),
        "report": result["final_report"],
        "report_summary": result.get("report_summary", ""),
        "evaluation_results": result.get("evaluation_results", []),
    }


def stream_research(
    topic: str = "",
    *,
    run_id: str | None = None,
    new_run: bool = False,
    output_root: Path | None = None,
):
    is_resume = run_id is not None and not new_run

    if not is_resume:
        topic = topic.strip()
        if not topic:
            raise ValueError("研究主题不能为空")

        run_id = run_id or f"{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"

    if not re.fullmatch(r"[0-9]{8}_[0-9]{6}_[0-9a-f]{8}", run_id):
        raise ValueError("研究编号格式错误")
    output_dir = (Path(output_root) if output_root is not None else Path(__file__).resolve().parents[2] / "outputs") / run_id

    # 恢复时保持 None，让 LangGraph 从检查点继续。
    initial_state = None

    if not is_resume:
        initial_state = {
            "workflow_version": 2,
            "topic": topic,
            "completed_research": [],
            "output_dir": str(output_dir),
            "task_results": {},
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
                    "tasks": [
                        {"task_number": number, "title": task.title}
                        for number, task in enumerate(
                            snapshot.values.get("tasks", []) if is_resume else [],
                            start=1,
                        )
                    ],
                    "completed_task_numbers": (
                        list(snapshot.values.get("task_results", {}))
                        if is_resume
                        else []
                    ),
                },
            }
            for namespace, stream_type, data in graph.stream(
                initial_state,
                config=config,
                stream_mode=["updates", "custom"],
                subgraphs=True,
                version="v1",
            ):
                if stream_type == "custom":
                    yield {
                        "event": "progress",
                        "data": data,
                    }

                elif stream_type == "updates":
                    # 子图进度由 custom 事件说明；
                    # 这里仅保留父图节点的完成提示。
                    if namespace:
                        continue

                    for node_name, update in data.items():
                        payload = {
                            "node": node_name,
                            "message": f"{node_name} 已完成",
                        }
                        if node_name == "plan":
                            payload["tasks"] = [
                                {"task_number": number, "title": task.title}
                                for number, task in enumerate(update["tasks"], start=1)
                            ]
                        yield {
                            "event": "progress",
                            "data": payload,
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
                "report_summary": result.get("report_summary", ""),
                "evaluation_results": result.get("evaluation_results", []),
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
