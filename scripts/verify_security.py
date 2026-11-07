"""Verifica controles de acceso, contrato de auditoría y evidencia M09."""

import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision


MINIMUM_COVERAGE = {"normal": 1, "limits": 2, "declared_failure": 1}
REQUIRED_FILES = (
    "src/access_control.py",
    "src/access-control-policy.json",
    "scripts/render_dynamodb_iam_policy.py",
    "tests/test_security_access.py",
    "docs/audit-event-schema.json",
    "docs/ADR-009-seguridad-colecciones.md",
    "fixtures/security-access-cases.json",
)


class SecurityResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    @staticmethod
    def category(test_id):
        method = test_id.rsplit(".", 1)[-1]
        if method.startswith("test_normal_"):
            return "normal"
        if method.startswith("test_limite_"):
            return "limits"
        if method.startswith("test_fallo_declarado_"):
            return "declared_failure"
        return "additional"

    def record(self, test, status, error=None):
        item = {
            "test": test.id(),
            "category": self.category(test.id()),
            "status": status,
        }
        if error:
            item["error_type"] = error[0].__name__
        self.cases.append(item)

    def _exc_info_to_string(self, err, test):
        return f"Security verification failed: {err[0].__name__}\n"

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
        super().addSkip(test, "Skipped test is not accepted")
        self.record(test, "skipped")


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    revision = source_revision()
    missing = [item for item in REQUIRED_FILES if not (ROOT / item).is_file()]
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "tests.test_security_access")
    result = unittest.TextTestRunner(
        stream=stream, verbosity=2, resultclass=SecurityResult,
    ).run(suite)
    coverage = {}
    for category, minimum in MINIMUM_COVERAGE.items():
        cases = [case for case in result.cases if case["category"] == category]
        coverage[category] = {
            "status": (
                "passed" if len(cases) >= minimum
                and all(case["status"] == "passed" for case in cases)
                else "failed"),
            "cases": len(cases),
            "minimum": minimum,
        }

    status = (
        "passed"
        if not missing
        and result.wasSuccessful()
        and not result.skipped
        and all(item["status"] == "passed" for item in coverage.values())
        else "failed"
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "assignment_id": "security-collection-access-controls",
        "status": status,
        **revision,
        "generated_at": generated_at,
        "commands": ["python scripts/verify_security.py"],
        "workflow_commands": ["make setup", "make verify", "make run"],
        "checks": {
            "required_files": {
                "status": "passed" if not missing else "failed",
                "missing": missing,
            },
            "security_tests": {
                "status": "passed" if result.wasSuccessful() else "failed",
                "total": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
            },
            "coverage": {
                "status": (
                    "passed" if all(
                        value["status"] == "passed" for value in coverage.values())
                    else "failed"),
                "categories": coverage,
            },
        },
        "cases": result.cases,
    }
    save_json(ROOT / "artifacts/security-access-controls-run.json", {
        "assignment_id": report["assignment_id"],
        "status": status,
        "generated_at": generated_at,
        "cases": result.cases,
    })
    save_json(ROOT / "artifacts/security-access-controls-verify.json", report)
    evidence = {
        "assignment_id": report["assignment_id"],
        "status": status,
        "generated_at": generated_at,
        "commit_sha": revision["commit_sha"],
        "source_dirty": revision["source_dirty"],
        "technical_authorship": {
            "Abril Miranda Baltazar Varillas": (
                "matriz de permisos, contrato de auditoría, políticas IAM y fixtures"
            ),
        },
        "synthetic_fixtures": True,
        "commands": report["commands"],
        "workflow_commands": report["workflow_commands"],
        "results": {
            "checks": report["checks"],
            "run_report": "artifacts/security-access-controls-run.json",
            "verification_report": "artifacts/security-access-controls-verify.json",
            "verification_output": (
                "artifacts/make-verify-output-security.txt"),
        },
    }
    save_json(ROOT / "evidence/security-access-controls.json", evidence)
    output = (
        stream.getvalue()
        + f"\nSecurity access verification: {status}\n"
        + json.dumps(report["checks"], ensure_ascii=False, indent=2)
        + "\n"
    )
    (ROOT / "artifacts/make-verify-output-security.txt").write_text(
        output, encoding="utf-8")
    print(output, end="")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
