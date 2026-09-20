"""Falla si Git contiene patrones comunes de credenciales o conexiones."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    r"AKIA[0-9A-Z]{16}",
    r"(?:ghp|github_pat)_[A-Za-z0-9_]+",
    r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----",
    r"postgres(?:ql)?://[^\s]+",
)


def main():
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                             capture_output=True, text=False).stdout.decode().split("\0")
    suspicious = []
    for relative in filter(None, tracked):
        path = ROOT / relative
        # Durante una corrección local, Git aún enumera archivos eliminados no
        # preparados. Su ausencia no debe convertir la revisión en un error.
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if any(re.search(pattern, content) for pattern in PATTERNS):
            suspicious.append(relative)
    if suspicious:
        print("Se encontraron patrones sensibles en archivos versionados:")
        print("\n".join(suspicious))
        return 1
    print("Secretos versionados: ninguno detectado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
