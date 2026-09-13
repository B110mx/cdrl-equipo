"""Aplica las migraciones SQL en orden; cada archivo controla su transacción."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime import connect_database


def apply_migrations(connection):
    """Ejecuta DDL idempotente sobre el search_path de la conexión recibida."""
    paths = sorted((ROOT / "db/migrations").glob("*.sql"))
    if not paths:
        raise RuntimeError("No hay migraciones SQL")
    try:
        with connection.cursor() as cursor:
            for path in paths:
                cursor.execute(path.read_text(encoding="utf-8-sig"))
                connection.commit()
    except Exception:
        connection.rollback()
        raise
    return [path.name for path in paths]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", action="store_true",
                        help="Usar PostgreSQL local de Docker Compose")
    args = parser.parse_args()
    db = None
    try:
        db = connect_database(compose=args.compose)
        names = apply_migrations(db.connection)
        print(json.dumps({"status": "passed", "migrations": names}))
        return 0
    except Exception as exc:
        # Los errores de conexión/SQL pueden incluir secretos o datos de filas.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}),
              file=sys.stderr)
        return 1
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
