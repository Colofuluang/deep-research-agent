# LangGraph的共享状态
from typing import NotRequired, TypedDict
from .models import ResearchTask, SearchResult, TaskResearch, ClaimToCheck

class ResearchState(TypedDict):
    topic: str 
    tasks: NotRequired[list[ResearchTask]]
    current_results: NotRequired[list[SearchResult]]
    current_summary: NotRequired[str]
    completed_research: NotRequired[list[TaskResearch]]
    task_index: int
    final_report: NotRequired[str]
    output_dir: str
    invalid_citations: NotRequired[list[str]]
    citation_count: NotRequired[int]
    claims_to_check: NotRequired[list[ClaimToCheck]]
    evaluation_results: NotRequired[list[dict]]
