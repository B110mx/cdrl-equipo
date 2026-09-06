"""Run the team's unit/integration tests and save auditable M01 results."""
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


def main():
    os.chdir(ROOT)
    report = {
        "assignment_id": "m01-data-contract",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "checks": {},
    }
    output = io.StringIO()
    checks = report["checks"]
    try:
        required = [
            "docs/M01-data-contract.md", "docs/ADR-001-python.md",
            "db/migrations/001_telemetry.sql", "db/seed/001_telemetry_seed.sql",
            "evidence/m01-data-contract.json",
        ]
        for path in required:
            if not (ROOT / path).is_file():
                raise RuntimeError("Missing required file: " + path)
        json.loads((ROOT / "evidence/m01-data-contract.json").read_text(encoding="utf-8-sig"))
        checks["required_files"] = {"status": "passed"}
        subprocess.run(["docker", "compose", "config", "--quiet"], check=True, timeout=30)
        subprocess.run(
            ["docker", "compose", "up", "-d", "--wait", "postgres"],
            check=True, timeout=180,
        )
        checks["postgres_started"] = {"status": "passed"}
        # Use the actual resolved Compose configuration, including local .env.
        config = json.loads(subprocess.check_output(
            ["docker", "compose", "config", "--format", "json"], text=True, timeout=30
        ))
        pg = config["services"]["postgres"]
        env = pg["environment"]
        for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
            os.environ[key] = str(env[key])
        os.environ["POSTGRES_HOST"] = "127.0.0.1"
        port = next(p for p in pg["ports"] if int(p["target"]) == 5432)
        os.environ["POSTGRES_PORT"] = str(port["published"])
        # The integration suite creates and removes its own schema.
        suite = unittest.TestSuite(
            unittest.defaultTestLoader.discover(
                str(ROOT / "tests"), pattern=pattern, top_level_dir=str(ROOT)
            )
            for pattern in ("test_telemetry.py", "test_integration.py")
        )
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
        checks["tests"] = {
            "status": "passed" if result.wasSuccessful() and not result.skipped and result.testsRun else "failed",
            "total": result.testsRun,
            "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
            "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped),
        }
        from tests.test_integration import TestTelemetryIntegration
        checks["database_reproducibility"] = TestTelemetryIntegration.evidence
        report["status"] = "passed" if all(c["status"] == "passed" for c in checks.values()) else "failed"
    except Exception as exc:
        # Never write connection strings/passwords or database exception details.
        checks["execution"] = {"status": "failed", "error_type": type(exc).__name__}
        output.write("Verification could not finish: " + type(exc).__name__ + "\n")
    finally:
        log = output.getvalue()
        for secret in (os.getenv("POSTGRES_PASSWORD"),):
            if secret:
                log = log.replace(secret, "[REDACTED]")
        print(log, end="")
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        (artifacts / "m01-verify.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (artifacts / "make-verify-output.txt").write_text(
            log + "\nM01 verification: " + report["status"] + "\n", encoding="utf-8"
        )
        print("M01 verification:", report["status"])
        # Regenerate after checkout so the delivered evidence names that commit.
        evidence_path = ROOT / "evidence/m01-data-contract.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
        evidence["commitSha"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=10
        ).strip()
        evidence["results"] = {
            "status": report["status"],
            "tests": checks.get("tests", {"status": "failed"}),
            "databaseReproducibility": checks.get("database_reproducibility", {"status": "failed"}),
            "machineReadableReport": "artifacts/m01-verify.json",
            "verificationOutput": "artifacts/make-verify-output.txt",
        }
        evidence["generatedAt"] = report["generated_at"]
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
