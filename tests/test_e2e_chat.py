import shutil
import subprocess
import textwrap

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
    assert '<div id="w2-actions" class="control-group" hidden>' in html
    assert '<div id="filing-status-actions" class="control-group chip-group" aria-label="Filing status" hidden>' in html
    assert 'data-answer="single"' in html
    assert 'data-answer="married_filing_jointly"' in html
    assert 'data-answer="married_filing_separately"' in html
    assert 'data-answer="head_of_household"' in html
    assert '<div id="digital-assets-actions" class="control-group chip-group" aria-label="Digital assets" hidden>' in html
    assert 'data-answer="true"' in html
    assert 'data-answer="false"' in html
    assert 'id="message-input"' in html
    assert 'aria-label="Message"' in html
    assert '<div id="refund-actions" class="control-group chip-group" aria-label="Refund method" hidden>' in html
    assert 'data-answer="paper_check"' in html
    assert 'data-answer="direct_deposit"' in html
    assert '<form id="chat-form" class="chat-form" hidden>' in html
    assert 'id="download-link"' in html
    assert 'id="events"' in html


def test_chat_client_supports_refund_text_details(tmp_path, monkeypatch):
    monkeypatch.setenv("TAX_ASSISTANT_DB_PATH", str(tmp_path / "tax_assistant.sqlite3"))
    monkeypatch.setenv("TAX_ASSISTANT_GENERATED_DIR", str(tmp_path / "generated"))
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert 'state.phase === "need_refund"' in script
    assert "Type paper check or fake direct deposit details" in script
    assert "refundTextAnswer(value)" in script
    assert 'rawAnswer === "direct_deposit"' in script


def test_chat_client_pure_functions_with_node_vm():
    if shutil.which("node") is None:
        return

    script = textwrap.dedent(
        r"""
        const assert = require("assert");
        const fs = require("fs");
        const vm = require("vm");

        function element(name) {
          return {
            name,
            hidden: false,
            disabled: false,
            files: [],
            value: "",
            href: "",
            dataset: {},
            textContent: "",
            scrollTop: 0,
            scrollHeight: 0,
            handlers: {},
            addEventListener(type, handler) {
              this.handlers[type] = handler;
            },
            append() {},
            replaceChildren() {},
          };
        }

        const elements = new Map([
          ["#messages", element("messages")],
          ["#phase-label", element("phase-label")],
          ["#question-counter", element("question-counter")],
          ["#status-message", element("status-message")],
          ["#sample-w2-button", element("sample-w2-button")],
          ["#w2-upload", element("w2-upload")],
          ["#chat-form", element("chat-form")],
          ["#message-input", element("message-input")],
          ["#download-link", element("download-link")],
          ["#events", element("events")],
          ["#w2-actions", element("w2-actions")],
          ["#filing-status-actions", element("filing-status-actions")],
          ["#digital-assets-actions", element("digital-assets-actions")],
          ["#refund-actions", element("refund-actions")],
        ]);
        const answerButtons = [
          "single",
          "paper_check",
          "direct_deposit",
        ].map((answer) => {
          const button = element(answer);
          button.dataset.answer = answer;
          button.textContent = answer;
          return button;
        });
        const controls = [...elements.values(), ...answerButtons];

        const context = {
          console,
          FormData: class {
            append() {}
          },
          fetch: async () => {
            throw new Error("fetch should not run in this test");
          },
        };
        context.document = {
          handlers: {},
          addEventListener(type, handler) {
            this.handlers[type] = handler;
          },
          querySelector(selector) {
            return elements.get(selector) || null;
          },
          querySelectorAll(selector) {
            if (selector === "[data-answer]") {
              return answerButtons;
            }
            if (selector === "button, input") {
              return controls;
            }
            return [];
          },
          createElement(tag) {
            return element(tag);
          },
        };
        context.window = context;
        context.globalThis = context;

        const source = fs.readFileSync("app/static/app.js", "utf8");
        vm.runInNewContext(source, context);

        const hooks = context.__taxAssistantTestHooks;
        assert(hooks, "expected test hooks");

        assert.strictEqual(hooks.canSendRequest(), false);
        hooks.state.sessionId = "session-1";
        assert.strictEqual(hooks.canSendRequest(), true);
        hooks.state.busy = true;
        assert.strictEqual(hooks.canSendRequest(), false);
        hooks.state.busy = false;

        assert.strictEqual(hooks.refundTextAnswer("mail a paper check"), "paper_check");
        assert.strictEqual(hooks.refundTextAnswer("check is fine"), "paper_check");
        assert.deepStrictEqual(JSON.parse(JSON.stringify(hooks.refundTextAnswer("use direct deposit"))), {
          method: "direct_deposit",
          routing_number: "000000000",
          account_number: "000000000000",
          account_type: "checking",
        });
        assert.strictEqual(hooks.refundTextAnswer("send it later"), "send it later");

        const sanitized = hooks.sanitizePayload({
          output_dir: "/Users/alan/Documents/vsCode/G5Hackathon/out",
          download_path: "/tmp/generated/completed.pdf",
          nested: {
            file_path: "C:\\Users\\alan\\secret.pdf",
            output_file: "file:///tmp/secret.pdf",
            note: "Saved at /Users/alan/private/a.pdf, /tmp/b.pdf, C:\\Temp\\c.pdf, file:///tmp/d.pdf, and ~/e.pdf",
            file_name: "completed-1040-2025.pdf",
          },
        });
        const rendered = JSON.stringify(sanitized);
        assert(!rendered.includes("/Users/alan"));
        assert(!rendered.includes("/tmp/"));
        assert(!rendered.includes("C:\\"));
        assert(!rendered.includes("file:///"));
        assert(!rendered.includes("~/"));
        assert.strictEqual(sanitized.output_dir, "[local path hidden]");
        assert.strictEqual(sanitized.download_path, "[local path hidden]");
        assert.strictEqual(sanitized.nested.file_path, "[local path hidden]");
        assert.strictEqual(sanitized.nested.output_file, "[local path hidden]");
        assert.strictEqual(sanitized.nested.file_name, "completed-1040-2025.pdf");
        assert(sanitized.nested.note.includes("[local path hidden]"));
        """
    )

    completed = subprocess.run(
        ["node", "-e", script],
        cwd="/Users/alan/Documents/vsCode/G5Hackathon/.worktrees/tax-assistant",
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


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
