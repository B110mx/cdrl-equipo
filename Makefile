.PHONY: setup verify run

ifeq ($(OS),Windows_NT)
PYTHON ?= python
VENV_PYTHON = .venv\Scripts\python.exe
CREATE_VENV = if not exist "$(VENV_PYTHON)" $(PYTHON) -m venv .venv
else
PYTHON ?= python3
VENV_PYTHON = .venv/bin/python
CREATE_VENV = test -x "$(VENV_PYTHON)" || $(PYTHON) -m venv .venv
endif

setup:
	$(CREATE_VENV)
	$(VENV_PYTHON) -m pip install -r requirements.txt
	docker compose up -d --wait postgres dynamodb
	$(VENV_PYTHON) fixtures/generate_fixtures.py
	@echo "=> Inicializando idempotentemente esquemas documentales v1/v2/v3 y tabla de auditoría..."
	$(VENV_PYTHON) scripts/init_document_store.py
	$(VENV_PYTHON) scripts/migrate.py --compose
	$(VENV_PYTHON) scripts/configure_roles.py --compose

verify:
	@echo "=> Verificando evolución compatible M07..."
	python scripts/verify_m07.py

run:
	$(VENV_PYTHON) scripts/run_m07.py
