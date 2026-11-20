import json
import sqlite3
from contextlib import closing, contextmanager

from app.errors import ReviewError
from app.manifest import canonical


class RunStore:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            yield connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS wafer_runs (
                    run_id TEXT PRIMARY KEY,
                    manifest TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    pinned TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS admission_decisions (
                    run_id TEXT NOT NULL,
                    wafer TEXT NOT NULL,
                    source TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, wafer, source)
                )
            """)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_admission_run ON admission_decisions (run_id)")

    def put(self, manifest, snapshot, pinned):
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO wafer_runs VALUES (?, ?, ?, ?) ON CONFLICT(run_id) DO NOTHING",
                (manifest["run_id"], canonical(manifest), canonical(snapshot), canonical(pinned)),
            )
            created = cursor.rowcount == 1
            row = connection.execute("SELECT manifest FROM wafer_runs WHERE run_id = ?",
                                     (manifest["run_id"],)).fetchone()
        return json.loads(row[0]), created

    def get(self, run_id):
        with self.connect() as connection:
            row = connection.execute("SELECT manifest, snapshot, pinned FROM wafer_runs WHERE run_id = ?",
                                     (run_id,)).fetchone()
        if row is None:
            raise ReviewError("RUN_NOT_FOUND", "图批未找到", 404)
        return tuple(json.loads(part) for part in row)

    def list(self):
        with self.connect() as connection:
            rows = connection.execute("SELECT manifest FROM wafer_runs ORDER BY rowid DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_admission(self, run_id, wafer, source):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT decision FROM admission_decisions WHERE run_id = ? AND wafer = ? AND source = ?",
                (run_id, wafer, source)).fetchone()
        return json.loads(row[0]) if row else None

    def list_admission(self, run_id):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT decision FROM admission_decisions WHERE run_id = ? ORDER BY rowid", (run_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put_admission(self, decision):
        key = (decision["run_id"], decision["wafer"], decision["source"])
        payload = canonical(decision)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO admission_decisions (run_id, wafer, source, decision, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(run_id, wafer, source) DO NOTHING",
                (*key, payload, decision["recorded_at"], decision["recorded_at"]))
            created = connection.execute("SELECT changes()").fetchone()[0] == 1
            if not created:
                connection.execute(
                    "UPDATE admission_decisions SET decision = ?, updated_at = ?"
                    " WHERE run_id = ? AND wafer = ? AND source = ?",
                    (payload, decision["recorded_at"], *key))
        return created
