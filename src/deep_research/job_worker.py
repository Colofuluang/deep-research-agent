"""每次研究一个进程；进程退出会一起结束图的全部执行线程。"""
import os
import signal
import threading
from pathlib import Path

from .job_store import JobStore


def worker_entry(target, job_id, output_root, parent_pid):
    os.setsid()

    def watch_parent():
        while os.getppid() == parent_pid:
            threading.Event().wait(0.2)
        # API意外退出时不遗留仍消耗额度的孤儿研究进程。
        os.killpg(os.getpid(), signal.SIGKILL)

    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        target(job_id, output_root)
    except Exception:
        JobStore(Path(output_root)).finish(job_id, "failed", "后台执行失败，请查看服务端日志并恢复研究")
        raise


def run_job(job_id, output_root):
    from .runner import stream_research
    root = Path(output_root)
    store = JobStore(root)
    job = store.get(job_id)
    for event in stream_research(job["topic"], run_id=job["run_id"], new_run=not job["resume"], output_root=root):
        if not store.append(job_id, event["event"], event["data"]):
            break
