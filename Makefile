.PHONY: setup verify run
ifeq ($(OS),Windows_NT)
PYTHON ?= python
VENV_PYTHON = .venv/Scripts/python.exe
else
PYTHON ?= python3
VENV_PYTHON = .venv/bin/python
endif

setup:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install -r requirements.txt
	docker compose up -d --wait postgres

verify:
	$(VENV_PYTHON) scripts/verify_m01.py

run:
	docker compose up -d --wait
