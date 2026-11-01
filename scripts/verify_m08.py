import os
import sys
import json
import subprocess
from datetime import datetime, UTC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    report = {
        "module": "M08",
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
        "checks": {}
    }

    required_files = [
        "docs/ADR-008-paginacion-rendimiento.md",
        "tests/test_m08_paginacion.py"
    ]
    
    missing = [f for f in required_files if not os.path.exists(os.path.join(ROOT, f))]
    report["checks"]["required_files"] = {
        "status": "passed" if not missing else "failed",
        "missing": missing
    }

    print("=> Ejecutando pruebas de paginacion estable M08...")
    test_check = subprocess.run(
        [sys.executable, "-m", "unittest", "tests/test_m08_paginacion.py"], 
        cwd=ROOT, capture_output=True, text=True
    )
    
    report["checks"]["tests"] = {
        "status": "passed" if test_check.returncode == 0 else "failed",
        "details": "Pruebas de paginacion y cursores pasaron correctamente" if test_check.returncode == 0 else "Fallaron pruebas de M08."
    }

    artifacts_dir = os.path.join(ROOT, "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)
    
    verify_file = os.path.join(artifacts_dir, "m08-verify.json")
    with open(verify_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    
    if any(c.get("status") == "failed" for c in report["checks"].values()):
        sys.exit(1)

if __name__ == "__main__":
    main()