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
	mkdir -p artifacts
	$(VENV_PYTHON) -m unittest tests/test_roles.py -v > artifacts/test_roles_results.txt 2>&1
	echo "Verificando estructura de entrega..."
	test -d docs || (echo "Error: Falta carpeta docs/" && exit 1)
	test -d artifacts || (echo "Error: Falta carpeta artifacts/" && exit 1)
	test -f artifacts/test_roles_results.txt || (echo "Error: Falta evidencia de pruebas de roles/" && exit 1)
	echo "Verificación exitosa. Estructura de entrega completa."

run:
	docker compose up -d --wait
	$(VENV_PYTHON) scripts/run_m03.py --compose
