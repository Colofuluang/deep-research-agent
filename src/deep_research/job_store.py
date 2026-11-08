"""SQLite任务和可重放事件；短事务协调API、调度器与worker。"""
import json
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

ACTIVE = {"queued", "running", "stopping"}
TERMINAL = {"completed", "stopped", "failed", "interrupted", "deleted"}


class JobStore:
    def __init__(self, output_root: Path):
        output_root.mkdir(parents=True, exist_ok=True)
        self.path = output_root / "jobs.sqlite"
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, topic TEXT NOT NULL,
                    resume INTEGER NOT NULL, status TEXT NOT NULL, request_id TEXT UNIQUE,
                    message TEXT NOT NULL, result TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON jobs(run_id)
                    WHERE status IN ('queued','running','stopping');
                CREATE TABLE IF NOT EXISTS job_events (
                    job_id TEXT NOT NULL, seq INTEGER NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(job_id, seq)
                );
                CREATE TABLE IF NOT EXISTS deleted_runs (
                    run_id TEXT PRIMARY KEY, deleted_at REAL NOT NULL
                );
            """)

    @contextmanager
    def connection(self, write=False):
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                if write:
                    conn.execute("BEGIN IMMEDIATE")
                yield conn

    @staticmethod
    def decode(row, include_result=True):
        job = dict(row)
        job["resume"] = bool(job["resume"])
        job["result"] = json.loads(job["result"]) if include_result and job["result"] else None
        return job

    @staticmethod
    def row(conn, job_id, include_deleted=False):
        sql = "SELECT * FROM jobs WHERE job_id=?"
        if not include_deleted:
            sql += " AND run_id NOT IN (SELECT run_id FROM deleted_runs)"
        row = conn.execute(sql, (job_id,)).fetchone()
        if row is None:
            raise KeyError("后台任务不存在")
        return row

    def event(self, conn, job, event, data):
        seq = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM job_events WHERE job_id=?", (job["job_id"],)).fetchone()[0]
        data = {**data, "job_id": job["job_id"], "run_id": job["run_id"]}
        conn.execute("INSERT INTO job_events VALUES (?,?,?,?)", (job["job_id"], seq, event, json.dumps(data, ensure_ascii=False)))

    def create(self, topic, run_id, *, resume=False, request_id=None):
        with self.connection(write=True) as conn:
            if conn.execute("SELECT 1 FROM deleted_runs WHERE run_id=?", (run_id,)).fetchone():
                raise FileNotFoundError("研究记录已删除")
            if request_id:
                old = conn.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
                if old:
                    if conn.execute("SELECT 1 FROM deleted_runs WHERE run_id=?", (old["run_id"],)).fetchone():
                        raise FileNotFoundError("研究记录已删除")
                    if old["topic"] != topic:
                        raise ValueError("同一请求编号不能更改研究主题")
                    return self.decode(old)
            old = conn.execute("SELECT * FROM jobs WHERE run_id=? AND status IN ('queued','running','stopping')", (run_id,)).fetchone()
            if old:
                return self.decode(old)
            now = time.time()
            job_id = uuid4().hex
            conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)", (job_id, run_id, topic, int(resume), "queued", request_id, "已加入后台队列", None, now, now))
            job = self.row(conn, job_id)
            self.event(conn, job, "job_status", {"status": "queued", "message": job["message"]})
            return self.decode(job)

    def get(self, job_id, *, include_deleted=False):
        with self.connection() as conn:
            return self.decode(self.row(conn, job_id, include_deleted=include_deleted))

    def list(self, limit=50):
        with self.connection() as conn:
            return [self.decode(r, False) for r in conn.execute(
                "SELECT job_id,run_id,topic,resume,status,request_id,message,NULL AS result,created_at,updated_at "
                "FROM jobs WHERE run_id NOT IN (SELECT run_id FROM deleted_runs) "
                "ORDER BY created_at DESC LIMIT ?", (limit,))]

    def latest(self, run_id):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE run_id=? AND run_id NOT IN "
                               "(SELECT run_id FROM deleted_runs) ORDER BY created_at DESC LIMIT 1", (run_id,)).fetchone()
            return self.decode(row) if row else None

    def deleted_runs(self):
        with self.connection() as conn:
            return [r[0] for r in conn.execute("SELECT run_id FROM deleted_runs ORDER BY deleted_at")]

    def is_deleted(self, run_id):
        with self.connection() as conn:
            return conn.execute("SELECT 1 FROM deleted_runs WHERE run_id=?", (run_id,)).fetchone() is not None

    def mark_deleting(self, run_id):
        with self.connection(write=True) as conn:
            rows = conn.execute("SELECT * FROM jobs WHERE run_id=?", (run_id,)).fetchall()
            for job in rows:
                if job["status"] in {"queued", "running"}:
                    conn.execute("UPDATE jobs SET status='stopping',message=?,updated_at=? WHERE job_id=?", ("正在停止并删除研究记录……", time.time(), job["job_id"]))
                    self.event(conn, job, "job_status", {"status": "stopping", "message": "正在停止并删除研究记录……"})
            return [r["job_id"] for r in rows]

    def delete_run(self, run_id):
        with self.connection(write=True) as conn:
            inserted = conn.execute("INSERT OR IGNORE INTO deleted_runs VALUES (?,?)", (run_id, time.time())).rowcount
            if not inserted:
                return
            for job in conn.execute("SELECT * FROM jobs WHERE run_id=?", (run_id,)).fetchall():
                conn.execute("UPDATE jobs SET status='deleted',message=?,updated_at=? WHERE job_id=?", ("研究记录已删除", time.time(), job["job_id"]))
                self.event(conn, job, "job_status", {"status": "deleted", "message": "研究记录已删除"})

    def claim(self, job_id):
        with self.connection(write=True) as conn:
            job = self.row(conn, job_id)
            if job["status"] != "queued":
                return False
            conn.execute("UPDATE jobs SET status='running',message=?,updated_at=? WHERE job_id=?", ("后台研究正在执行", time.time(), job_id))
            self.event(conn, job, "job_status", {"status": "running", "message": "后台研究正在执行"})
            return True

    def append(self, job_id, event, data):
        with self.connection(write=True) as conn:
            job = self.row(conn, job_id)
            # 停止请求先落库，之后的迟到模型结果不能再提交为完成。
            if job["status"] != "running":
                return False
            status = "completed" if event == "completed" else "failed" if event == "error" else "running"
            message = "研究已完成" if status == "completed" else data.get("message", job["message"])
            result = json.dumps(data, ensure_ascii=False) if status == "completed" else job["result"]
            conn.execute("UPDATE jobs SET status=?,message=?,result=?,updated_at=? WHERE job_id=?", (status, message, result, time.time(), job_id))
            self.event(conn, job, event, data)
            return True

    def request_stop(self, job_id):
        with self.connection(write=True) as conn:
            job = self.row(conn, job_id)
            if job["status"] not in {"queued", "running"}:
                return self.decode(job)
            status = "stopped" if job["status"] == "queued" else "stopping"
            message = "已停止，可恢复研究" if status == "stopped" else "正在停止全部研究分支……"
            conn.execute("UPDATE jobs SET status=?,message=?,updated_at=? WHERE job_id=?", (status, message, time.time(), job_id))
            self.event(conn, job, "job_status", {"status": status, "message": message})
            return self.decode(self.row(conn, job_id))

    def finish(self, job_id, status, message):
        if status not in {"stopped", "interrupted", "failed"}:
            raise ValueError("无效的任务终止状态")
        with self.connection(write=True) as conn:
            job = self.row(conn, job_id)
            if job["status"] in TERMINAL:
                return self.decode(job)
            conn.execute("UPDATE jobs SET status=?,message=?,updated_at=? WHERE job_id=?", (status, message, time.time(), job_id))
            self.event(conn, job, "job_status", {"status": status, "message": message})
            return self.decode(self.row(conn, job_id))

    def events(self, job_id, after=0, *, include_deleted=False):
        with self.connection() as conn:
            self.row(conn, job_id, include_deleted=include_deleted)
            return [{"id": r["seq"], "event": r["event"], "data": json.loads(r["data"])} for r in conn.execute(
                "SELECT * FROM job_events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 200", (job_id, after))]
