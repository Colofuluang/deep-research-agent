"""单机单调度器：持久任务、有限并发、整进程停止与检查点恢复。"""
import fcntl
import multiprocessing
import os
import re
import signal
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .job_store import ACTIVE, TERMINAL, JobStore
from .job_worker import run_job, worker_entry


class JobManager:
    def __init__(self, output_root: Path, *, max_running=2, worker_target=run_job):
        if max_running < 1:
            raise ValueError("后台并发数必须大于0")
        self.root = Path(output_root).resolve()
        self.store = JobStore(self.root)
        self.max_running = max_running
        self.worker_target = worker_target
        self._processes = {}
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._closed = threading.Event()
        self._thread = None
        self._owner = None

    def start(self):
        if self._closed.is_set():
            raise RuntimeError("后台调度器已关闭")
        if self._thread is not None:
            return
        self._owner = (self.root / "manager.lock").open("a")
        try:
            fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._owner.close()
            self._owner = None
            raise RuntimeError("已有后台调度器，请使用单个API worker") from None
        for job in self.store.list(limit=100000):
            if job["status"] in ACTIVE:
                self.store.finish(job["job_id"], "interrupted", "服务已重启，请从检查点恢复研究")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._closed.is_set():
            with self._lock:
                for job_id, process in list(self._processes.items()):
                    if not process.is_alive():
                        process.join()
                        self._processes.pop(job_id)
                        job = self.store.get(job_id)
                        if job["status"] not in TERMINAL:
                            status = "stopped" if job["status"] == "stopping" else "interrupted"
                            self.store.finish(job_id, status, "执行已结束，可从检查点恢复研究")
                queued = [j for j in reversed(self.store.list(limit=100000)) if j["status"] == "queued"]
                for job in queued:
                    if len(self._processes) >= self.max_running:
                        break
                    if not self.store.claim(job["job_id"]):
                        continue
                    process = multiprocessing.get_context("spawn").Process(
                        target=worker_entry,
                        args=(self.worker_target, job["job_id"], str(self.root), os.getpid()),
                    )
                    try:
                        process.start()
                        self._processes[job["job_id"]] = process
                    except Exception:
                        self.store.finish(job["job_id"], "failed", "后台进程启动失败，可恢复重试")
            self._wake.wait(0.1)
            self._wake.clear()

    def create(self, topic, request_id=None):
        if self._owner is None or self._closed.is_set():
            raise RuntimeError("后台调度器未启动或已关闭")
        topic = topic.strip()
        if not topic:
            raise ValueError("研究主题不能为空")
        with self._lock:
            run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
            job = self.store.create(topic, run_id, request_id=request_id)
        self._wake.set()
        return job

    def resume(self, run_id):
        if self._owner is None or self._closed.is_set():
            raise RuntimeError("后台调度器未启动或已关闭")
        if not re.fullmatch(r"[0-9]{8}_[0-9]{6}_[0-9a-f]{8}", run_id):
            raise ValueError("研究编号格式错误")
        with self._lock:
            if self.store.is_deleted(run_id):
                raise FileNotFoundError("研究记录已删除")
            latest = self.store.latest(run_id)
            if latest and latest["status"] in ACTIVE | {"completed"}:
                return latest
            checkpoint = self.root / run_id / "checkpoints.sqlite"
            if not latest and not checkpoint.is_file():
                raise FileNotFoundError("研究检查点不存在")
            topic = latest["topic"] if latest else ""
            resume = False
            if checkpoint.is_file():
                from .runner import research_session
                with research_session(run_id, checkpoint.parent) as (graph, config):
                    values = graph.get_state(config).values
                    if values:
                        topic = values["topic"]
                        resume = True
            if not topic:
                raise ValueError("未找到可恢复的研究状态")
            job = self.store.create(topic, run_id, resume=resume)
        self._wake.set()
        return job

    def get(self, job_id):
        return self.store.get(job_id)

    def list(self):
        return self.store.list()

    @staticmethod
    def _signal(process, sig):
        try:
            if os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid, sig)
            else:
                os.kill(process.pid, sig)
        except ProcessLookupError:
            pass

    def _terminate(self, job_id):
        process = self._processes.get(job_id)
        if process is None:
            return
        if process.is_alive():
            self._signal(process, signal.SIGTERM)
            process.join(timeout=2)
        if process.is_alive():
            self._signal(process, signal.SIGKILL)
        process.join(timeout=2)
        if process.is_alive():
            raise RuntimeError("研究进程尚未退出，请稍后查询状态")
        self._processes.pop(job_id, None)

    def stop(self, job_id):
        with self._lock:
            job = self.store.request_stop(job_id)
            if job["status"] == "stopping":
                self._terminate(job_id)
                job = self.store.finish(job_id, "stopped", "已停止全部研究分支，可从检查点恢复")
        self._wake.set()
        return job

    def delete(self, run_id):
        if not re.fullmatch(r"[0-9]{8}_[0-9]{6}_[0-9a-f]{8}", run_id):
            raise ValueError("研究编号格式错误")
        with self._lock:
            if not self.store.is_deleted(run_id):
                for job_id in self.store.mark_deleting(run_id):
                    self._terminate(job_id)
                self.store.delete_run(run_id)
        self._wake.set()
        return {"run_id": run_id, "deleted": True}

    def close(self):
        if self._owner is None:
            return
        self._closed.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        with self._lock:
            for job_id in list(self._processes):
                self.store.request_stop(job_id)
                self._terminate(job_id)
                self.store.finish(job_id, "interrupted", "服务已关闭，可从检查点恢复研究")
            for job in self.store.list(limit=100000):
                if job["status"] == "queued":
                    self.store.finish(job["job_id"], "interrupted", "服务已关闭，请恢复研究")
        if self._owner:
            self._owner.close()
            self._owner = None
