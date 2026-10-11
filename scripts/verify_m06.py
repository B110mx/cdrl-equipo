import os
import sys
import json
import subprocess
from datetime import datetime, UTC

# Definir la raíz del proyecto
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    report = {
        "module": "M06",
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
        "checks": {}
    }

    # 1. Verificar existencia de archivos requeridos del M06
    required_files = [
        "docs/ADR-006-evolucion-auditoria.md",
        "tests/test_m06_auditoria.py",
        "scripts/verify_m06.py"
    ]
    
    missing = [f for f in required_files if not os.path.exists(os.path.join(ROOT, f))]
    report["checks"]["required_files"] = {
        "status": "passed" if not missing else "failed",
        "missing": missing
    }

    # 2. Verificar ausencia de secretos (usando la herramienta existente)
    script_secretos = os.path.join(ROOT, "scripts", "check_no_secrets.py")
    if os.path.exists(script_secretos):
        secret_check = subprocess.run(
            [sys.executable, script_secretos], 
            cwd=ROOT, capture_output=True
        )
        report["checks"]["no_secrets"] = {
            "status": "passed" if secret_check.returncode == 0 else "failed"
        }
    else:
        report["checks"]["no_secrets"] = {"status": "skipped", "reason": "Script no encontrado"}

    # 3. Ejecutar las pruebas unitarias del M06
    print("=> Ejecutando pruebas unitarias de M06...")
    test_check = subprocess.run(
        [sys.executable, "-m", "unittest", "tests/test_m06_auditoria.py"], 
        cwd=ROOT, capture_output=True, text=True
    )
    
    report["checks"]["tests"] = {
        "status": "passed" if test_check.returncode == 0 else "failed",
        # Guardamos un resumen para no saturar el JSON
        "details": "Pruebas pasaron correctamente" if test_check.returncode == 0 else "Fallaron algunas pruebas. Revisa los logs."
    }

    # 4. Generar el artefacto de verificación
    artifacts_dir = os.path.join(ROOT, "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)
    
    verify_file = os.path.join(artifacts_dir, "m06-verify.json")
    with open(verify_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Imprimir el resultado en consola para GitHub Actions
    print(json.dumps(report, indent=2))
    
    # Si algo falló, salir con error para que el CI falle
    if any(c.get("status") == "failed" for c in report["checks"].values()):
        sys.exit(1)

if __name__ == "__main__":
    main()