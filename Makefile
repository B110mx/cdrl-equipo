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
	echo "Verificando estructura de entrega..."
	test -d docs || (echo "Error: Falta carpeta docs/" && exit 1)
	test -d artifacts || (echo "Error: Falta carpeta artifacts/" && exit 1)
	test -f evidence/m02-relational-model.json || (echo "Error: Falta JSON de evidencia" && exit 1)
	echo "Verificación exitosa. Estructura de entrega completa."

run:
	docker compose up -d --wait
