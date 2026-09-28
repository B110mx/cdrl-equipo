"""Verifica M04, conserva M03 y genera evidencia reproducible."""
import argparse
import hashlib
import io
import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fixtures.generate_fixtures import generate
from scripts.evidence_support import source_revision
from scripts.verify_m02 import AuditedResult

FIXTURE_FILES = ("document_data.json", "graph_data.json", "column_data.csv", "object_data.jsonl")


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture_digest():
    digest = hashlib.sha256()
    for name in FIXTURE_FILES:
        digest.update(name.encode())
        digest.update((ROOT / "fixtures" / name).read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", action="store_true")
    args = parser.parse_args()
    report = {
        "assignment_id": "m04-storage-comparison", "status": "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "docker-compose" if args.compose else "local-models",
        "checks": {}, "cases": [], "commit_sha": None, "source_dirty": True,
    }
    output = io.StringIO()
    try:
        report.update(source_revision())
        required = (
            "docs/investigacion-alternativas-almacenamiento.md",
            "docs/ADR-003-seleccion-almacenamiento-eventos.md",
            "fixtures/generate_fixtures.py", "src/storage_comparison.py",
            "scripts/run_m04.py", "tests/test_storage_comparison.py",
        )
        missing = [path for path in required if not (ROOT / path).is_file()]
        report["checks"]["required_files"] = {
            "status": "passed" if not missing else "failed", "missing_count": len(missing)}
        if missing:
            raise RuntimeError("required_files")

        generate()
        first_digest = fixture_digest()
        generate()
        second_digest = fixture_digest()
        report["checks"]["deterministic_fixtures"] = {
            "status": "passed" if first_digest == second_digest else "failed",
            "sha256": second_digest, "event_count": 5,
        }

        regression = subprocess.run(
            [sys.executable, "scripts/verify_m03.py", *(["--compose"] if args.compose else [])],
            cwd=ROOT, capture_output=True, text=True, timeout=240)
        report["checks"]["m03_regression"] = {
            "status": "passed" if regression.returncode == 0 else "failed"}
        output.write(regression.stdout)
        if regression.returncode != 0:
            output.write("M03 regression failed; details omitted.\n")

        secret_check = subprocess.run(
            [sys.executable, "scripts/check_no_secrets.py"], cwd=ROOT,
            capture_output=True, text=True, timeout=30)
        report["checks"]["no_versioned_secrets"] = {
            "status": "passed" if secret_check.returncode == 0 else "failed"}

        suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_storage_comparison")
        result = unittest.TextTestRunner(
            stream=output, verbosity=2, resultclass=AuditedResult).run(suite)
        report["cases"] = result.cases
        for case in report["cases"]:
            name = case["test"].rsplit(".", 1)[-1]
            if name.startswith("test_normal_"):
                case["category"] = "normal"
            elif name.startswith("test_limit_"):
                case["category"] = "limits"
            elif name.startswith("test_declared_failure_"):
                case["category"] = "declared_failure"
            else:
                case["category"] = "constraints"
        report["checks"]["tests"] = {
            "status": "passed" if result.wasSuccessful() and result.testsRun == 5 else "failed",
            "total": result.testsRun,
            "passed": sum(case["status"] == "passed" for case in report["cases"]),
            "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped),
        }
        coverage = {category: [case for case in report["cases"] if case["category"] == category]
                    for category in ("normal", "limits", "declared_failure")}
        report["checks"]["m04_coverage"] = {
            "status": "passed" if len(coverage["normal"]) >= 1 and
            len(coverage["limits"]) >= 2 and len(coverage["declared_failure"]) >= 1 and
            all(case["status"] == "passed" for cases in coverage.values() for case in cases)
            else "failed",
            "normal_cases": len(coverage["normal"]), "limit_cases": len(coverage["limits"]),
            "declared_failure_cases": len(coverage["declared_failure"]),
            "stores_covered": ["document", "graph", "column", "object"],
        }

        runtime = subprocess.run([sys.executable, "scripts/run_m04.py"], cwd=ROOT,
                                 capture_output=True, text=True, timeout=60)
        report["checks"]["runtime"] = {
            "status": "passed" if runtime.returncode == 0 else "failed",
            "report": "artifacts/m04-run.json"}
        report["status"] = "passed" if all(
            check["status"] == "passed" for check in report["checks"].values()) else "failed"
    except Exception as exc:
        report["checks"]["execution"] = {"status": "failed", "error_type": type(exc).__name__}
        output.write("M04 verification failed: " + type(exc).__name__ + "\n")
    finally:
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        save_json(ROOT / "artifacts/m04-verify.json", report)
        evidence = {
            "assignment_id": report["assignment_id"], "commit_sha": report["commit_sha"],
            "source_dirty": report["source_dirty"], "generated_at": report["generated_at"],
            "environment": report["environment"],
            "authors": ["Abril Miranda Baltazar Varillas", "Luis Bryan Rojas Rodriguez",
                        "Edwin Yahir Cruz Flores"],
            "results": {"status": report["status"], "checks": report["checks"],
                        "machine_readable_report": "artifacts/m04-verify.json",
                        "runtime_report": "artifacts/m04-run.json",
                        "verification_output": "artifacts/make-verify-output.txt"},
        }
        save_json(ROOT / "evidence/m04-storage-comparison.json", evidence)
        log = output.getvalue() + "\nM04 verification: " + report["status"] + "\n"
        (ROOT / "artifacts/make-verify-output.txt").write_text(log, encoding="utf-8")
        print(log, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
