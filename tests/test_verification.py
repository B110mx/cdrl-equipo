"""El verificador no debe producir falsos positivos ni exponer errores sensibles."""
import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_m02


class TestVerification(unittest.TestCase):
    def test_missing_category_is_failure(self):
        cases = [{"category": name, "status": "passed"}
                 for name in verify_m02.CATEGORIES if name != "empty"]
        self.assertEqual(verify_m02.category_results(cases)["empty"]["status"], "failed")

    def test_skipped_case_is_failure(self):
        cases = [{"category": "normal", "status": "skipped"}]
        self.assertEqual(verify_m02.category_results(cases)["normal"]["status"], "failed")

    def test_error_messages_are_sanitized(self):
        def synthetic_failure():
            raise RuntimeError("sensitive-marker-not-for-report")
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, resultclass=verify_m02.AuditedResult).run(
            unittest.TestSuite([unittest.FunctionTestCase(synthetic_failure)]))
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.cases[0]["status"], "failed")
        self.assertNotIn("sensitive-marker-not-for-report", stream.getvalue())

    def test_database_failure_produces_failed_evidence(self):
        stream = io.StringIO()
        # No cambia los archivos ni detiene PostgreSQL: inyecta el error de conexión.
        with patch("sys.argv", ["verify_m02.py"]), \
             patch.object(verify_m02, "connect_database", side_effect=ConnectionError("sensitive-marker")), \
             patch.object(verify_m02, "save_json") as save, \
             patch.object(Path, "write_text"), contextlib.redirect_stdout(stream):
            code = verify_m02.main()
        self.assertEqual(code, 1)
        report = save.call_args_list[0].args[1]
        evidence = save.call_args_list[-1].args[1]
        self.assertEqual(report["status"], "failed")
        self.assertEqual(evidence["results"]["status"], "failed")
        self.assertEqual(report["checks"]["execution"]["error_type"], "ConnectionError")
        self.assertNotIn("sensitive-marker", stream.getvalue())
