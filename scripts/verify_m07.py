"""Verificación reproducible M07 con regresión acumulada y evidencia auditable."""

import io
import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision


EXPECTED_TEAM = (
    "Abril Miranda Baltazar Varillas",
    "Luis Bryan Rojas Rodriguez",
    "Edwin Yahir Cruz Flores",
)
M07_CATEGORIES = {
    "normal": 1,
    "limits": 2,
    "declared_failure": 1,
    "rollback": 1,
}


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def command_check(command, timeout=120):
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "command": " ".join(command),
        "exit_code": completed.returncode,
    }


class AuditedM07Result(unittest.TextTestResult):
    """Registra resultados sin copiar excepciones ni configuración sensible."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    @staticmethod
    def category(test_id):
        if not test_id.startswith("tests.test_document_migration."):
            return "regression"
        method = test_id.rsplit(".", 1)[-1]
        if method.startswith("test_normal_"):
            return "normal"
        if method.startswith("test_limit_"):
            return "limits"
        if method.startswith("test_declared_failure_"):
            return "declared_failure"
        if method.startswith("test_rollback_"):
            return "rollback"
        return "m07_other"

    def record(self, test, status, err=None):
        test_id = test.id()
        entry = {
            "test": test_id,
            "category": self.category(test_id),
            "status": status,
        }
        if err:
            entry["error_type"] = err[0].__name__
        self.cases.append(entry)

    def _exc_info_to_string(self, err, test):
        return (
            "Error de verificación: "
            + err[0].__name__
            + " (detalles sensibles omitidos)\n"
        )

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "passed")

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "failed", err)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "failed", err)

    def addSkip(self, test, reason):
        super().addSkip(test, "Omisión no permitida")
        self.record(test, "skipped")

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, "failed", err)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, "failed")


def coverage_result(cases):
    result = {}
    for category, minimum in M07_CATEGORIES.items():
        selected = [case for case in cases if case["category"] == category]
        result[category] = {
            "status": (
                "passed"
                if len(selected) >= minimum
                and all(case["status"] == "passed" for case in selected)
                else "failed"
            ),
            "cases": len(selected),
            "minimum": minimum,
        }
    return result


def main():
    required = (
        "src/document_store.py",
        "src/document_migration.py",
        "scripts/init_document_store.py",
        "scripts/run_m07.py",
        "scripts/verify_m07.py",
        "tests/test_document_version_contract.py",
        "tests/test_document_migration.py",
        "docs/ADR-005-evolucion-documental.md",
        "docs/ADR-007-evolucion-compatible.md",
        "docs/M07-event-document-schema-v3.json",
        "fixtures/document_data.json",
        "fixtures/m07-document-data-transition-v2.json",
        "fixtures/m07-document-data-v3.json",
    )
    missing = [path for path in required if not (ROOT / path).is_file()]
    report = {
        "assignment_id": "m07-compatible-document-evolution",
        "status": "failed",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commands": ["make setup", "make verify", "make run"],
        "checks": {
            "required_files": {
                "status": "passed" if not missing else "failed",
                "missing": missing,
            }
        },
        "cases": [],
    }
    checks = report["checks"]
    test_output = io.StringIO()

    try:
        checks["no_secrets"] = command_check(
            [sys.executable, "scripts/check_no_secrets.py"]
        )
        checks["document_store_init"] = command_check(
            [sys.executable, "scripts/init_document_store.py"]
        )
        checks["m07_run"] = command_check(
            [sys.executable, "scripts/run_m07.py"]
        )

        run_report = json.loads(
            (ROOT / "artifacts/m07-run.json").read_text(encoding="utf-8")
        )
        required_run_cases = {
            "normal_v2_migrates_to_v3",
            "boundary_legacy_v1_remains_readable",
            "boundary_repeated_migration_is_idempotent",
            "declared_failure_rejects_unknown_quality",
            "rollback_restores_v2_fixture",
            "boundary_repeated_rollback_is_idempotent",
        }
        actual_run_cases = run_report.get("cases", {})
        checks["machine_readable_run"] = {
            "status": (
                "passed"
                if run_report.get("status") == "passed"
                and required_run_cases.issubset(actual_run_cases)
                and all(
                    actual_run_cases[name].get("status") == "passed"
                    for name in required_run_cases
                )
                else "failed"
            ),
            "artifact": "artifacts/m07-run.json",
            "cases": len(actual_run_cases),
        }

        suite = unittest.defaultTestLoader.discover(
            str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT)
        )
        result = unittest.TextTestRunner(
            stream=test_output,
            verbosity=2,
            resultclass=AuditedM07Result,
        ).run(suite)
        report["cases"] = [
            case for case in result.cases if case["category"] != "regression"
        ]
        tests_ok = (
            result.testsRun > 0
            and result.wasSuccessful()
            and not result.skipped
            and all(case["status"] == "passed" for case in result.cases)
        )
        checks["cumulative_tests"] = {
            "status": "passed" if tests_ok else "failed",
            "command": (
                f"{sys.executable} -m unittest discover -s tests -p test_*.py"
            ),
            "scope": "M01-M07 cumulative regression",
            "total": result.testsRun,
            "passed": sum(
                case["status"] == "passed" for case in result.cases
            ),
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
        }
        categories = coverage_result(report["cases"])
        checks["m07_coverage"] = {
            "status": (
                "passed"
                if all(value["status"] == "passed" for value in categories.values())
                else "failed"
            ),
            "categories": categories,
        }
    except Exception as exc:
        checks["execution"] = {
            "status": "failed",
            "error_type": type(exc).__name__,
        }
        test_output.write(
            "No se pudo completar la verificación: "
            + type(exc).__name__
            + "\n"
        )

    report["status"] = (
        "passed"
        if checks
        and all(check["status"] == "passed" for check in checks.values())
        else "failed"
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    evidence = {
        "assignment_id": report["assignment_id"],
        "status": report["status"],
        "generated_at": report["generated_at"],
        "commit_sha": report["commit_sha"],
        "source_dirty": report["source_dirty"],
        "team": list(EXPECTED_TEAM),
        "technical_authorship": {
            EXPECTED_TEAM[0]: "contrato v3, fixtures e inicialización idempotente",
            EXPECTED_TEAM[1]: "migración compatible, ejecución y rollback",
            EXPECTED_TEAM[2]: "verificación acumulada, cobertura y evidencia",
        },
        "synthetic_fixtures": True,
        "strategy": "expand-migrate-rollback",
        "commands": report["commands"],
        "results": {
            "status": report["status"],
            "checks": checks,
            "machine_readable_report": "artifacts/m07-verify.json",
            "run_report": "artifacts/m07-run.json",
            "verification_output": "artifacts/make-verify-output-m07.txt",
        },
    }
    contract_artifact = {
        "assignment_id": "m07-document-contract",
        "status": report["status"],
        "generated_at": report["generated_at"],
        "commit_sha": report["commit_sha"],
        "source_dirty": report["source_dirty"],
        "version": 3,
        "version_change": (
            "v3 requires synthetic quality; v1/v2 remain readable"
        ),
        "checks": {
            "required_files": checks.get("required_files", {}),
            "document_store_init": checks.get("document_store_init", {}),
            "m07_coverage": checks.get("m07_coverage", {}),
        },
    }

    save_json(ROOT / "artifacts/m07-verify.json", report)
    save_json(ROOT / "artifacts/m07-document-contract-verify.json", contract_artifact)
    save_json(ROOT / "evidence/m07-document-contract.json", evidence)
    verification_output = (
        test_output.getvalue()
        + "\nM07 verification: "
        + report["status"]
        + "\n"
    )
    (ROOT / "artifacts/make-verify-output-m07.txt").write_text(
        verification_output, encoding="utf-8"
    )
    print(verification_output, end="")
    print("=== RESUMEN DE VERIFICACIÓN M07 ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
