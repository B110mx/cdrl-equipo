"""Verifica M03, conserva las regresiones y genera evidencia reproducible."""
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

from scripts.configure_roles import compose_environment, configure_roles
from scripts.evidence_support import source_revision
from scripts.migrate import apply_migrations
from scripts.verify_m02 import AuditedResult
from src.runtime import connect_database


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitized(text, environment):
    for key, value in environment.items():
        if key.endswith("_PASSWORD") and value:
            text = text.replace(value, "[REDACTED]")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", action="store_true")
    args = parser.parse_args()
    report = {
        "assignment_id": "m03-role-separation", "status": "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "docker-compose" if args.compose else "postgres-env",
        "checks": {}, "cases": [], "commit_sha": None, "source_dirty": True,
    }
    db = None
    environment = dict(os.environ)
    test_output = io.StringIO()
    try:
        report.update(source_revision())
        required = (
            "db/migrations/003_roles.sql", "scripts/configure_roles.py",
            "scripts/check_no_secrets.py", "scripts/run_m03.py",
            "tests/test_roles.py", "docs/ADR-002-roles-postgresql.md",
            "evidence/m03-role-separation.json",
        )
        report["checks"]["required_files"] = {
            "status": "passed" if all((ROOT / path).is_file() for path in required) else "failed"
        }
        if report["checks"]["required_files"]["status"] != "passed":
            raise RuntimeError("required_files")
        if args.compose:
            subprocess.run(["docker", "compose", "up", "-d", "--wait", "postgres"],
                           cwd=ROOT, check=True, timeout=180, capture_output=True)
            environment.update(compose_environment())
            os.environ.update(environment)
        db = connect_database(compose=args.compose)
        apply_migrations(db.connection)
        configure_roles(db.connection, environment)
        db.close()
        db = None
        report["checks"]["database_roles"] = {"status": "passed"}

        secret_check = subprocess.run([sys.executable, "scripts/check_no_secrets.py"],
                                      cwd=ROOT, capture_output=True, text=True)
        report["checks"]["no_versioned_secrets"] = {
            "status": "passed" if secret_check.returncode == 0 else "failed"
        }

        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py",
                                                     top_level_dir=str(ROOT))
        result = unittest.TextTestRunner(
            stream=test_output, verbosity=2, resultclass=AuditedResult).run(suite)
        report["cases"] = result.cases
        for case in report["cases"]:
            if not case["test"].startswith("tests.test_roles."):
                continue
            name = case["test"].rsplit(".", 1)[-1]
            if name == "test_declared_permissions_are_available":
                case["category"] = "normal"
            elif name.startswith("test_limits_"):
                case["category"] = "limits"
            elif name.startswith("test_declared_failure_"):
                case["category"] = "declared_failure"
            elif "cannot" in name:
                case["category"] = "access_denied"
            else:
                case["category"] = "constraints"
        role_cases = [case for case in result.cases if case["test"].startswith("tests.test_roles.")]
        report["checks"]["tests"] = {
            "status": "passed" if result.wasSuccessful() and result.testsRun > 0 else "failed",
            "total": result.testsRun,
            "passed": sum(case["status"] == "passed" for case in result.cases),
            "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped),
        }
        negative_cases = [case for case in role_cases if "cannot" in case["test"]]
        report["checks"]["role_contract"] = {
            "status": "passed" if len(role_cases) >= 6 and len(negative_cases) >= 3 and
            all(case["status"] == "passed" for case in role_cases) else "failed",
            "cases": len(role_cases),
            "negative_access_cases": sum(case["status"] == "passed" for case in negative_cases),
            "single_membership_verified": any(
                "exactly_one_cdrl_membership" in case["test"] and case["status"] == "passed"
                for case in role_cases),
        }
        coverage = {
            category: [case for case in role_cases if case["category"] == category]
            for category in ("normal", "limits", "declared_failure", "access_denied")
        }
        report["checks"]["m03_coverage"] = {
            "status": "passed" if len(coverage["normal"]) >= 1 and
            len(coverage["limits"]) >= 2 and len(coverage["declared_failure"]) >= 1 and
            len(coverage["access_denied"]) >= 3 and
            all(case["status"] == "passed" for cases in coverage.values() for case in cases)
            else "failed",
            "normal_cases": len(coverage["normal"]),
            "limit_cases": len(coverage["limits"]),
            "declared_failure_cases": len(coverage["declared_failure"]),
            "access_denied_cases": len(coverage["access_denied"]),
        }
        report["status"] = "passed" if all(
            check["status"] == "passed" for check in report["checks"].values()
        ) else "failed"
    except Exception as exc:
        report["checks"]["execution"] = {"status": "failed", "error_type": type(exc).__name__}
    finally:
        if db is not None:
            db.close()
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        (ROOT / "artifacts").mkdir(exist_ok=True)
        save_json(ROOT / "artifacts/m03-verify.json", report)
        evidence = {
            "assignment_id": report["assignment_id"], "commit_sha": report["commit_sha"],
            "source_dirty": report["source_dirty"], "generated_at": report["generated_at"],
            "environment": report["environment"],
            "results": {"status": report["status"], "checks": report["checks"],
                        "machine_readable_report": "artifacts/m03-verify.json",
                        "verification_output": "artifacts/make-verify-output.txt"},
        }
        save_json(ROOT / "evidence/m03-role-separation.json", evidence)
        summary = json.dumps(report, ensure_ascii=False, indent=2)
        log = sanitized(test_output.getvalue() + "\n" + summary + "\n", environment)
        (ROOT / "artifacts/make-verify-output.txt").write_text(log, encoding="utf-8")
        print(summary)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
