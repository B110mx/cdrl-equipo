"""Verificación acumulada y evidencia reproducible de M06."""

import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def command_check(command):
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True
    )
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def main():
    required = [
        "src/document_store.py",
        "docs/ADR-005-evolucion-documental.md",
        "docs/ADR-006-evolucion-auditoria.md",
        "docs/M07-event-document-schema-v3.json",
        "fixtures/m07-document-data-transition-v2.json",
        "fixtures/m06-document-data-v2.json",
        "fixtures/m07-document-data-v3.json",
        "scripts/run_m06.py",
        "tests/test_document_version_contract.py",
        "tests/test_m06_auditoria.py",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    report = {
        "assignment_id": "m06-evolution-audit-recovery",
        "status": "failed",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commands": [
            "make setup",
            "make verify",
            "make run",
        ],
        "checks": {
            "required_files": {
                "status": "passed" if not missing else "failed",
                "missing": missing,
            }
        },
    }

    report["checks"]["no_secrets"] = command_check(
        [sys.executable, "scripts/check_no_secrets.py"]
    )
    report["checks"]["document_store_init"] = command_check(
        [sys.executable, "scripts/init_document_store.py"]
    )
    # M05 genera su propio reporte y demuestra la regresión M01-M05 desde
    # el mismo `make verify` usado para la verificación acumulada.
    report["checks"]["m05_verification"] = command_check(
        [sys.executable, "scripts/verify_m05.py"]
    )
    # La regresión M02 no se limita a descubrir sus tests: ejecuta su
    # verificador para regenerar y validar el reporte y la evidencia propios.
    report["checks"]["m02_verification"] = command_check(
        [sys.executable, "scripts/verify_m02.py", "--compose"]
    )

    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT)
    )
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    report["checks"]["cumulative_tests"] = {
        "status": "passed" if result.wasSuccessful() else "failed",
        "command": f"{sys.executable} -m unittest discover -s tests -p test_*.py",
        "total": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }
    report["status"] = (
        "passed"
        if all(check["status"] == "passed" for check in report["checks"].values())
        else "failed"
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()

    evidence = {
        "assignment_id": report["assignment_id"],
        "status": report["status"],
        "generated_at": report["generated_at"],
        "commit_sha": report["commit_sha"],
        "source_dirty": report["source_dirty"],
        "team": [
            "Abril Miranda Baltazar Varillas",
            "Luis Bryan Rojas Rodriguez",
            "Edwin Yahir Cruz Flores",
        ],
        "strategy": "versioned-coexistence",
        "results": report["checks"],
    }
    save_json(ROOT / "artifacts/m06-verify.json", report)
    save_json(ROOT / "evidence/m06-evolution-audit-recovery.json", evidence)
    print("\n=== RESUMEN DE VERIFICACIÓN M06 ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
