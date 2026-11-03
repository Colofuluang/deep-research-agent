from langgraph.graph import END, START, StateGraph
from .nodes import plan_node, search_node, summarize_node, record_node, fetch_node, \
    advance_node, route_after_advance, report_node, persist_node, extract_node, evaluate_node
from .state import ResearchState
from pathlib import Path
from .storage import save_outputs

def build_graph(checkpointer = None):
    builder = StateGraph(ResearchState)

    builder.add_node("plan", plan_node)
    builder.add_node("search", search_node)
    builder.add_node("summarize", summarize_node)
    builder.add_node("record", record_node)
    builder.add_node("fetch", fetch_node)   
    builder.add_node("advance", advance_node)
    builder.add_node("persist", persist_node)
    builder.add_node("report", report_node)
    builder.add_node("extract", extract_node)
    builder.add_node("evaluate", evaluate_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "search")
    builder.add_edge("search", "fetch")
    builder.add_edge("fetch", "summarize")
    builder.add_edge("summarize", "record")
    builder.add_edge("record", "persist")
    builder.add_edge("persist", "advance")
    builder.add_conditional_edges(
        "advance", 
        route_after_advance,
        {
            "search": "search",
            "done": "report",
        },
    )  
    builder.add_edge("report", "extract")
    builder.add_edge("extract", "evaluate")
    builder.add_edge("evaluate", END)

    return builder.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    graph = build_graph()
    
    output_dir = Path(__file__).resolve().parents[2] / "outputs"

    result = graph.invoke({
        "topic": "如何为个人 Markdown 笔记构建支持来源引用的问答 Agent？",
        "task_index": 0,
        "completed_research": [],
        "output_dir": str(output_dir),
    })
    save_outputs(result, output_dir)

    print("研究成果已保存到：", output_dir)

    print("研究主题：", result["topic"])

    for index, task in enumerate(result["tasks"], start=1):
        print(f"\n任务 {index}：{task.title}")
        print(f"研究目的：{task.intent}")
        print(f"搜索查询：{task.query}")

    for index, research in enumerate(result["completed_research"], start=1):
        print(f"\n--- 任务 {index} 的研究结果：{research.task.title} ---")

        print("搜索资料：")
        if not research.sources:
            print("没有可用的搜索资料")

        for source_index, source in enumerate(research.sources, start=1):
            print(f"[{source_index}] {source.title}")
            print("链接：", source.url)
            print("摘要：", source.snippet)

        print("\n初步总结：")
        print(research.summary)

    print("已保存的研究记录数：", len(result["completed_research"]))

    print("\n--- 最终研究报告 ---")
    print(result["final_report"])
