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
	@echo "=> Verificando paginación y rendimiento M08 con regresión acumulada..."
	$(VENV_PYTHON) scripts/verify_m08.py
	@echo "=> Verificando permisos por colección, políticas IAM y auditoría..."
	$(VENV_PYTHON) scripts/verify_security.py


run:
	$(VENV_PYTHON) scripts/run_m08.py
	$(VENV_PYTHON) scripts/benchmark_m08.py
	$(VENV_PYTHON) scripts/run_m09.py
