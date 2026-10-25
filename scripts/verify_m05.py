"""Verifica M05: Almacén Documental, genera artefactos y evidencia."""
import json
import os
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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def main():
    report = {
        "assignment_id": "m05-documental",
        "status": "failed",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commands": ["make setup", "make verify", "make run"],
        "checks": {}
    }
    
    try:
        # 1. Verificar archivos requeridos
        required = [
            "src/document_store.py", 
            "tests/test_document_store.py", 
            "docs/M05-event-document-schema.json",
            "docs/ADR-004-almacen-documental.md"
        ]
        files_exist = all((ROOT / path).is_file() for path in required)
        report["checks"]["required_files"] = {"status": "passed" if files_exist else "failed"}

        # 2. Comprobar que no haya secretos
        secret_check = subprocess.run(
            [sys.executable, "scripts/check_no_secrets.py"], cwd=ROOT, capture_output=True
        )
        report["checks"]["no_secrets"] = {
            "status": "passed" if secret_check.returncode == 0 else "failed"
        }

        # 3. Inicializar la base de datos
        # 3. Inicializar la base de datos
        init_check = subprocess.run(
            [sys.executable, "scripts/init_document_store.py"], 
            cwd=ROOT, capture_output=True, text=True
        )
        
        if init_check.returncode != 0:
            print("\n[!] ERROR EN DATABASE INIT:", file=sys.stderr)
            print(init_check.stderr, file=sys.stderr)
            
        report["checks"]["database_init"] = {
            "status": "passed" if init_check.returncode == 0 else "failed"
        }

        # La entrega M05 parte de la decisión M04 corregida. Ejecutar su
        # verificador comprueba también la matriz ponderada, la trazabilidad
        # y la alternativa descartada antes de validar el CRUD documental.
        m04_check = subprocess.run(
            [sys.executable, "scripts/verify_m04.py", "--compose"],
            cwd=ROOT, capture_output=True, text=True
        )
        report["checks"]["m04_regression"] = {
            "status": "passed" if m04_check.returncode == 0 else "failed",
            "command": f"{sys.executable} scripts/verify_m04.py --compose",
            "exit_code": m04_check.returncode,
        }

        # 4. Ejecutar M05 y la regresión de M01 a M04.
        modules = [
            "tests.test_telemetry",
            "tests.test_integration",
            "tests.test_relational",
            "tests.test_roles",
            "tests.test_storage_comparison",
            "tests.test_verification",
            "tests.test_document_store",
        ]
        suite = unittest.TestSuite(
            unittest.defaultTestLoader.loadTestsFromName(module)
            for module in modules
        )
        result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
        
        report["checks"]["tests"] = {
            "status": "passed" if result.wasSuccessful() else "failed",
            "command": (
                f"{sys.executable} -m unittest " + " ".join(modules)
            ),
            "scope": "M01-M05 cumulative regression",
            "total": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
        }

        # Estado global
        report["status"] = "passed" if all(c["status"] == "passed" for c in report["checks"].values()) else "failed"

    except Exception as e:
        report["checks"]["execution"] = {"status": "failed", "error": str(e)}

    finally:
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Guardar artefactos y evidencias
        save_json(ROOT / "artifacts/m05-verify.json", report)
        
        evidence = {
            "assignment_id": report["assignment_id"],
            "status": report["status"],
            "generated_at": report["generated_at"],
            "commit_sha": report["commit_sha"],
            "source_dirty": report["source_dirty"],
            "commands": report["commands"],
            "team": [
                "Abril Miranda Baltazar Varillas",
                "Luis Bryan Rojas Rodriguez",
                "Edwin Yahir Cruz Flores",
            ],
            "results": {"status": report["status"], "checks": report["checks"]}
        }
        save_json(ROOT / "evidence/m05-documental.json", evidence)
        
        print("\n=== RESUMEN DE VERIFICACIÓN M05 ===")
        print(json.dumps(report, indent=2))
        
    return 0 if report["status"] == "passed" else 1

if __name__ == "__main__":
    sys.exit(main())
