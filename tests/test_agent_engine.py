from pathlib import Path

from app.agent.engine import handle_message, start_session, upload_w2
from app.storage import db


SAMPLE_W2_PATH = Path("assets/sample/sample-w2-2025.pdf")


def test_agent_happy_path_completes_in_five_questions_with_download(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))

    started = start_session()
    session_id = started["session_id"]

    assert started["phase"] == "need_w2"
    assert started["question_count"] == 1
    assert "use_sample_w2" in started["actions"]

    w2_response = upload_w2(session_id, SAMPLE_W2_PATH)
    assert w2_response["phase"] == "need_filing_status"
    assert w2_response["question_count"] == 2

    filing_response = handle_message(session_id, answer="single")
    assert filing_response["phase"] == "need_household"
    assert filing_response["question_count"] == 3

    household_response = handle_message(session_id, answer="No dependents")
    assert household_response["phase"] == "need_digital_assets"
    assert household_response["question_count"] == 4

    digital_assets_response = handle_message(session_id, answer=False)
    assert digital_assets_response["phase"] == "need_refund"
    assert digital_assets_response["question_count"] == 5

    completed = handle_message(session_id, answer={"method": "paper_check"})
    assert completed["phase"] == "complete"
    assert completed["question_count"] == 5
    assert completed["download_url"].startswith("/downloads/")
    assert completed["actions"] == ["download_pdf"]
    assert "not tax advice" in completed["message"].lower()
    assert "e-file" in completed["message"].lower()

    saved = db.load_session(session_id)
    assert saved is not None
    assert saved.phase == "complete"
    assert saved.question_count == 5
    assert saved.download_id
    assert saved.return_summary["refund"] == 528
    assert Path(saved.answers["download_path"]).exists()

    event_types = [event["event_type"] for event in db.list_events(session_id)]
    assert "guardrail_check" in event_types
    assert "state_transition" in event_types
    assert "tax_calculation_started" in event_types
    assert "tax_calculation_succeeded" in event_types
    assert "form_generation_started" in event_types
    assert "form_generation_succeeded" in event_types


def test_out_of_scope_message_refuses_without_tool_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))

    started = start_session()
    refused = handle_message(started["session_id"], message="Can you e-file this return for me?")

    assert refused["phase"] == "need_w2"
    assert refused["question_count"] == 1
    assert "can't e-file" in refused["message"].lower()
    assert "use_sample_w2" in refused["actions"]

    event_types = [event["event_type"] for event in db.list_events(started["session_id"])]
    assert "guardrail_violation" in event_types
    assert "w2_parse_started" not in event_types
    assert "tax_calculation_started" not in event_types
    assert "form_generation_started" not in event_types
