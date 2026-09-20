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
	$(VENV_PYTHON) scripts/migrate.py --compose
	$(VENV_PYTHON) scripts/configure_roles.py --compose

verify:
	$(VENV_PYTHON) scripts/verify_m03.py --compose

run:
	docker compose up -d --wait
	$(VENV_PYTHON) scripts/run_m03.py --compose
