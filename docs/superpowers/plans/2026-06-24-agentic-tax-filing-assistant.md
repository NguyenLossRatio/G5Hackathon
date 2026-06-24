# Agentic Tax-Filing Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deployed web chat that takes a fake single W-2, asks no more than five friendly questions, computes a simple 2025 federal Form 1040, and returns a downloadable completed PDF.

**Architecture:** Use a deterministic agent harness rather than an LLM-centered design. The agent is a state machine that chooses the next conversational move, validates inputs, calls explicit tools, writes an observation trail, and only supports the scoped W-2/simple-return scenario.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, vanilla JavaScript, SQLite, pydantic, pypdf, reportlab, pdfplumber, pytest, Playwright, Render.

---

## Core Decisions

- **No LLM in the critical path:** The challenge allows this, and it makes guardrails real instead of prompt-only. Warm copy is generated from templates selected by state.
- **Single deployable service:** FastAPI serves the chat UI, API routes, static assets, generated PDFs, and observation data.
- **Official Form 1040 PDF as base:** Vendor the 2025 IRS Form 1040 PDF in `assets/forms/` and overlay calculated values into exact coordinates.
- **Fake W-2 only:** Provide a realistic generated sample W-2 PDF plus parser support for that known fake document. Do not accept or encourage real PII.
- **Simple tax model:** Support W-2 wages, federal withholding, standard deduction, filing status, dependents metadata for display, and refund/amount owed. Exclude itemization, self-employment, credits beyond what is explicitly implemented, state filing, and e-filing.
- **Observation first:** Every agent transition and tool call writes a structured event visible in the UI and logs.
- **Deployment target:** Render free web service using `render.yaml`.

## Five-Question Conversation

The upload/start action counts as question 1. A prompt may collect several fields, but the UI must count and display the question number so the budget is obvious.

1. **W-2 intake:** "Upload the fake W-2, or use the sample W-2 I brought along."
2. **Filing status:** "Which filing status should we use: single, married filing jointly, married filing separately, or head of household?"
3. **Household details:** "Any spouse or dependents to include for this prototype return? If not, 'none' is perfect."
4. **Required 1040 checks:** "Did this taxpayer have digital asset activity in 2025? Yes or no."
5. **Refund delivery and final confirmation:** "Use paper check, or enter fake direct deposit details, then confirm I can prepare the downloadable draft."

The final message must clearly say this is a hackathon/educational draft, not tax advice or an e-filed return.

## File Structure

- `app/main.py`: FastAPI app factory, route registration, startup checks.
- `app/routes/chat.py`: Chat API endpoints and session loading.
- `app/routes/downloads.py`: Download endpoint for generated PDFs.
- `app/agent/state.py`: Session state model, allowed phases, question budget.
- `app/agent/engine.py`: Agent transition loop and response selection.
- `app/agent/messages.py`: Friendly text templates.
- `app/tools/w2_parser.py`: Parse sample W-2 PDF/text into structured W-2 data.
- `app/tools/tax_2025.py`: 2025 tax constants and tax calculation.
- `app/tools/form1040.py`: Map return data to 1040 overlay fields and produce PDF.
- `app/tools/observability.py`: Append structured observation events.
- `app/guardrails/policy.py`: Scope checks, prohibited input checks, state transition guards.
- `app/storage/db.py`: SQLite schema and session/event persistence.
- `app/templates/index.html`: Minimal chat UI.
- `app/static/app.js`: Chat behavior, upload, download link, observation panel.
- `app/static/styles.css`: Minimal responsive styling.
- `assets/forms/f1040-2025.pdf`: Official IRS 2025 Form 1040 base PDF.
- `assets/sample/sample-w2-2025.pdf`: Fake W-2 for judge testing.
- `docs/DECISIONS.md`: Half-page architecture rationale.
- `render.yaml`: Render deployment definition.
- `Makefile`: One-command setup and local run target.
- `requirements.txt`: Python dependencies.
- `tests/`: Unit and integration tests.

## Task 1: Scaffold The App

**Files:**
- Create: `requirements.txt`
- Create: `app/main.py`
- Create: `app/templates/index.html`
- Create: `app/static/app.js`
- Create: `app/static/styles.css`
- Create: `tests/test_health.py`

- [ ] Create the Python package directories: `app/`, `app/routes/`, `app/agent/`, `app/tools/`, `app/guardrails/`, `app/storage/`, `app/templates/`, `app/static/`, `assets/forms/`, `assets/sample/`, and `tests/`.
- [ ] Add FastAPI dependencies: `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `pydantic`, `pypdf`, `reportlab`, `pdfplumber`, `pytest`, `httpx`.
- [ ] Implement `GET /health` returning `{"ok": true}`.
- [ ] Implement `GET /` serving the chat shell.
- [ ] Add a smoke test for `/health`.
- [ ] Run: `pytest tests/test_health.py -v`.
- [ ] Commit: `chore: scaffold tax assistant app`.

## Task 2: Add Session State And Observation

**Files:**
- Create: `app/agent/state.py`
- Create: `app/tools/observability.py`
- Create: `app/storage/db.py`
- Test: `tests/test_state_and_observation.py`

- [ ] Define a `TaxSession` pydantic model with `session_id`, `phase`, `question_count`, `w2`, `answers`, `return_summary`, and `download_id`.
- [ ] Define allowed phases: `start`, `need_w2`, `need_filing_status`, `need_household`, `need_digital_assets`, `need_refund`, `ready_to_prepare`, `complete`, `out_of_scope`.
- [ ] Add `QuestionBudgetExceeded` and enforce a maximum of five user-facing questions.
- [ ] Implement SQLite tables for sessions and observation events.
- [ ] Implement `record_event(session_id, event_type, payload)` and persist timestamped JSON.
- [ ] Test state transitions, question-budget enforcement, and event persistence.
- [ ] Run: `pytest tests/test_state_and_observation.py -v`.
- [ ] Commit: `feat: add session state and observation log`.

## Task 3: Build Guardrails

**Files:**
- Create: `app/guardrails/policy.py`
- Test: `tests/test_guardrails.py`

- [ ] Implement accepted scope: one fake W-2, tax year 2025, federal Form 1040, no real filing, no state returns, no itemized deductions, no real PII recommendation.
- [ ] Reject requests for e-filing, state filing, real tax advice, multiple income documents, self-employment, capital gains, and real identity data.
- [ ] Validate W-2 numeric ranges for the demo: wages between `$30,000` and `$50,000`; withholding between `$0` and `$8,000`; Social Security wages not less than box 1 wages.
- [ ] Validate filing status against `single`, `married_filing_jointly`, `married_filing_separately`, `head_of_household`.
- [ ] Validate digital asset answer as boolean.
- [ ] Validate refund routing/account values only as fake/test values.
- [ ] Test accepted and rejected scenarios.
- [ ] Run: `pytest tests/test_guardrails.py -v`.
- [ ] Commit: `feat: enforce prototype tax guardrails`.

## Task 4: Implement W-2 Sample And Parser

**Files:**
- Create: `scripts/create_sample_w2.py`
- Create: `app/tools/w2_parser.py`
- Create: `assets/sample/sample-w2-2025.pdf`
- Test: `tests/test_w2_parser.py`

- [ ] Generate a fake W-2 PDF with clearly labeled boxes: wages `$40,000`, federal income tax withheld `$3,200`, Social Security wages `$40,000`, Social Security tax `$2,480`, Medicare wages `$40,000`, Medicare tax `$580`, fake employer and fake employee data.
- [ ] Implement parser using `pdfplumber` text extraction and regexes for the generated sample.
- [ ] Return a structured `W2Data` model.
- [ ] Record an observation event when parsing starts, succeeds, or fails.
- [ ] Test parser extracts every required field from `sample-w2-2025.pdf`.
- [ ] Run: `pytest tests/test_w2_parser.py -v`.
- [ ] Commit: `feat: parse sample W-2 PDF`.

## Task 5: Implement 2025 Tax Calculation

**Files:**
- Create: `app/tools/tax_2025.py`
- Test: `tests/test_tax_2025.py`

- [ ] Store tax constants in one file with source comments pointing to IRS pages.
- [ ] Use current 2025 standard deductions under the One Big Beautiful Bill updates: single/MFS `$15,750`, MFJ `$31,500`, HOH `$23,625`.
- [ ] Use 2025 marginal brackets from IRS inflation guidance for ordinary income.
- [ ] Compute AGI from W-2 box 1 wages.
- [ ] Compute taxable income as `max(0, agi - standard_deduction)`.
- [ ] Compute tax from marginal brackets.
- [ ] Compute refund or amount owed as `federal_withholding - tax`.
- [ ] Test single `$40,000` wages with `$3,200` withheld.
- [ ] Test MFJ, MFS, and HOH produce different taxable income where applicable.
- [ ] Run: `pytest tests/test_tax_2025.py -v`.
- [ ] Commit: `feat: calculate simple 2025 federal tax`.

## Task 6: Generate Completed 1040 PDF

**Files:**
- Create: `scripts/fetch_irs_forms.py`
- Create: `app/tools/form1040.py`
- Create: `assets/forms/f1040-2025.pdf`
- Test: `tests/test_form1040.py`

- [ ] Download the official IRS 2025 Form 1040 PDF during development and commit it to `assets/forms/`.
- [ ] If the official PDF has fillable fields, map by field name; otherwise overlay text at calibrated coordinates using reportlab and pypdf.
- [ ] Populate taxpayer name, fake SSN, address, filing status checkbox, digital assets checkbox, wages, AGI, standard deduction, taxable income, tax, withholding, refund/amount owed, and direct deposit/paper check fields.
- [ ] Flatten the generated PDF so values are visible in common browsers.
- [ ] Save generated files under a local runtime directory such as `var/generated/`.
- [ ] Test a generated PDF exists, has at least one page, and extracted text contains the taxpayer name plus key dollar values.
- [ ] Run: `pytest tests/test_form1040.py -v`.
- [ ] Commit: `feat: generate downloadable 1040 PDF`.

## Task 7: Implement Agent Engine And Chat API

**Files:**
- Create: `app/agent/messages.py`
- Create: `app/agent/engine.py`
- Create: `app/routes/chat.py`
- Modify: `app/main.py`
- Test: `tests/test_agent_engine.py`
- Test: `tests/test_chat_api.py`

- [ ] Implement agent transitions from start through complete.
- [ ] Ensure every user-facing question increments the budget once.
- [ ] Ensure every tool call records an observation event with input summary, result summary, and failure details when relevant.
- [ ] Implement `/api/chat/start`, `/api/chat/message`, `/api/chat/upload-w2`, and `/api/sessions/{session_id}/events`.
- [ ] Return structured responses: message text, phase, question count, available actions, download URL when complete.
- [ ] Test the happy path completes within five questions.
- [ ] Test out-of-scope user messages get warm refusals without tool execution.
- [ ] Run: `pytest tests/test_agent_engine.py tests/test_chat_api.py -v`.
- [ ] Commit: `feat: add bounded agent chat loop`.

## Task 8: Build Minimal Web Chat

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_e2e_chat.py`

- [ ] Build a single-page chat with messages, sample-W-2 button, upload control, answer chips for filing status and booleans, text input for household/refund details, download button, and observation panel.
- [ ] Display "Question X of 5" in the interface.
- [ ] Show observation trail entries as they happen: state transition, guardrail check, parser call, tax calculation, PDF generation.
- [ ] Keep styling plain and readable; UI polish is not the scoring focus.
- [ ] Add Playwright or FastAPI TestClient-based end-to-end coverage for the sample W-2 flow.
- [ ] Run: `pytest tests/test_e2e_chat.py -v`.
- [ ] Commit: `feat: add web chat experience`.

## Task 9: Add Decisions And Local Run Docs

**Files:**
- Create: `docs/DECISIONS.md`
- Create: `README.md`
- Create: `Makefile`

- [ ] Write a half-page `docs/DECISIONS.md` explaining deterministic agent choice, tool boundaries, guardrails, observation, W-2 input, PDF output, tax calculation scope, and deployment.
- [ ] Add a `Makefile` target named `dev` that creates `.venv`, installs dependencies, and starts the app:
  - `python -m venv .venv`
  - `.venv/bin/python -m pip install -r requirements.txt`
  - `.venv/bin/uvicorn app.main:app --reload`
- [ ] Write `README.md` with one-command local run instructions:
  - `make dev`
- [ ] Include manual fallback commands for environments without `make`:
  - `python -m venv .venv`
  - `.venv/bin/python -m pip install -r requirements.txt`
  - `.venv/bin/uvicorn app.main:app --reload`
- [ ] Include the fake W-2 path and the expected demo flow.
- [ ] Commit: `docs: document decisions and local run`.

## Task 10: Deploy To Render

**Files:**
- Create: `render.yaml`
- Modify: `README.md`

- [ ] Add Render service config with build command `pip install -r requirements.txt`.
- [ ] Add start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- [ ] Ensure runtime generated PDFs write to a directory allowed on Render, such as `/tmp/tax-assistant-generated`.
- [ ] Deploy publicly.
- [ ] Add the live URL to `README.md`.
- [ ] Commit: `chore: add render deployment`.

## Task 11: Final Verification

**Files:**
- No new files unless a bug fix requires it.

- [ ] Run full tests: `pytest -v`.
- [ ] Run the app locally and complete the sample W-2 flow manually.
- [ ] Verify the UI asks no more than five questions.
- [ ] Verify the observation panel shows chat loop, tools, guardrails, and decisions.
- [ ] Download the generated 1040 and open it in a browser/PDF viewer.
- [ ] Verify Render URL completes the same flow.
- [ ] Add any final bug-fix commit with a precise message.

## Judging Checklist

- **Chat loop:** Session state persists across turns and phases.
- **Tools:** W-2 parser, tax calculator, and PDF generator are explicit callable tools.
- **Guardrails:** Scope, input validation, transition checks, and question budget are enforced in code.
- **Observation:** Event log is visible through API and UI.
- **End result:** Judge can use sample W-2, answer <=5 questions, and download a completed 2025 Form 1040.
- **Deliverables:** Source, deployed public URL, one-command local fallback, and `docs/DECISIONS.md`.
