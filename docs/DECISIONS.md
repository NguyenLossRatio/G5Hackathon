# Decisions

This prototype uses a deterministic agent instead of putting an LLM in the
critical path. Each chat session moves through explicit phases: W-2 intake,
filing status, household details, digital assets, refund preference, and PDF
completion. That keeps the five-question limit enforceable and makes each next
step explainable from state rather than from model output.

Tool boundaries are intentionally narrow. The agent chooses when to call the
W-2 parser, guardrail checks, 2025 federal tax calculator, Form 1040 PDF
generator, and observation logger. Each tool owns one job and returns structured
data back to the session. The chat layer only routes requests and renders the
current response; it does not calculate tax or write PDFs directly.

Guardrails define the product boundary: one fake W-2, tax year 2025, federal
Form 1040, no state filing, no e-filing, no itemized deductions, no real tax
advice, and no real identity or bank details. Uploaded W-2s must parse as the
generated fake sample shape and pass demo ranges for wages and withholding.
This keeps the hackathon flow educational and prevents the app from implying it
can prepare or submit a real return.

Observation is a first-class feature. State transitions, guardrail checks, W-2
parse events, tax calculation events, and PDF generation events are persisted so
the UI can show a trace of what the agent did and why. The demo W-2 lives at
`assets/sample/sample-w2-2025.pdf`; the final output is a generated, downloadable
Form 1040 PDF under local runtime storage. The tax scope is deliberately simple:
W-2 wages, standard deduction, ordinary-income brackets, federal withholding,
refund, and amount owed.

Deployment is not documented as live yet. Local development runs with FastAPI
and Uvicorn at `http://127.0.0.1:8000`; a later deployment task will add the
Render configuration and any public URL placeholder.
