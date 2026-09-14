"""Identidad de la ejecución; excluye salidas generadas del indicador de código sucio."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_revision():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
    # No cuenta los reportes regenerados, paquetes locales ni evidencia histórica.
    paths = ["src", "tests", "scripts", "db", "docs", ".github", "Makefile",
             "README.md", "requirements.txt", "docker-compose.yml", ".gitignore",
             "artifacts/test_cases.sql"]
    dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *paths],
        cwd=ROOT, text=True, timeout=10,
    ).strip())
    return {"commit_sha": sha, "source_dirty": dirty}
