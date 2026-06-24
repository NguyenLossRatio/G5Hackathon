.PHONY: dev

dev:
	python -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	.venv/bin/uvicorn app.main:app --reload
