import os
import sys
import json
import subprocess
from datetime import datetime, UTC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    report = {
        "module": "M09",
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
        "checks": {}
    }

    # 1. Verificar archivos requeridos de M09
    required_files = [
        "docs/ADR-009-seguridad-nosql.md",
        "tests/test_m09_seguridad.py"
    ]
    
    missing = [f for f in required_files if not os.path.exists(os.path.join(ROOT, f))]
    report["checks"]["required_files"] = {
        "status": "passed" if not missing else "failed",
        "missing": missing
    }

    # 2. Ejecutar las pruebas de seguridad y auditoría
    print("=> Ejecutando pruebas de seguridad y auditoria M09...")
    test_check = subprocess.run(
        [sys.executable, "-m", "unittest", "tests/test_m09_seguridad.py"], 
        cwd=ROOT, capture_output=True, text=True
    )
    
    report["checks"]["tests"] = {
        "status": "passed" if test_check.returncode == 0 else "failed",
        "details": "Pruebas de seguridad, minimo privilegio y auditoria pasaron correctamente" if test_check.returncode == 0 else "Fallaron pruebas de M09."
    }

    # 3. Generar evidencia en artifacts/
    artifacts_dir = os.path.join(ROOT, "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)
    
    verify_file = os.path.join(artifacts_dir, "m09-verify.json")
    with open(verify_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    
    if any(c.get("status") == "failed" for c in report["checks"].values()):
        sys.exit(1)

if __name__ == "__main__":
    main()