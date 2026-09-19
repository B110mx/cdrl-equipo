"""Verifica separación de usuarios, permisos mínimos y ausencia de secretos."""
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
from src.runtime import connect_database


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", action="store_true")
    args = parser.parse_args()
    report = {
        "assignment_id": "m03-role-separation", "status": "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "docker-compose" if args.compose else "postgres-env",
        "checks": {}, "commit_sha": None, "source_dirty": True,
    }
    db = None
    try:
        report.update(source_revision())
        required = (
            "db/migrations/003_roles.sql", "scripts/configure_roles.py",
            "scripts/check_no_secrets.py", "tests/test_roles.py",
            "docs/ADR-002-roles-postgresql.md",
        )
        report["checks"]["required_files"] = {
            "status": "passed" if all((ROOT / path).is_file() for path in required) else "failed"
        }
        if report["checks"]["required_files"]["status"] != "passed":
            raise RuntimeError("required_files")
        if args.compose:
            subprocess.run(["docker", "compose", "up", "-d", "--wait", "postgres"],
                           cwd=ROOT, check=True, timeout=180, capture_output=True)
            os.environ.update(compose_environment())
        db = connect_database(compose=args.compose)
        apply_migrations(db.connection)
        configure_roles(db.connection)
        db.close()
        db = None
        report["checks"]["database_roles"] = {"status": "passed"}
        secret_check = subprocess.run([sys.executable, "scripts/check_no_secrets.py"],
                                      cwd=ROOT, capture_output=True, text=True)
        report["checks"]["no_versioned_secrets"] = {
            "status": "passed" if secret_check.returncode == 0 else "failed"
        }
        suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_roles")
        output = io.StringIO()
        result = unittest.TextTestRunner(stream=output, verbosity=0).run(suite)
        report["checks"]["role_tests"] = {
            "status": "passed" if result.wasSuccessful() else "failed",
            "total": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
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
        save(ROOT / "artifacts/m03-verify.json", report)
        save(ROOT / "evidence/m03-role-separation.json", {
            "assignment_id": report["assignment_id"],
            "commit_sha": report["commit_sha"],
            "source_dirty": report["source_dirty"],
            "generated_at": report["generated_at"],
            "environment": report["environment"],
            "results": {"status": report["status"], "checks": report["checks"],
                        "machine_readable_report": "artifacts/m03-verify.json"},
        })
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())