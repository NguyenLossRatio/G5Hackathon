# Tax Filing Assistant

A hackathon demo for a bounded, deterministic tax-filing assistant. It walks
through one fake 2025 W-2, asks no more than five questions, calculates a simple
federal Form 1040 outcome, and returns a downloadable demo PDF. It does not
e-file, submit, or provide real tax advice.

## Run Locally

From the repository root:

```bash
make dev
```

The app runs at `http://127.0.0.1:8000`.

## Manual Fallback

Use these commands if `make` is not available:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`.

## Render Deployment

Live URL: `TBD`

Deployment is not live yet. After creating a Render account and connecting this
repository, create a new Blueprint deployment from `render.yaml`. The service
uses:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Generated PDF directory: `/tmp/tax-assistant-generated`
- SQLite database path: `/tmp/tax-assistant.sqlite3`

Render free web services have an ephemeral filesystem. Generated PDFs and the
SQLite database stored under `/tmp` can be removed when the service restarts or
is redeployed, which is acceptable for this hackathon demo.

## Demo Flow

Use the fake W-2 at `assets/sample/sample-w2-2025.pdf`, or choose the in-app
"Use sample W-2" action.

Expected flow:

1. Start the chat at `http://127.0.0.1:8000`.
2. Upload the fake W-2 or use the sample W-2 button.
3. Choose a filing status.
4. Enter household details such as `none`.
5. Answer the digital assets question.
6. Choose paper check or fake direct deposit.
7. Download the generated demo Form 1040 PDF and review the observation trail.
