from pathlib import Path
from .storage import save_outputs
from datetime import datetime
from uuid import uuid4 
from .runner import research_session

def print_progress(node_name: str, update: dict) -> None:
    if node_name == "plan":
        tasks = update["tasks"]
        print(f"研究计划已生成，共 {len(tasks)} 个任务", flush=True)

    elif node_name == "search":
        current_results = update["current_results"]
        print(f"搜索任务已经结束，共 {len(current_results)} 个结果", flush=True)

    elif node_name == "record":
        # 从 update 中获取 completed_research
        # 打印累计完成了多少个任务
        completed_research = update["completed_research"]
        print(f"累计完成了 {len(completed_research)} 个任务", flush=True)

    elif node_name == "report":
        print("研究报告已生成", flush=True)

    elif node_name == "fetch":
        sources = update["current_results"]

        success_count = 0
        failed_count = 0
        usable_count = 0

        for source in sources:
            if source.fetch_status == "success":
                success_count += 1

                if source.content_status == "usable":
                    usable_count += 1

            elif source.fetch_status == "failed":
                failed_count += 1

        print(
            f"网页读取完成：共 {len(sources)} 条，"
            f"读取成功 {success_count} 条，"
            f"失败 {failed_count} 条，"
            f"正文可用 {usable_count} 条",
            flush=True,
        )
    
    elif node_name == "summarize":
        print("当前任务总结完成", flush=True)

    else:
        print(f"完成节点：{node_name}", flush=True)

def main() -> None:
    mode = input("请输入运行模式：[new/resume]：").strip().lower()
    if mode not in {"new", "resume"}:
        print("运行模式只能是 new 或 resume")
        return

    if mode == "new":
        topic = input("请输入研究主题：").strip()
        if not topic:
            print("研究主题不能为空")
            return

        run_id = (
            f"{datetime.now():%Y%m%d_%H%M%S}_"
            f"{uuid4().hex[:8]}"    
        )
        print(f"本次研究编号：{run_id}")
    else:
        run_id = input("请输入研究编号：").strip()
        if not run_id:
            print("研究编号不能为空")
            return

    output_dir = Path(__file__).resolve().parents[2] / "outputs" / run_id
    db_path = output_dir / "checkpoints.sqlite"

    if mode == "resume" and not db_path.is_file():
        print("数据库文件不存在")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    initial_state = None
    
    if mode == "new":
        initial_state = {
            "topic": topic,
            "task_index": 0,
            "completed_research": [],
            "output_dir": str(output_dir),
        }

    with research_session(run_id, output_dir) as (graph, config):
        if mode == "resume":
            snapshot = graph.get_state(config)

            if not snapshot.values:
                print("数据库中没有找到该研究编号对应的执行状态")
                return
            
        for attempt in range(2):
            try:
                graph_input = initial_state if attempt == 0 else None
                for stream_type, data in graph.stream(
                    graph_input,
                    config=config,
                    stream_mode=["updates", "custom"],
                    version="v1"
                ):
                    if stream_type == "custom":
                        print(data["message"], flush=True)  
                    elif stream_type == "updates":
                        for node_name, update in data.items():
                            print_progress(node_name, update)
                result = graph.get_state(config).values
                break

            except Exception as exc:
                print(f"研究中断：{type(exc).__name__}")

                snapshot = graph.get_state(config)
                print(
                    "已完成任务数：",
                    len(snapshot.values.get("completed_research", [])),
                )
                print("待执行节点：", snapshot.next)
                print("本次输出目录：", output_dir)

            if attempt == 1:
                print("本次重试仍然失败，结束运行。")
                return

            choice = input("是否从失败处重试一次？[y/N]：").strip().lower()
            if choice != "y":
                return

        save_outputs(result, output_dir)

        print(f"已完成任务数：{len(result['completed_research'])}")
        print(f"研究记录：{output_dir / 'research.json'}")
        print(f"研究报告：{output_dir / 'report.md'}")
        print(f"评估记录：{output_dir / 'evaluation.json'}")

if __name__ == "__main__":
    main()