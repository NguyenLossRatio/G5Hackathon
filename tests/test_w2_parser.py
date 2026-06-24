from pathlib import Path

import pytest

from app.storage import db
from app.tools.w2_parser import W2Data, W2ParseError, parse_w2_pdf
from scripts.create_sample_w2 import create_sample_w2


SAMPLE_W2_PATH = Path("assets/sample/sample-w2-2025.pdf")


@pytest.fixture(scope="module", autouse=True)
def sample_w2_pdf():
    assert SAMPLE_W2_PATH.exists(), "Committed sample W-2 PDF is missing"


def test_parse_sample_w2_extracts_every_required_field(tmp_path, monkeypatch):
    db_path = tmp_path / "tax_assistant.sqlite3"
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(db_path))

    w2 = parse_w2_pdf(SAMPLE_W2_PATH, session_id="sess-w2-success")

    assert isinstance(w2, W2Data)
    assert w2.tax_year == 2025
    assert w2.is_fake is True
    assert w2.document_count == 1
    assert w2.employee_name == "Jordan Sample"
    assert w2.employee_ssn == "000-00-0000"
    assert w2.employee_address == "123 Demo Lane, Springfield, IL 62704"
    assert w2.employer_name == "Example Payroll LLC"
    assert w2.employer_ein == "00-0000000"
    assert w2.employer_address == "456 Prototype Ave, Chicago, IL 60601"
    assert w2.box_1_wages == 40_000
    assert w2.federal_income_tax_withheld == 3_200
    assert w2.box_3_social_security_wages == 40_000
    assert w2.social_security_tax_withheld == 2_480
    assert w2.medicare_wages == 40_000
    assert w2.medicare_tax_withheld == 580


def test_parse_sample_w2_records_success_observation_events(tmp_path, monkeypatch):
    db_path = tmp_path / "tax_assistant.sqlite3"
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(db_path))

    parse_w2_pdf(SAMPLE_W2_PATH, session_id="sess-w2-events")

    events = list(db.list_events("sess-w2-events", db_path=db_path))
    assert [event["event_type"] for event in events] == [
        "w2_parse_started",
        "w2_parse_succeeded",
    ]
    assert events[0]["payload"] == {
        "file_name": "sample-w2-2025.pdf",
        "source": "sample_w2",
    }
    assert events[1]["payload"]["summary"] == {
        "tax_year": 2025,
        "is_fake": True,
        "document_count": 1,
        "box_1_wages": 40_000.0,
        "federal_income_tax_withheld": 3_200.0,
    }
    assert_no_local_paths(events)
    assert "000-00-0000" not in repr(events)
    assert "Jordan Sample" not in repr(events)
    assert "123 Demo Lane" not in repr(events)


def test_parse_sample_w2_records_failure_observation_event(tmp_path, monkeypatch):
    db_path = tmp_path / "tax_assistant.sqlite3"
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(db_path))

    with pytest.raises(W2ParseError, match="W-2 PDF not found"):
        parse_w2_pdf(tmp_path / "missing-w2.pdf", session_id="sess-w2-failure")

    events = list(db.list_events("sess-w2-failure", db_path=db_path))
    assert [event["event_type"] for event in events] == [
        "w2_parse_started",
        "w2_parse_failed",
    ]
    assert events[1]["payload"]["file_name"] == "missing-w2.pdf"
    assert events[1]["payload"]["error"] == "W-2 PDF not found"
    assert_no_local_paths(events)


def test_create_sample_w2_generates_pdf_that_parses_successfully(tmp_path, monkeypatch):
    db_path = tmp_path / "tax_assistant.sqlite3"
    generated_path = tmp_path / "generated.pdf"
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(db_path))

    create_sample_w2(generated_path)
    w2 = parse_w2_pdf(generated_path, session_id="sess-w2-generated")

    assert generated_path.exists()
    assert w2.tax_year == 2025
    assert w2.employee_name == "Jordan Sample"
    assert w2.box_1_wages == 40_000
    assert w2.federal_income_tax_withheld == 3_200


def test_generated_and_committed_sample_w2s_are_semantically_equivalent(tmp_path, monkeypatch):
    db_path = tmp_path / "tax_assistant.sqlite3"
    generated_path = tmp_path / "generated.pdf"
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(db_path))

    create_sample_w2(generated_path)
    committed = parse_w2_pdf(SAMPLE_W2_PATH, session_id="sess-w2-committed")
    generated = parse_w2_pdf(generated_path, session_id="sess-w2-generated-equivalent")

    assert model_dict(generated) == model_dict(committed)


def assert_no_local_paths(events):
    serialized_events = repr(events)
    assert "file_path" not in serialized_events
    assert "/Users/alan" not in serialized_events
    assert "/Documents/vsCode/G5Hackathon" not in serialized_events
    assert str(Path.cwd()) not in serialized_events


def model_dict(w2):
    if hasattr(w2, "model_dump"):
        return w2.model_dump()
    return w2.dict()
