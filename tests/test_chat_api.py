from pathlib import Path
from uuid import uuid4

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


def test_chat_api_ambiguous_refund_check_text_does_not_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)
    session_id = _api_session_at_refund_phase(client)

    response = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": "I need to check later"},
    ).json()

    assert response["phase"] == "need_refund"
    assert response["question_count"] == 5
    assert "download_url" not in response
    assert "question limit" in response["message"].lower()

    saved_events = client.get(f"/api/sessions/{session_id}/events").json()["events"]
    event_types = [event["event_type"] for event in saved_events]
    assert "question_budget_exceeded" in event_types
    assert "tax_calculation_started" not in event_types
    assert "form_generation_started" not in event_types


def test_chat_api_clear_paper_check_text_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)
    session_id = _api_session_at_refund_phase(client)

    response = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": "paper check"},
    ).json()

    assert response["phase"] == "complete"
    assert response["question_count"] == 5
    assert response["download_url"].startswith("/downloads/")


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


def test_upload_w2_invalid_session_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)
    filename = f"invalid-session-{uuid4().hex}.pdf"
    legacy_upload_path = Path("var/uploads") / filename

    try:
        response = client.post(
            "/api/chat/upload-w2",
            data={"session_id": "missing-session"},
            files={"file": (filename, SAMPLE_W2_BYTES, "application/pdf")},
        )

        assert response.status_code == 404
        assert not legacy_upload_path.exists()
    finally:
        if legacy_upload_path.exists():
            legacy_upload_path.unlink()


def test_same_upload_filename_for_different_sessions_uses_distinct_server_files(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)
    first_session = client.post("/api/chat/start").json()["session_id"]
    second_session = client.post("/api/chat/start").json()["session_id"]

    first_response = client.post(
        "/api/chat/upload-w2",
        data={"session_id": first_session},
        files={"file": ("same-name.pdf", SAMPLE_W2_BYTES, "application/pdf")},
    )
    second_response = client.post(
        "/api/chat/upload-w2",
        data={"session_id": second_session},
        files={"file": ("same-name.pdf", SAMPLE_W2_BYTES, "application/pdf")},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_event = client.get(f"/api/sessions/{first_session}/events").json()["events"][1]
    second_event = client.get(f"/api/sessions/{second_session}/events").json()["events"][1]
    first_file_name = first_event["payload"]["input_summary"]["file_name"]
    second_file_name = second_event["payload"]["input_summary"]["file_name"]
    assert first_file_name != second_file_name
    assert first_file_name != "same-name.pdf"
    assert second_file_name != "same-name.pdf"


def test_upload_w2_rejects_malformed_pdf_with_bounded_response(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app, raise_server_exceptions=False)
    session_id = client.post("/api/chat/start").json()["session_id"]

    response = client.post(
        "/api/chat/upload-w2",
        data={"session_id": session_id},
        files={"file": ("bad.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert "W-2" in response.json()["detail"]
    events = client.get(f"/api/sessions/{session_id}/events").json()["events"]
    assert "w2_parse_failed" in [event["event_type"] for event in events]


def test_upload_w2_rejects_non_pdf_extension_and_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)
    session_id = client.post("/api/chat/start").json()["session_id"]

    extension_response = client.post(
        "/api/chat/upload-w2",
        data={"session_id": session_id},
        files={"file": ("sample.txt", b"not a pdf", "text/plain")},
    )
    size_response = client.post(
        "/api/chat/upload-w2",
        data={"session_id": session_id},
        files={"file": ("huge.pdf", b"x" * (5 * 1024 * 1024 + 1), "application/pdf")},
    )

    assert extension_response.status_code == 400
    assert "PDF" in extension_response.json()["detail"]
    assert size_response.status_code == 413


SAMPLE_W2_BYTES = Path("assets/sample/sample-w2-2025.pdf").read_bytes()


def _api_session_at_refund_phase(client: TestClient) -> str:
    session_id = client.post("/api/chat/start").json()["session_id"]
    client.post(
        "/api/chat/upload-w2",
        data={"session_id": session_id, "use_sample": "true"},
    )
    client.post("/api/chat/message", json={"session_id": session_id, "answer": "single"})
    client.post("/api/chat/message", json={"session_id": session_id, "answer": "No dependents"})
    refund = client.post("/api/chat/message", json={"session_id": session_id, "answer": False}).json()
    assert refund["phase"] == "need_refund"
    assert refund["question_count"] == 5
    return session_id
