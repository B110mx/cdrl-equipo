"""Verificación M08 reproducible con regresión acumulada y evidencia auditable."""

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
M08_CATEGORIES = {"normal": 1, "limits": 2, "declared_failure": 1}


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


class AuditedM08Result(unittest.TextTestResult):
    """Registra resultados sin copiar configuración ni excepciones sensibles."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    @staticmethod
    def category(test_id):
        if not test_id.startswith("tests.test_m08_paginacion."):
            return "regression"
        method = test_id.rsplit(".", 1)[-1]
        if method.startswith("test_normal_"):
            return "normal"
        if method.startswith("test_limit_"):
            return "limits"
        if method.startswith("test_declared_failure_"):
            return "declared_failure"
        return "m08_other"

    def record(self, test, status, error=None):
        entry = {
            "test": test.id(),
            "category": self.category(test.id()),
            "status": status,
        }
        if error:
            entry["error_type"] = error[0].__name__
        self.cases.append(entry)

    def _exc_info_to_string(self, err, test):
        return f"Error de verificación: {err[0].__name__}\n"

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


def category_coverage(cases):
    coverage = {}
    for category, minimum in M08_CATEGORIES.items():
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
    required_cases = {
        "normal_complete_ordered_traversal",
        "boundary_empty_device",
        "boundary_final_partial_page",
        "boundary_insertions_are_positional",
        "declared_failure_mismatched_cursor_rejected",
    }
    cases = value.get("cases", {})
    passed = (
        value.get("status") == "passed"
        and required_cases.issubset(cases)
        and all(cases[name].get("status") == "passed" for name in required_cases)
        and value.get("normal_page_sizes") == [5, 5, 5, 5, 4]
    )
    return {
        "status": "passed" if passed else "failed",
        "artifact": "artifacts/m08-run.json",
        "cases": len(cases),
    }


def validate_benchmark_artifact(value):
    method = value.get("method", {})
    environment = value.get("environment", {})
    baseline = value.get("baseline", {})
    optimized = value.get("optimized", {})
    comparison = value.get("comparison", {})
    metric_keys = {"p50", "p95", "minimum", "maximum"}
    metrics_valid = all(
        metric_keys.issubset(variant)
        and all(isinstance(variant[key], (int, float)) and variant[key] >= 0
                for key in metric_keys)
        for variant in (baseline, optimized)
    )
    passed = (
        value.get("status") == "passed"
        and method.get("fixture_kind") == "deterministic-synthetic"
        and method.get("dataset_events", 0) >= 24
        and method.get("warmup_runs_excluded", 0) >= 1
        and method.get("measured_repetitions_per_variant", 0) >= 20
        and 1 <= method.get("page_size", 0) <= 100
        and {"python", "platform", "backend", "region", "table"}.issubset(
            environment)
        and metrics_valid
        and baseline.get("items_materialized_per_run", 0)
        > optimized.get("items_returned_per_run", 0)
        and comparison.get("same_first_page") is True
        and "no se generaliza" in comparison.get("claim", "").lower()
    )
    return {
        "status": "passed" if passed else "failed",
        "artifact": "artifacts/m08-benchmark.json",
        "dataset_events": method.get("dataset_events"),
        "warmup_runs": method.get("warmup_runs_excluded"),
        "repetitions": method.get("measured_repetitions_per_variant"),
        "baseline_p50_ms": baseline.get("p50"),
        "baseline_p95_ms": baseline.get("p95"),
        "optimized_p50_ms": optimized.get("p50"),
        "optimized_p95_ms": optimized.get("p95"),
    }


def main():
    required = (
        "src/document_store.py",
        "scripts/run_m08.py",
        "scripts/benchmark_m08.py",
        "scripts/verify_m08.py",
        "tests/test_m08_paginacion.py",
        "docs/M08-pagination-contract.md",
        "docs/ADR-008-paginacion-rendimiento.md",
        "fixtures/m08-pagination.json",
    )
    revision = source_revision()
    report = {
        "assignment_id": "m08-document-query-performance",
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

    adr_text = (ROOT / "docs/ADR-008-paginacion-rendimiento.md").read_text(
        encoding="utf-8").lower() if not missing else ""
    adr_markers = (
        "clave primaria", "p50", "p95", "costo", "fallos",
        "alternativas descartadas", "producción",
    )
    checks["adr_decision"] = {
        "status": (
            "passed" if all(marker in adr_text for marker in adr_markers)
            else "failed"),
        "required_topics": list(adr_markers),
    }

    checks["no_secrets"] = command_check(
        [sys.executable, "scripts/check_no_secrets.py"])
    checks["document_store_init"] = command_check(
        [sys.executable, "scripts/init_document_store.py"])
    checks["m08_run"] = command_check(
        [sys.executable, "scripts/run_m08.py"])
    checks["m08_benchmark"] = command_check(
        [sys.executable, "scripts/benchmark_m08.py"])

    try:
        run_artifact = json.loads(
            (ROOT / "artifacts/m08-run.json").read_text(encoding="utf-8"))
        benchmark_artifact = json.loads(
            (ROOT / "artifacts/m08-benchmark.json").read_text(encoding="utf-8"))
        checks["machine_readable_run"] = validate_run_artifact(run_artifact)
        checks["machine_readable_benchmark"] = validate_benchmark_artifact(
            benchmark_artifact)
    except (OSError, json.JSONDecodeError) as error:
        run_artifact = {}
        benchmark_artifact = {}
        checks["machine_readable_artifacts"] = {
            "status": "failed",
            "error_type": type(error).__name__,
        }

    output_stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(
        stream=output_stream,
        verbosity=2,
        resultclass=AuditedM08Result,
    ).run(suite)
    report["cases"] = [
        case for case in result.cases if case["category"] != "regression"]
    tests_ok = (
        result.testsRun > 0
        and result.wasSuccessful()
        and not result.skipped
        and all(case["status"] == "passed" for case in result.cases)
    )
    checks["cumulative_tests"] = {
        "status": "passed" if tests_ok else "failed",
        "command": f"{sys.executable} -m unittest discover -s tests -p test_*.py",
        "scope": "M01-M08 cumulative regression",
        "total": result.testsRun,
        "passed": sum(case["status"] == "passed" for case in result.cases),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }
    coverage = category_coverage(report["cases"])
    checks["m08_coverage"] = {
        "status": (
            "passed"
            if all(value["status"] == "passed" for value in coverage.values())
            else "failed"),
        "categories": coverage,
    }

    report["status"] = (
        "passed"
        if checks and all(check["status"] == "passed" for check in checks.values())
        else "failed")
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    evidence = {
        "assignment_id": report["assignment_id"],
        "status": report["status"],
        "generated_at": report["generated_at"],
        "commit_sha": report["commit_sha"],
        "source_dirty": report["source_dirty"],
        "team": list(TEAM),
        "technical_authorship": {
            TEAM[0]: "contrato de paginación, clave de acceso y fixture sintético",
            TEAM[1]: "API paginada, validación de cursor, ejecución y benchmark",
            TEAM[2]: "pruebas, verificación acumulada, ADR y evidencia",
        },
        "synthetic_fixtures": True,
        "commands": report["commands"],
        "results": {
            "status": report["status"],
            "checks": checks,
            "run_report": "artifacts/m08-run.json",
            "benchmark_report": "artifacts/m08-benchmark.json",
            "verification_report": "artifacts/m08-verify.json",
            "verification_output": "artifacts/make-verify-output-m08.txt",
        },
        "benchmark": {
            "environment": benchmark_artifact.get("environment", {}),
            "method": benchmark_artifact.get("method", {}),
            "baseline": benchmark_artifact.get("baseline", {}),
            "optimized": benchmark_artifact.get("optimized", {}),
            "comparison": benchmark_artifact.get("comparison", {}),
        },
    }
    save_json(ROOT / "artifacts/m08-verify.json", report)
    save_json(ROOT / "evidence/m08-query-performance.json", evidence)
    verification_output = (
        output_stream.getvalue()
        + f"\nM08 verification: {report['status']}\n"
        + json.dumps({
            "commit_sha": report["commit_sha"],
            "source_dirty": report["source_dirty"],
            "checks": checks,
        }, ensure_ascii=False, indent=2)
        + "\n"
    )
    (ROOT / "artifacts/make-verify-output-m08.txt").write_text(
        verification_output, encoding="utf-8")
    print(verification_output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
