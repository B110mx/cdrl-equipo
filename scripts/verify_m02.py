"""Verifica M01 + M02 y genera reportes auditables incluso cuando hay fallos."""
import argparse
import io
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
from src.runtime import connect_database

CATEGORIES = ("normal", "empty", "limits", "declared_failure", "constraints",
              "reproducibility", "parameterization", "runtime")


class AuditedResult(unittest.TextTestResult):
    """Registra casos; no publica mensajes SQL, credenciales ni trazas de conexión."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def record(self, test, status, err=None):
        test_id = test.id()
        category = "regression_m01"
        if test_id.startswith("tests.test_verification."):
            category = "verification_safety"
        if test_id.startswith("tests.test_relational."):
            category = next((name for name in CATEGORIES if ".test_" + name + "_" in test_id), "other")
        entry = {"test": test_id, "category": category, "status": status}
        if err:
            entry["error_type"] = err[0].__name__
        self.cases.append(entry)

    def _exc_info_to_string(self, err, test):
        return "Error de verificación: " + err[0].__name__ + " (detalles sensibles omitidos)\n"

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "passed")

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "failed", err)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "failed", err)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            self.record(test, "failed", err)

    def addSkip(self, test, reason):
        # No imprimir razones de omisión que puedan contener configuración.
        super().addSkip(test, "Omisión no permitida")
        self.record(test, "skipped")

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, "failed", err)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, "failed")


def category_results(cases):
    results = {}
    for category in CATEGORIES:
        selected = [case for case in cases if case["category"] == category]
        results[category] = {
            "status": "passed" if selected and all(c["status"] == "passed" for c in selected) else "failed",
            "cases": len(selected),
        }
    return results


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    report = {
        "assignment_id": "m02-relational-model", "status": "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "docker-compose" if args.compose else "postgres-env",
        "checks": {}, "cases": [],
        "commit_sha": None, "source_dirty": True,
    }
    output = io.StringIO()
    evidence = {}
    db = None
    checks = report["checks"]
    try:
        report.update(source_revision())
        required = (
            "docs/ADR-001-relacional-model.md", "evidence/m02-relational-model.json",
            "db/migrations/001_telemetry.sql", "db/migrations/002_relational_model.sql",
            "db/seed/000_devices_seed.sql", "db/seed/001_telemetry_seed.sql",
            "artifacts/test_cases.sql", "src/relational.py", "scripts/run_m02.py",
            "tests/test_telemetry.py", "tests/test_integration.py", "tests/test_relational.py",
        )
        for relative in required:
            if not (ROOT / relative).is_file() or (ROOT / relative).stat().st_size == 0:
                raise RuntimeError("Archivo obligatorio ausente o vacío")
        evidence = json.loads((ROOT / "evidence/m02-relational-model.json").read_text(encoding="utf-8-sig"))
        if evidence.get("assignment_id") != report["assignment_id"]:
            raise ValueError("Identificador de evidencia incorrecto")
        checks["required_files"] = {"status": "passed"}
        if args.compose:
            subprocess.run(["docker", "compose", "config", "--quiet"],
                           check=True, timeout=30, capture_output=True)
            subprocess.run(["docker", "compose", "up", "-d", "--wait", "postgres"],
                           check=True, timeout=180, capture_output=True)
        db = connect_database(compose=args.compose)
        # Todas las pruebas, incluido el subprocess del CLI, usan esta configuración.
        for key, value in {"POSTGRES_HOST": db.host, "POSTGRES_PORT": db.port,
                           "POSTGRES_DB": db.dbname, "POSTGRES_USER": db.user,
                           "POSTGRES_PASSWORD": db.password}.items():
            os.environ[key] = str(value)
        db.close()
        checks["database_available"] = {"status": "passed"}
        from tests import test_relational
        from tests.test_integration import TestTelemetryIntegration
        test_relational.SCHEMAS.update(created=0, removed=0)
        TestTelemetryIntegration.evidence = {"status": "failed"}
        suite = unittest.defaultTestLoader.discover(
            str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT))
        result = unittest.TextTestRunner(
            stream=output, verbosity=2, resultclass=AuditedResult).run(suite)
        report["cases"] = result.cases
        tests_ok = (result.testsRun > 0 and result.wasSuccessful() and not result.skipped
                    and all(c["status"] == "passed" for c in result.cases))
        checks["tests"] = {
            "status": "passed" if tests_ok else "failed", "total": result.testsRun,
            "passed": sum(c["status"] == "passed" for c in result.cases),
            "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped),
        }
        checks["regression_m01"] = dict(TestTelemetryIntegration.evidence)
        categories = category_results(result.cases)
        checks["m02_coverage"] = {
            "status": "passed" if all(c["status"] == "passed" for c in categories.values()) else "failed",
            "categories": categories,
        }
        schemas = test_relational.SCHEMAS
        checks["isolated_schemas"] = {
            **schemas, "status": "passed" if schemas["created"] > 0 and
            schemas["created"] == schemas["removed"] else "failed",
        }
        report["status"] = "passed" if all(c["status"] == "passed" for c in checks.values()) else "failed"
    except Exception as exc:
        checks["execution"] = {"status": "failed", "error_type": type(exc).__name__}
        output.write("No se pudo completar la verificación: " + type(exc).__name__ + "\n")
    finally:
        if db is not None:
            db.close()
        log = output.getvalue() + "\nM02 verification: " + report["status"] + "\n"
        secret = os.getenv("POSTGRES_PASSWORD")
        if secret:
            log = log.replace(secret, "[REDACTED]")
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        save_json(artifacts / "m02-verify.json", report)
        (artifacts / "make-verify-output.txt").write_text(log, encoding="utf-8")
        declared = [case for case in report["cases"] if case["category"] == "declared_failure"]
        failure_ok = bool(declared) and all(c["status"] == "passed" for c in declared)
        (artifacts / "failure_result.txt").write_text(
            "Fallo declarado M02: medición con dispositivo inexistente.\n"
            "Resultado de la prueba: " + ("passed" if failure_ok else "failed_or_not_run") + "\n"
            "Rechazo esperado: SQLSTATE 23503, telemetry_measurements_device_fk.\n"
            "SHA base: " + str(report["commit_sha"]) + "\n"
            "Cambios locales de código: " + str(report["source_dirty"]) + "\n", encoding="utf-8")
        evidence.update(
            assignment_id=report["assignment_id"], commit_sha=report["commit_sha"],
            source_dirty=report["source_dirty"], generated_at=report["generated_at"],
            environment=report["environment"],
            results={"status": report["status"], "checks": checks,
                     "machine_readable_report": "artifacts/m02-verify.json",
                     "verification_output": "artifacts/make-verify-output.txt",
                     "declared_failure_output": "artifacts/failure_result.txt"},
        )
        save_json(ROOT / "evidence/m02-relational-model.json", evidence)
        print(log, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
