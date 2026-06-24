from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_chat_api_happy_path_downloads_generated_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)

    started = client.post("/api/chat/start").json()
    assert started["phase"] == "need_w2"
    assert started["question_count"] == 1

    session_id = started["session_id"]
    w2_response = client.post(
        "/api/chat/upload-w2",
        data={"session_id": session_id, "use_sample": "true"},
    ).json()
    assert w2_response["phase"] == "need_filing_status"
    assert w2_response["question_count"] == 2

    assert client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": "single"},
    ).json()["phase"] == "need_household"
    assert client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": "No dependents"},
    ).json()["phase"] == "need_digital_assets"
    assert client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": False},
    ).json()["phase"] == "need_refund"

    completed = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": {"method": "paper_check"}},
    ).json()
    assert completed["phase"] == "complete"
    assert completed["question_count"] == 5
    assert completed["download_url"].startswith("/downloads/")

    download_response = client.get(completed["download_url"])
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/pdf"
    assert download_response.content.startswith(b"%PDF")

    events = client.get(f"/api/sessions/{session_id}/events").json()
    event_types = [event["event_type"] for event in events["events"]]
    assert "w2_parse_started" in event_types
    assert "form_generation_succeeded" in event_types


def test_download_route_rejects_unknown_and_traversal_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)

    assert client.get("/downloads/not-a-real-download").status_code == 404
    assert client.get("/downloads/../pyproject.toml").status_code == 404


def test_chat_api_out_of_scope_message_records_refusal_without_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)

    started = client.post("/api/chat/start").json()
    refused = client.post(
        "/api/chat/message",
        json={
            "session_id": started["session_id"],
            "message": "Please prepare my Illinois state return too.",
        },
    ).json()

    assert refused["phase"] == "need_w2"
    assert refused["question_count"] == 1
    assert "federal 2025 Form 1040" in refused["message"]

    events = client.get(f"/api/sessions/{started['session_id']}/events").json()["events"]
    event_types = [event["event_type"] for event in events]
    assert "guardrail_violation" in event_types
    assert "tax_calculation_started" not in event_types
    assert "form_generation_started" not in event_types
