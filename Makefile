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
	docker compose up -d --wait postgres dynamodb
	$(VENV_PYTHON) fixtures/generate_fixtures.py
	$(VENV_PYTHON) scripts/init_document_store.py
	$(VENV_PYTHON) scripts/migrate.py --compose
	$(VENV_PYTHON) scripts/configure_roles.py --compose

verify:
	@echo "=> Verificando integridad del entorno y conexiones M05..."
	$(PYTHON) scripts/verify_m05.py


run:
	$(VENV_PYTHON) scripts/run_m05.py
