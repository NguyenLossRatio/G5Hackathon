from pathlib import Path

import pytest

from app.agent.state import (
    ALLOWED_PHASES,
    MAX_USER_QUESTIONS,
    QuestionBudgetExceeded,
    TaxSession,
)
from app.storage import db
from app.tools.observability import record_event


def test_tax_session_transitions_only_to_allowed_phases():
    session = TaxSession(session_id="sess-1", phase="start")

    session.transition_to("need_w2")

    assert session.phase == "need_w2"
    assert tuple(ALLOWED_PHASES) == (
        "start",
        "need_w2",
        "need_filing_status",
        "need_household",
        "need_digital_assets",
        "need_refund",
        "ready_to_prepare",
        "complete",
        "out_of_scope",
    )
    with pytest.raises(ValueError, match="Invalid phase"):
        session.transition_to("unsupported")


def test_user_facing_question_budget_is_enforced():
    session = TaxSession(session_id="sess-2", phase="start")

    for _ in range(MAX_USER_QUESTIONS):
        session.ask_question("need_household")

    assert session.question_count == MAX_USER_QUESTIONS
    with pytest.raises(QuestionBudgetExceeded):
        session.ask_question("need_refund")


def test_sessions_are_saved_and_loaded_as_json(tmp_path):
    db_path = tmp_path / "tax_assistant.sqlite3"
    db.initialize_db(db_path)
    session = TaxSession(
        session_id="sess-3",
        phase="ready_to_prepare",
        question_count=3,
        w2={"employer": "Acme", "wages": 12345},
        answers={"filing_status": "single"},
        return_summary={"refund": 250},
        download_id="download-1",
    )

    db.save_session(session, db_path=db_path)
    loaded = db.load_session("sess-3", db_path=db_path)

    assert loaded == session
    assert db.load_session("missing", db_path=db_path) is None


def test_record_event_persists_timestamped_json_payloads(tmp_path, monkeypatch):
    db_path = tmp_path / "tax_assistant.sqlite3"
    db.initialize_db(db_path)
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(db_path))

    event = record_event("sess-4", "phase_transition", {"from": "start", "to": "need_w2"})

    events = db.list_events("sess-4", db_path=db_path)
    assert len(events) == 1
    assert events[0]["id"] == event["id"]
    assert events[0]["timestamp"] == event["timestamp"]
    assert events[0]["event_type"] == "phase_transition"
    assert events[0]["payload"] == {"from": "start", "to": "need_w2"}
    assert Path(db.default_db_path()).name == "tax_assistant.sqlite3"
