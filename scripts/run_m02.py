"""Puebla la base, ejecuta consultas M02 e imprime/guarda su reporte JSON."""
import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.migrate import apply_migrations
from scripts.evidence_support import source_revision
from src.relational import (
    seed_database, measurements_by_device, metric_summary, devices_by_status,
)
from src.runtime import connect_database


def json_value(value):
    """Conserva precisión decimal como texto y expresa las fechas en UTC."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    raise TypeError("Tipo no serializable")


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError()
        return result
    except ValueError:
        raise argparse.ArgumentTypeError("Usa una fecha ISO 8601 con zona horaria") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", action="store_true")
    parser.add_argument("--no-artifact", action="store_true",
                        help="No guardar reporte (para pruebas aisladas)")
    parser.add_argument("--device-id", default="sensor-lab-01")
    parser.add_argument("--start", type=timestamp, default="2026-09-03T00:00:00Z")
    parser.add_argument("--end", type=timestamp, default="2026-09-04T00:00:00Z")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--status", choices=("active", "inactive"), default="active")
    args = parser.parse_args()
    if args.start >= args.end or not 1 <= args.limit <= 1000 or not args.device_id:
        parser.error("Revisa dispositivo, inicio < fin y límite entre 1 y 1000")
    db = None
    result = {"module": "m02-relational-model", "status": "failed"}
    try:
        result.update(source_revision())
        db = connect_database(compose=args.compose)
        migrations = apply_migrations(db.connection)
        seeds = seed_database(db.connection)
        result = {
            **result,
            "module": "m02-relational-model", "status": "passed",
            "migrations": migrations, "seeds": seeds,
            "parameters": {
                "device_id": args.device_id, "start": args.start, "end": args.end,
                "limit": args.limit, "device_status": args.status,
            },
            "measurements": measurements_by_device(
                db.connection, args.device_id, args.start, args.end, args.limit),
            "metric_summary": metric_summary(
                db.connection, args.device_id, args.start, args.end),
            "devices": devices_by_status(db.connection, args.status),
        }
        db.connection.commit()
        return 0
    except Exception as exc:
        if db is not None:
            db.connection.rollback()
        result.update(status="failed", error_type=type(exc).__name__)
        return 1
    finally:
        if db is not None:
            db.close()
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(result, ensure_ascii=False, indent=2, default=json_value) + "\n"
        if not args.no_artifact:
            (ROOT / "artifacts").mkdir(exist_ok=True)
            (ROOT / "artifacts/m02-run.json").write_text(payload, encoding="utf-8")
        print(payload, end="", file=sys.stdout if result["status"] == "passed" else sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
