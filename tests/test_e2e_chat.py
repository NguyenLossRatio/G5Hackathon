from fastapi.testclient import TestClient

from app.main import app


def test_chat_shell_exposes_minimal_web_chat_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert '<script src="/static/app.js"></script>' in html
    assert '<link rel="stylesheet" href="/static/styles.css">' in html
    assert 'id="messages"' in html
    assert 'id="question-counter"' in html
    assert 'id="sample-w2-button"' in html
    assert 'id="w2-upload"' in html
    assert 'id="filing-status-actions"' in html
    assert 'data-answer="single"' in html
    assert 'data-answer="married_filing_jointly"' in html
    assert 'data-answer="married_filing_separately"' in html
    assert 'data-answer="head_of_household"' in html
    assert 'id="digital-assets-actions"' in html
    assert 'data-answer="true"' in html
    assert 'data-answer="false"' in html
    assert 'id="message-input"' in html
    assert 'id="refund-actions"' in html
    assert 'data-answer="paper_check"' in html
    assert 'data-answer="direct_deposit"' in html
    assert 'id="download-link"' in html
    assert 'id="events"' in html


def test_sample_w2_chat_flow_completes_with_download_and_observations(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)

    started = client.post("/api/chat/start").json()
    assert started["question_count"] == 1
    assert started["actions"] == ["upload_w2", "use_sample_w2"]

    session_id = started["session_id"]
    uploaded = client.post(
        "/api/chat/upload-w2",
        data={"session_id": session_id, "use_sample": "true"},
    ).json()
    assert uploaded["question_count"] == 2
    assert "single" in uploaded["actions"]

    household = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": "single"},
    ).json()
    assert household["question_count"] == 3
    assert household["actions"] == ["answer_household"]

    digital_assets = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": "No dependents"},
    ).json()
    assert digital_assets["question_count"] == 4
    assert digital_assets["actions"] == ["yes", "no"]

    refund = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": False},
    ).json()
    assert refund["question_count"] == 5
    assert refund["actions"] == ["paper_check", "direct_deposit"]

    completed = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "answer": "paper_check"},
    ).json()
    assert completed["phase"] == "complete"
    assert completed["question_count"] == 5
    assert completed["actions"] == ["download_pdf"]
    assert completed["download_url"].startswith("/downloads/")

    pdf = client.get(completed["download_url"])
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    events = client.get(f"/api/sessions/{session_id}/events").json()["events"]
    event_types = {event["event_type"] for event in events}
    assert "state_transition" in event_types
    assert "guardrail_check" in event_types
    assert "w2_parse_started" in event_types
    assert "tax_calculation_started" in event_types
    assert "form_generation_succeeded" in event_types
