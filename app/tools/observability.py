from typing import Any, Dict

from app.storage import db


def record_event(session_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return db.append_event(session_id, event_type, payload)
