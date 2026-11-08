# LangGraph的共享状态
from typing import Annotated, NotRequired, TypedDict, TypeVar

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from .models import ClaimToCheck, ResearchTask, SearchResult, TaskMaterials, TaskResearch

T = TypeVar("T")


def merge_task_results(
    existing: dict[int, T],
    incoming: dict[int, T],
) -> dict[int, T]:
    merged = dict(existing)
    for task_number, record in incoming.items():
        if task_number in merged and merged[task_number] != record:
            raise ValueError(f"任务 {task_number} 出现不一致的研究成果")
        merged[task_number] = record
    return merged


class ResearchState(TypedDict):
    topic: str
    workflow_version: NotRequired[int]
    tasks: NotRequired[list[ResearchTask]]
    completed_research: NotRequired[list[TaskResearch]]
    task_results: NotRequired[
        Annotated[
            dict[int, TaskResearch],
            merge_task_results,
        ]
    ]
    final_report: NotRequired[str]
    report_summary: NotRequired[str]
    output_dir: str
    invalid_citations: NotRequired[list[str]]
    citation_count: NotRequired[int]
    claims_to_check: NotRequired[list[ClaimToCheck]]
    evaluation_results: NotRequired[list[dict]]
    report_research: NotRequired[list[TaskResearch]]
    report_source_map: NotRequired[dict[str, str]]
    task_materials: NotRequired[Annotated[dict[int, TaskMaterials], merge_task_results]]


class TaskState(TypedDict):
    topic: NotRequired[str]
    task_number: int
    task: ResearchTask
    output_dir: str
    messages: NotRequired[Annotated[list[AnyMessage], add_messages]]
    tool_rounds: NotRequired[int]

    current_results: NotRequired[list[SearchResult]]
    current_summary: NotRequired[str]
    selected_source_ids: NotRequired[list[int]]
    selected_research: NotRequired[TaskResearch]
    task_materials: NotRequired[Annotated[dict[int, TaskMaterials], merge_task_results]]

    task_results: NotRequired[
        Annotated[
            dict[int, TaskResearch],
            merge_task_results,
        ]
    ]


class TaskInput(TypedDict):
    topic: NotRequired[str]
    task_number: int
    task: ResearchTask
    output_dir: str


class TaskOutput(TypedDict):
    task_materials: Annotated[dict[int, TaskMaterials], merge_task_results]
    task_results: Annotated[
        dict[int, TaskResearch],
        merge_task_results,
    ]
