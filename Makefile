.PHONY: setup verify run clean

ifeq ($(OS),Windows_NT)
PYTHON ?= python
VENV_PYTHON = .venv/Scripts/python.exe
else
PYTHON ?= python3
VENV_PYTHON = .venv/bin/python
endif

setup:
	@echo "=> [1/4] Creando entorno virtual e instalando dependencias..."
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements.txt
	@echo "=> [2/4] Levantando contenedores base..."
	docker compose up -d --wait
	@echo "=> [3/4] Generando fixtures sintéticos para los paradigmas..."
	$(VENV_PYTHON) fixtures/generate_fixtures.py
	@echo "=> [4/4] Aplicando migraciones y configurando roles..."
	$(VENV_PYTHON) scripts/migrate.py --compose
	$(VENV_PYTHON) scripts/configure_roles.py --compose

verify:
	@echo "=> Verificando integridad del entorno y conexiones M03..."
	$(VENV_PYTHON) scripts/verify_m03.py --compose

run:
	@echo "=> Asegurando servicios activos y ejecutando la suite M03..."
	docker compose up -d --wait
	$(VENV_PYTHON) scripts/run_m03.py --compose

clean:
	@echo "=> Limpiando contenedores, volúmenes y artefactos generados..."
	docker compose down -v
	rm -rf artifacts/* evidence/* fixtures/*.json fixtures/*.csv fixtures/*.bin