import json
from pathlib import Path
from .state import ResearchState


def save_research_records(
    state: ResearchState,
    output_dir: Path,
) -> None:
    """保存已完成的研究记录，不要求已有最终报告。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    records = [
        record.model_dump(mode="json")
        for record in state["completed_research"]
    ]

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

    report_path = output_dir / "report.md"
    report_path.write_text(
        state["final_report"],
        encoding="utf-8",
    )
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