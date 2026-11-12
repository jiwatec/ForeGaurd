"""Local audit and approval persistence. Approval never executes a command."""

from contextlib import contextmanager
import json
import os
import sqlite3
import stat
import time
from uuid import uuid4

from app.classifier import assess_command


class ApprovalError(ValueError):
    pass


class Store:
    def __init__(self, path, clock=time.time):
        self.path = str(path)
        self.clock = clock
        # Audit records can contain sensitive command text. Require a private
        # directory and file before handing the path to SQLite.
        parent = os.path.dirname(os.path.abspath(self.path))
        if stat.S_IMODE(os.stat(parent).st_mode) & 0o077:
            raise PermissionError("Audit directory must be private")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        info = os.lstat(self.path)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("Audit database must be a private regular file")
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, command TEXT NOT NULL,
                    cwd TEXT NOT NULL, source TEXT NOT NULL,
                    assessment TEXT NOT NULL, created REAL NOT NULL,
                    expires REAL NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, request_id TEXT NOT NULL,
                    kind TEXT NOT NULL, timestamp REAL NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES requests(id)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def submit(self, command, cwd, source, ttl=300):
        if not all(isinstance(value, str) and value.strip() for value in (command, cwd, source)):
            raise ValueError("Invalid request fields")
        if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 3600:
            raise ValueError("TTL must be between 1 and 3600 seconds")
        assessment = assess_command(command)
        now = self.clock()
        request_id = str(uuid4())
        status = "PENDING" if assessment["decision"] == "REVIEW" else assessment["decision"]
        with self.connection() as db:
            db.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (request_id, command, cwd, source, json.dumps(assessment), now, now + ttl, status))
            db.execute("INSERT INTO events(request_id, kind, timestamp) VALUES (?, ?, ?)",
                       (request_id, "ASSESSED", now))
        return request_id

    def get(self, request_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if row is None:
            raise ApprovalError("Unknown request")
        record = dict(row)
        record["assessment"] = json.loads(record["assessment"])
        # Expiry is effective even before a decision is attempted.
        if record["status"] == "PENDING" and self.clock() >= record["expires"]:
            record["status"] = "EXPIRED"
        return record

    def decide(self, request_id, decision, *, command, cwd, source):
        if decision not in {"APPROVE", "REJECT"}:
            raise ApprovalError("Invalid decision")
        expired = False
        with self.connection() as db:
            # Serialize decisions: two callers cannot both consume one approval.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
            if row is None or row["status"] != "PENDING":
                raise ApprovalError("Request is not pending review")
            if (command, cwd, source) != (row["command"], row["cwd"], row["source"]):
                raise ApprovalError("Request identity does not match")
            now = self.clock()
            expired = now >= row["expires"]
            status = "EXPIRED" if expired else ("APPROVED" if decision == "APPROVE" else "REJECTED")
            db.execute("UPDATE requests SET status = ? WHERE id = ?", (status, request_id))
            db.execute("INSERT INTO events(request_id, kind, timestamp) VALUES (?, ?, ?)",
                       (request_id, status, now))
        if expired:
            raise ApprovalError("Approval expired")
        return self.get(request_id)

    def history(self, limit=50, offset=0):
        if type(limit) is not int or type(offset) is not int or not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Invalid pagination")
        with self.connection() as db:
            rows = db.execute("SELECT id FROM requests ORDER BY created DESC, rowid DESC LIMIT ? OFFSET ?",
                              (limit, offset)).fetchall()
        return [self.get(row["id"]) for row in rows]

    def events(self, request_id):
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT kind, timestamp FROM events WHERE request_id = ? ORDER BY id", (request_id,))]
