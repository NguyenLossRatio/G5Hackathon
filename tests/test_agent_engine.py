from pathlib import Path

from app.agent.state import TaxSession
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


def test_message_during_need_w2_asks_retry_question_and_increments_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))

    started = start_session()
    response = handle_message(started["session_id"], message="I am ready with the sample W-2.")

    assert response["phase"] == "need_w2"
    assert response["question_count"] == 2
    assert "sample W-2" in response["message"]

    saved = db.load_session(started["session_id"])
    assert saved.question_count == 2
    transitions = [
        event["payload"]
        for event in db.list_events(started["session_id"])
        if event["event_type"] == "state_transition"
    ]
    assert transitions[-1]["from"] == "need_w2"
    assert transitions[-1]["to"] == "need_w2"
    assert transitions[-1]["question_incremented"] is True


def test_invalid_filing_status_asks_retry_question_and_increments_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))

    started = start_session()
    upload_w2(started["session_id"], SAMPLE_W2_PATH)

    response = handle_message(started["session_id"], answer="surviving spouse")

    assert response["phase"] == "need_filing_status"
    assert response["question_count"] == 3
    assert "supported filing status" in response["message"]

    saved = db.load_session(started["session_id"])
    assert saved.question_count == 3
    transitions = [
        event["payload"]
        for event in db.list_events(started["session_id"])
        if event["event_type"] == "state_transition"
    ]
    assert transitions[-1]["from"] == "need_filing_status"
    assert transitions[-1]["to"] == "need_filing_status"
    assert transitions[-1]["question_incremented"] is True


def test_retry_question_at_budget_limit_returns_bounded_response(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    session = TaxSession(
        session_id="sess-budget",
        phase="need_filing_status",
        question_count=5,
        w2={"tax_year": 2025},
    )
    db.save_session(session)

    response = handle_message("sess-budget", answer="surviving spouse")

    assert response["phase"] == "need_filing_status"
    assert response["question_count"] == 5
    assert "question limit" in response["message"].lower()
    assert db.load_session("sess-budget").question_count == 5


def test_tax_calculation_failure_event_uses_failure_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    session = TaxSession(
        session_id="sess-tax-failure",
        phase="need_refund",
        question_count=5,
        w2={
            "tax_year": 2025,
            "is_fake": True,
            "document_count": 1,
            "box_1_wages": 40_000,
            "federal_income_tax_withheld": 3_200,
            "box_3_social_security_wages": 40_000,
            "employee_name": "Jordan Sample",
            "employee_ssn": "000-00-0000",
            "employee_address": "123 Demo Lane, Springfield, IL 62704",
        },
        answers={"filing_status": "unsupported", "digital_assets": False},
    )
    db.save_session(session)

    handle_message("sess-tax-failure", answer={"method": "paper_check"})

    failed = [
        event
        for event in db.list_events("sess-tax-failure")
        if event["event_type"] == "tax_calculation_failed"
    ][0]
    assert set(failed["payload"]) == {"input_summary", "failure_summary"}
    assert "error" in failed["payload"]["failure_summary"]


def test_form_generation_failure_event_uses_failure_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    session = TaxSession(
        session_id="sess-form-failure",
        phase="need_refund",
        question_count=5,
        w2={
            "tax_year": 2025,
            "is_fake": True,
            "document_count": 1,
            "box_1_wages": 40_000,
            "federal_income_tax_withheld": 3_200,
            "box_3_social_security_wages": 40_000,
            "employee_name": "Jordan Sample",
            "employee_ssn": "000-00-0000",
            "employee_address": "123 Demo Lane, Springfield, IL 62704",
        },
        answers={"filing_status": "single", "digital_assets": False},
    )
    db.save_session(session)

    def fail_generate_1040_pdf(**kwargs):
        raise RuntimeError("forced form failure")

    monkeypatch.setattr("app.agent.engine.generate_1040_pdf", fail_generate_1040_pdf)

    try:
        handle_message("sess-form-failure", answer={"method": "paper_check"})
    except RuntimeError:
        pass

    failed = [
        event
        for event in db.list_events("sess-form-failure")
        if event["event_type"] == "form_generation_failed"
    ][0]
    assert set(failed["payload"]) == {"input_summary", "failure_summary"}
    assert failed["payload"]["failure_summary"] == {"error": "forced form failure"}
