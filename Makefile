.PHONY: setup verify run

ifeq ($(OS),Windows_NT)
setup:
	@python -c "from pathlib import Path; [Path(p).mkdir(parents=True, exist_ok=True) for p in ('artifacts', 'evidence', 'docs', 'db/migrations', 'db/seed', 'src', 'tests')]"
	@python -c "from pathlib import Path; assert Path('.env.example').is_file(), 'missing .env.example'"
	@echo CDRL starter base preparada. Configura .env localmente cuando corresponda.
else
setup:
	@mkdir -p artifacts evidence docs db/migrations db/seed src tests
	@test -f .env.example
	@echo "CDRL starter base preparada. Configura .env localmente cuando corresponda."
endif

ifeq ($(OS),Windows_NT)
verify:
	@powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_base.ps1
else
verify:
	@bash scripts/verify_base.sh
endif

run:
	@docker compose up
