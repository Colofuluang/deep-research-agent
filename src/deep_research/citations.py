import re
from .models import TaskResearch, SearchResult

def resolve_source(
    citation_id: str,
    records: list[TaskResearch],
) -> SearchResult:
    """根据 T任务号-S来源号，返回对应来源。"""
    match = re.fullmatch(
        r"T([1-9][0-9]*)-S([1-9][0-9]*)",
        citation_id,
    )
    if match is None:
        raise ValueError(f"引用编号格式错误：{citation_id}")

    task_number = int(match.group(1))
    source_number = int(match.group(2))

    if task_number > len(records):
        raise ValueError(f"研究任务不存在：{citation_id}")

    research = records[task_number - 1]

    if source_number > len(research.sources):
        raise ValueError(f"来源不存在：{citation_id}")

    return research.sources[source_number - 1]

def extract_citation_ids(report: str) -> set[str]:
    """提取报告中的引用编号，自动去重。"""
    return set(re.findall(r"\[(T\d+-S\d+)\]", report))

def find_invalid_citations(
    report: str,
    records: list[TaskResearch]
) -> list[str]:
    valid_ids = set()
    for task_index, research in enumerate(records, start=1):
        for source_index, source in enumerate(research.sources, start=1):
            citation_id = f"T{task_index}-S{source_index}"
            valid_ids.add(citation_id)
    used_ids = extract_citation_ids(report)
    return sorted(used_ids - valid_ids)
