from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .nodes import (
    collect_node,
    decide_task_node,
    evaluate_node,
    execute_task_tools_node,
    extract_node,
    persist_node,
    persist_report_materials_node,
    plan_node,
    prepare_task_node,
    report_node,
    route_after_decide,
    route_after_tools,
    select_materials_node,
    task_persist_node,
    task_record_node,
    task_summarize_node,
    task_select_materials_node,
    task_summarize_selected_node,
    distill_conclusions_node,
)
from .state import ResearchState, TaskInput, TaskOutput, TaskState


def build_task_graph(*, legacy=False):
    builder = StateGraph(
        TaskState,
        input_schema=TaskInput,
        output_schema=TaskOutput,
    )
    builder.add_node("prepare", prepare_task_node)
    builder.add_node("decide", decide_task_node)
    builder.add_node("tools", execute_task_tools_node)
    builder.add_node("summarize", task_summarize_node)
    builder.add_node("record", task_record_node)
    builder.add_node("persist", task_persist_node)

    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "decide")
    builder.add_conditional_edges(
        "decide",
        route_after_decide,
        {
            "tools": "tools",
            "summarize": "summarize",
        },
    )
    builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "decide": "decide",
            "summarize": "summarize",
        },
    )
    if legacy:
        builder.add_edge("summarize", "record")
    else:
        builder.add_node("select_materials", task_select_materials_node)
        builder.add_node("summarize_selected", task_summarize_selected_node)
        builder.add_edge("summarize", "select_materials")
        builder.add_edge("select_materials", "summarize_selected")
        builder.add_edge("summarize_selected", "record")
    builder.add_edge("record", "persist")
    builder.add_edge("persist", END)

    return builder.compile()


def dispatch_tasks(state: ResearchState) -> list[Send]:
    return [
        Send(
            "research_task",
            {
                "topic": state["topic"],
                "task_number": task_number,
                "task": task,
                "output_dir": state["output_dir"],
            },
        )
        for task_number, task in enumerate(
            state["tasks"],
            start=1,
        )
    ]


def build_graph(checkpointer=None, *, legacy=False):
    builder = StateGraph(ResearchState)

    builder.add_node("plan", plan_node)

    builder.add_node(
        "research_task",
        build_task_graph(legacy=legacy),
    )

    builder.add_node("collect", collect_node)
    builder.add_node("persist", persist_node)
    if legacy:
        builder.add_node("select_materials", select_materials_node)
    builder.add_node("persist_report_materials", persist_report_materials_node)
    builder.add_node("report", report_node)
    builder.add_node("extract", extract_node)
    builder.add_node("evaluate", evaluate_node)

    builder.add_edge(START, "plan")

    builder.add_conditional_edges(
        "plan",
        dispatch_tasks,
        ["research_task"],
    )

    builder.add_edge("research_task", "collect")
    builder.add_edge("collect", "persist")
    if legacy:
        builder.add_edge("persist", "select_materials")
        builder.add_edge("select_materials", "persist_report_materials")
    else:
        builder.add_edge("persist", "persist_report_materials")
    builder.add_edge("persist_report_materials", "report")
    builder.add_edge("report", "extract")
    builder.add_edge("extract", "evaluate")
    if legacy:
        builder.add_edge("evaluate", END)
    else:
        builder.add_node("distill_conclusions", distill_conclusions_node)
        builder.add_edge("evaluate", "distill_conclusions")
        builder.add_edge("distill_conclusions", END)

    return builder.compile(checkpointer=checkpointer)
