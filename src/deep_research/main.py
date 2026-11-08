"""交互式研究入口，复用与 Web 相同的执行和恢复逻辑。"""

from pathlib import Path

from .runner import stream_research


def main() -> None:
    mode = input("请输入运行模式：[new/resume]：").strip().lower()
    if mode not in {"new", "resume"}:
        print("运行模式只能是 new 或 resume")
        return

    topic = ""
    run_id = None
    if mode == "new":
        topic = input("请输入研究主题：").strip()
        if not topic:
            print("研究主题不能为空")
            return
    else:
        run_id = input("请输入研究编号：").strip()
        if not run_id:
            print("研究编号不能为空")
            return

    for attempt in range(2):
        for event in stream_research(topic, run_id=run_id):
            data = event["data"]
            if event["event"] == "started":
                run_id = data["run_id"]
                print(f"本次研究编号：{run_id}", flush=True)
            elif event["event"] == "progress":
                print(data["message"], flush=True)
            elif event["event"] == "completed":
                output_dir = Path(__file__).resolve().parents[2] / "outputs" / run_id
                print(f"已完成任务数：{data['completed_tasks']}")
                print(f"研究记录：{output_dir / 'research.json'}")
                print(f"研究报告：{output_dir / 'report.md'}")
                print(f"评估记录：{output_dir / 'evaluation.json'}")
                return
            elif event["event"] == "error":
                run_id = data.get("run_id") or run_id
                print(f"研究中断：{data['error_type']}，{data['message']}")

        if attempt == 1 or not run_id:
            return
        choice = input("是否从失败处重试一次？[y/N]：").strip().lower()
        if choice != "y":
            return


if __name__ == "__main__":
    main()
