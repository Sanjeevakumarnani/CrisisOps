from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    DashboardStats,
    Need,
    OperationalEvent,
    OperationalEventCreate,
    Resource,
    Responder,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("CRISISOPS_DB_PATH", str(BASE_DIR / "data" / "crisisops.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            urgency TEXT NOT NULL,
            status TEXT NOT NULL,
            affected_people INTEGER NOT NULL,
            sector TEXT NOT NULL,
            details TEXT NOT NULL,
            needs_json TEXT NOT NULL,
            resources_json TEXT NOT NULL,
            responders_json TEXT NOT NULL,
            transport_json TEXT NOT NULL,
            conditions_json TEXT NOT NULL,
            attempted_actions_json TEXT NOT NULL,
            outcome TEXT NOT NULL,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'operator',
            occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            input_json TEXT NOT NULL,
            output_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS live_intel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            payload TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            retained_to_hindsight INTEGER NOT NULL DEFAULT 0,
            hindsight_memory_id TEXT
        );
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        if "source_type" not in columns:
            conn.execute("ALTER TABLE events ADD COLUMN source_type TEXT NOT NULL DEFAULT 'operator'")


def create_event(data: OperationalEventCreate) -> OperationalEvent:
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO events
            (kind,title,location,lat,lon,urgency,status,affected_people,sector,details,
             needs_json,resources_json,responders_json,transport_json,conditions_json,
             attempted_actions_json,outcome,source,source_type,occurred_at,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.kind, data.title, data.location, data.lat, data.lon, data.urgency,
                data.status, data.affected_people, data.sector, data.details,
                json.dumps([x.model_dump() for x in data.needs]),
                json.dumps([x.model_dump() for x in data.resources]),
                json.dumps([x.model_dump() for x in data.responders]),
                json.dumps(data.transport_constraints),
                json.dumps(data.operational_conditions),
                json.dumps(data.attempted_actions),
                data.outcome, data.source, data.source_type, data.occurred_at.isoformat(), now.isoformat(),
            ),
        )
        event_id = int(cur.lastrowid)
    return get_event(event_id)


def row_to_event(row: sqlite3.Row) -> OperationalEvent:
    return OperationalEvent(
        id=row["id"], kind=row["kind"], title=row["title"], location=row["location"],
        lat=row["lat"], lon=row["lon"], urgency=row["urgency"], status=row["status"],
        affected_people=row["affected_people"], sector=row["sector"], details=row["details"],
        needs=[Need.model_validate(x) for x in json.loads(row["needs_json"])],
        resources=[Resource.model_validate(x) for x in json.loads(row["resources_json"])],
        responders=[Responder.model_validate(x) for x in json.loads(row["responders_json"])],
        transport_constraints=json.loads(row["transport_json"]),
        operational_conditions=json.loads(row["conditions_json"]),
        attempted_actions=json.loads(row["attempted_actions_json"]),
        outcome=row["outcome"], source=row["source"], source_type=row["source_type"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def get_event(event_id: int) -> OperationalEvent:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if row is None:
        raise KeyError(event_id)
    return row_to_event(row)


def list_events(limit: int = 200) -> list[OperationalEvent]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY occurred_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [row_to_event(row) for row in rows]


def dashboard_stats() -> DashboardStats:
    events = list_events(1000)
    open_needs = sum(
        1 for e in events for n in e.needs if n.status in {"open", "blocked", "active"}
    )
    resources = sum(
        max(0, r.available - r.committed)
        for e in events for r in e.resources
        if r.status in {"available", "ready"}
    )
    responders = sum(
        1 for e in events for r in e.responders if r.status.lower() in {"deployed", "en route", "active"}
    )
    routes = sum(
        1 for e in events
        for c in e.transport_constraints
        if any(word in c.lower() for word in ("closed", "blocked", "impassable", "cut off"))
    )
    return DashboardStats(
        events=len(events),
        affected_people=sum(e.affected_people for e in events),
        open_needs=open_needs,
        resources_available=resources,
        active_responders=responders,
        blocked_routes=routes,
    )


def store_analysis(payload: dict[str, Any], result: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analyses(input_json,output_json,created_at) VALUES(?,?,?)",
            (json.dumps(payload), json.dumps(result), datetime.now(timezone.utc).isoformat()),
        )


def latest_analysis() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return {
        "input": json.loads(row["input_json"]),
        **json.loads(row["output_json"]),
        "created_at": row["created_at"],
    }
