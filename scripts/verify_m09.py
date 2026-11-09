"""Verificación reproducible de seguridad NoSQL y auditoría M09."""

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


TEAM = (
    "Abril Miranda Baltazar Varillas",
    "Luis Bryan Rojas Rodriguez",
    "Edwin Yahir Cruz Flores",
)
M09_CATEGORIES = {"normal": 1, "limits": 2, "declared_failure": 1}
DENIAL_TESTS = {
    "test_limit_reader_no_escribe_y_reporta_codigo",
    "test_limit_auditor_no_lee_eventos_y_si_consulta_auditoria",
    "test_declared_failure_writer_no_administra_eventos",
    "test_remediation_impide_que_el_abuso_llegue_al_backend",
}


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def command_check(command, timeout=180):
    try:
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
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "command": " ".join(command),
            "error_type": "TimeoutExpired",
        }


class AuditedM09Result(unittest.TextTestResult):
    """Registra casos y códigos esperados sin copiar excepciones sensibles."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    @staticmethod
    def category(test_id):
        method = test_id.rsplit(".", 1)[-1]
        if method.startswith("test_normal_"):
            return "normal"
        if method.startswith("test_limit_"):
            return "limits"
        if method.startswith("test_declared_failure_"):
            return "declared_failure"
        return "additional"

    def record(self, test, status, error=None):
        method = test.id().rsplit(".", 1)[-1]
        item = {
            "test": test.id(),
            "category": self.category(test.id()),
            "status": status,
        }
        if method in DENIAL_TESTS:
            item["expected_error_code"] = "ACCESS_DENIED"
            item["expected_audit_result"] = "denied"
        if error:
            item["error_type"] = error[0].__name__
        self.cases.append(item)

    def _exc_info_to_string(self, err, test):
        return f"M09 verification failed: {err[0].__name__}\n"

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


def category_coverage(cases):
    coverage = {}
    for category, minimum in M09_CATEGORIES.items():
        selected = [case for case in cases if case["category"] == category]
        coverage[category] = {
            "status": (
                "passed"
                if len(selected) >= minimum
                and all(case["status"] == "passed" for case in selected)
                else "failed"
            ),
            "cases": len(selected),
            "minimum": minimum,
        }
    return coverage


def validate_run_artifact(value):
    required = {
        "normal_authorized_read",
        "boundary_reader_write_denied",
        "boundary_auditor_business_read_denied",
        "declared_failure_writer_admin_denied",
        "controlled_abuse_remediated",
        "audit_contract_and_secret_absence",
    }
    cases = value.get("cases", {})
    denied = (
        "boundary_reader_write_denied",
        "boundary_auditor_business_read_denied",
        "declared_failure_writer_admin_denied",
        "controlled_abuse_remediated",
    )
    passed = (
        value.get("status") == "passed"
        and required.issubset(cases)
        and all(cases[name].get("status") == "passed" for name in required)
        and all(cases[name].get("error_code") == "ACCESS_DENIED" for name in denied)
        and cases["controlled_abuse_remediated"].get(
            "unguarded_access_observed") is True
        and cases["controlled_abuse_remediated"].get(
            "guarded_access_denied") is True
        and cases["audit_contract_and_secret_absence"].get(
            "forbidden_terms_absent") is True
    )
    return {
        "status": "passed" if passed else "failed",
        "artifact": "artifacts/m09-run.json",
        "cases": len(cases),
        "denied_cases_with_error_code": sum(
            cases.get(name, {}).get("error_code") == "ACCESS_DENIED"
            for name in denied
        ),
    }


def main():
    required = (
        "src/access_control.py",
        "src/access-control-policy.json",
        "scripts/render_dynamodb_iam_policy.py",
        "scripts/run_m09.py",
        "scripts/verify_m09.py",
        "tests/test_security_access.py",
        "tests/test_m09_seguridad.py",
        "docs/audit-event-schema.json",
        "docs/ADR-009-seguridad-colecciones.md",
        "fixtures/security-access-cases.json",
    )
    revision = source_revision()
    report = {
        "assignment_id": "m09-nosql-security-audit",
        "status": "failed",
        **revision,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commands": ["make setup", "make verify", "make run"],
        "checks": {},
        "cases": [],
    }
    checks = report["checks"]
    missing = [path for path in required if not (ROOT / path).is_file()]
    checks["required_files"] = {
        "status": "passed" if not missing else "failed",
        "missing": missing,
    }

    adr_path = ROOT / "docs/ADR-009-seguridad-colecciones.md"
    adr_text = adr_path.read_text(encoding="utf-8").lower() if adr_path.is_file() else ""
    adr_markers = (
        "mínimo privilegio", "actor", "acción", "recurso", "resultado",
        "remediación", "audit_writer", "dynamodb local", "aws",
    )
    checks["adr"] = {
        "status": (
            "passed" if all(marker in adr_text for marker in adr_markers)
            else "failed"),
        "required_topics": list(adr_markers),
    }
    checks["no_secrets"] = command_check(
        [sys.executable, "scripts/check_no_secrets.py"])
    checks["m09_run"] = command_check(
        [sys.executable, "scripts/run_m09.py"])

    try:
        run_artifact = json.loads(
            (ROOT / "artifacts/m09-run.json").read_text(encoding="utf-8"))
        checks["machine_readable_run"] = validate_run_artifact(run_artifact)
    except (OSError, json.JSONDecodeError) as error:
        run_artifact = {}
        checks["machine_readable_run"] = {
            "status": "failed",
            "error_type": type(error).__name__,
        }

    stream = io.StringIO()
    suite = unittest.TestSuite()
    for module in ("tests.test_security_access", "tests.test_m09_seguridad"):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
    result = unittest.TextTestRunner(
        stream=stream,
        verbosity=2,
        resultclass=AuditedM09Result,
    ).run(suite)
    report["cases"] = result.cases
    tests_ok = (
        result.testsRun > 0
        and result.wasSuccessful()
        and not result.skipped
        and all(case["status"] == "passed" for case in result.cases)
    )
    checks["m09_tests"] = {
        "status": "passed" if tests_ok else "failed",
        "total": result.testsRun,
        "passed": sum(case["status"] == "passed" for case in result.cases),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }
    coverage = category_coverage(result.cases)
    checks["coverage"] = {
        "status": (
            "passed"
            if all(value["status"] == "passed" for value in coverage.values())
            else "failed"),
        "categories": coverage,
    }
    checks["negative_access"] = {
        "status": (
            "passed"
            if sum(
                case.get("expected_error_code") == "ACCESS_DENIED"
                and case["status"] == "passed"
                for case in result.cases
            ) >= 4
            else "failed"),
        "passed_cases": sum(
            case.get("expected_error_code") == "ACCESS_DENIED"
            and case["status"] == "passed"
            for case in result.cases
        ),
        "expected_error_code": "ACCESS_DENIED",
    }

    report["status"] = (
        "passed"
        if checks and all(check["status"] == "passed" for check in checks.values())
        else "failed"
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    evidence = {
        "assignment_id": report["assignment_id"],
        "status": report["status"],
        "generated_at": report["generated_at"],
        "commit_sha": report["commit_sha"],
        "source_dirty": report["source_dirty"],
        "team": list(TEAM),
        "technical_authorship": {
            TEAM[0]: "matriz de permisos, contrato de auditoría, IAM y fixtures",
            TEAM[1]: "fachada autorizada, persistencia idempotente y abuso/remediación",
            TEAM[2]: "pruebas negativas, verificación M09, ADR y evidencia",
        },
        "synthetic_fixtures": True,
        "commands": report["commands"],
        "results": {
            "checks": checks,
            "cases": report["cases"],
            "run_report": "artifacts/m09-run.json",
            "verification_report": "artifacts/m09-verify.json",
            "verification_output": "artifacts/make-verify-output-m09.txt",
        },
    }
    save_json(ROOT / "artifacts/m09-verify.json", report)
    save_json(ROOT / "evidence/m09-nosql-security-audit.json", evidence)
    output = (
        stream.getvalue()
        + f"\nM09 verification: {report['status']}\n"
        + json.dumps({
            "commit_sha": report["commit_sha"],
            "source_dirty": report["source_dirty"],
            "checks": checks,
        }, ensure_ascii=False, indent=2)
        + "\n"
    )
    (ROOT / "artifacts/make-verify-output-m09.txt").write_text(
        output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
