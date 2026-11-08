from .models import SourceSelection, TaskResearch


def select_task_sources(
    research: TaskResearch, source_ids: list[int], task_number: int,
) -> tuple[TaskResearch, dict[str, str]]:
    """复制入选来源，保留原始记录与稳定的任务编号。"""
    selection = SourceSelection(source_ids=source_ids)
    if len(selection.source_ids) != len(set(selection.source_ids)):
        raise ValueError(f"任务 {task_number} 的筛选来源编号重复")
    selected_sources = []
    source_map = {}
    for new_number, old_number in enumerate(selection.source_ids, start=1):
        if old_number > len(research.sources):
            raise ValueError(f"任务 {task_number} 的来源 {old_number} 不存在")
        selected_sources.append(research.sources[old_number - 1].model_copy(deep=True))
        source_map[f"T{task_number}-S{new_number}"] = f"T{task_number}-S{old_number}"
    return TaskResearch(
        task=research.task.model_copy(deep=True), sources=selected_sources, summary="",
    ), source_map


def build_report_materials(
    records: list[TaskResearch],
    selected_by_task: dict[int, list[int]],
) -> tuple[list[TaskResearch], dict[str, str]]:
    """校验选择结果，创建报告材料和新旧来源编号映射。"""
    expected_tasks = set(range(1, len(records) + 1))

    if set(selected_by_task) != expected_tasks:
        raise ValueError("筛选结果必须包含每个研究任务")

    report_records = []
    source_map = {}

    for task_number, research in enumerate(records, start=1):
        selected, mapping = select_task_sources(
            research, selected_by_task[task_number], task_number,
        )
        report_records.append(selected)
        source_map.update(mapping)

    return report_records, source_map
