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

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def main():
    report = {
        "assignment_id": "m05-documental",
        "status": "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
        init_check = subprocess.run(
            [sys.executable, "scripts/init_document_store.py"], cwd=ROOT, capture_output=True
        )
        report["checks"]["database_init"] = {
            "status": "passed" if init_check.returncode == 0 else "failed"
        }

        # 4. Ejecutar pruebas
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_document_store.py")
        result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
        
        report["checks"]["tests"] = {
            "status": "passed" if result.wasSuccessful() else "failed",
            "total": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors)
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
            "generated_at": report["generated_at"],
            "results": {"status": report["status"], "checks": report["checks"]}
        }
        save_json(ROOT / "evidence/m05-documental.json", evidence)
        
        print("\n=== RESUMEN DE VERIFICACIÓN M05 ===")
        print(json.dumps(report, indent=2))
        
    return 0 if report["status"] == "passed" else 1

if __name__ == "__main__":
    sys.exit(main())