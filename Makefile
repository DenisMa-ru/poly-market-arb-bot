PYTHON ?= python3
VENV ?= .venv

.PHONY: venv install run dashboard compile

venv:
	$(PYTHON) -m venv $(VENV)

install:
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e .[dev]

run:
	$(VENV)/bin/python scripts/paper_run.py

dashboard:
	$(VENV)/bin/streamlit run dashboard/app.py

compile:
	$(VENV)/bin/python -m compileall .

