import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.agent.state import TaxSession


def default_db_path() -> Path:
    configured_path = os.getenv("TAX_ASSISTANT_DB_PATH")
    if configured_path:
        return Path(configured_path)
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "var" / "tax_assistant.sqlite3"


def initialize_db(db_path: Optional[Path] = None) -> None:
    path = Path(db_path) if db_path is not None else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS observation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """
        )


def save_session(session: TaxSession, db_path: Optional[Path] = None) -> None:
    path = Path(db_path) if db_path is not None else default_db_path()
    initialize_db(path)
    payload = _session_to_json(session)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO sessions (session_id, data, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (session.session_id, payload, _utc_timestamp()),
        )


def load_session(session_id: str, db_path: Optional[Path] = None) -> Optional[TaxSession]:
    path = Path(db_path) if db_path is not None else default_db_path()
    initialize_db(path)
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT data FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    return _session_from_json(row[0])


def append_event(
    session_id: str,
    event_type: str,
    payload: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    path = Path(db_path) if db_path is not None else default_db_path()
    initialize_db(path)
    timestamp = _utc_timestamp()
    payload_json = json.dumps(payload, sort_keys=True)
    with sqlite3.connect(path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO observation_events (session_id, event_type, payload, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, event_type, payload_json, timestamp),
        )
        event_id = cursor.lastrowid
    return {
        "id": event_id,
        "session_id": session_id,
        "event_type": event_type,
        "payload": payload,
        "timestamp": timestamp,
    }


def list_events(
    session_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Iterable[Dict[str, Any]]:
    path = Path(db_path) if db_path is not None else default_db_path()
    initialize_db(path)
    query = """
        SELECT id, session_id, event_type, payload, timestamp
        FROM observation_events
    """
    params = ()
    if session_id is not None:
        query += " WHERE session_id = ?"
        params = (session_id,)
    query += " ORDER BY id"
    with sqlite3.connect(path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [
        {
            "id": row[0],
            "session_id": row[1],
            "event_type": row[2],
            "payload": json.loads(row[3]),
            "timestamp": row[4],
        }
        for row in rows
    ]


def _session_to_json(session: TaxSession) -> str:
    if hasattr(session, "model_dump_json"):
        return session.model_dump_json()
    return session.json()


def _session_from_json(payload: str) -> TaxSession:
    if hasattr(TaxSession, "model_validate_json"):
        return TaxSession.model_validate_json(payload)
    return TaxSession.parse_raw(payload)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
