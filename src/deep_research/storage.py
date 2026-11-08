import json
from pathlib import Path

from .models import TaskMaterials, TaskResearch
from .state import ResearchState


def save_research_records(
    state: ResearchState,
    output_dir: Path,
) -> None:
    """保存已完成的研究记录，不要求已有最终报告。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    records = [record.model_dump(mode="json") for record in state["completed_research"]]

    data = {
        "topic": state["topic"],
        "completed_research": records,
    }

    if "invalid_citations" in state:
        data["invalid_citations"] = state["invalid_citations"]

    if "citation_count" in state:
        data["citation_count"] = state["citation_count"]

    # 先写临时文件，成功后再替换已有记录。
    temp_path = output_dir / "research.json.tmp"
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(output_dir / "research.json")


def save_outputs(
    state: ResearchState,
    output_dir: Path,
) -> None:
    """研究结束后，保存研究记录和最终报告。"""
    save_research_records(state, output_dir)
    if "report_research" in state:
        save_report_materials(state, output_dir)

    report_path = output_dir / "report.md"
    report_path.write_text(
        state["final_report"],
        encoding="utf-8",
    )
    if "report_summary" in state:
        (output_dir / "summary.md").write_text(state["report_summary"], encoding="utf-8")
    if "evaluation_results" in state:
        save_evaluation(state["evaluation_results"], output_dir)


def save_evaluation(
    results: list[dict],
    output_dir: Path,
) -> Path:
    """保存评估结果，返回文件路径。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "evaluation.json"
    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def save_task_record(
    task_number: int,
    record: TaskResearch,
    output_dir: Path,
    materials: TaskMaterials | None = None,
) -> Path:
    """保存一个任务的研究成果。"""
    if task_number < 1:
        raise ValueError("任务编号必须从 1 开始")

    tasks_dir = output_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    target_path = tasks_dir / f"{task_number}.json"
    temp_path = tasks_dir / f"{task_number}.json.tmp"

    data = {
        "task_number": task_number,
        "research": record.model_dump(mode="json"),
    }
    if materials is not None:
        data["report_research"] = materials.research.model_dump(mode="json")
        data["source_ids"] = materials.source_ids

    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(target_path)

    return target_path


def save_report_materials(state: ResearchState, output_dir: Path) -> None:
    """将报告实际使用的来源与编号映射一起保存，避免两份文件不一致。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "topic": state["topic"],
        "report_research": [
            record.model_dump(mode="json") for record in state["report_research"]
        ],
        "report_source_map": state["report_source_map"],
    }
    temp_path = output_dir / "report_materials.json.tmp"
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp_path.replace(output_dir / "report_materials.json")
