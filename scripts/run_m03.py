"""Demuestra el flujo M03 usando cuatro conexiones con privilegios separados."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.configure_roles import compose_environment, configure_roles
from scripts.evidence_support import source_revision
from scripts.migrate import apply_migrations
from src.relational import seed_database
from src.runtime import connect_database

EVENT_ID = "018f47a0-79f2-7c19-bc7f-1a26d47e93ff"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", action="store_true")
    args = parser.parse_args()
    report = {"module": "m03-role-separation", "status": "failed", **source_revision()}
    opened = []
    admin = None
    try:
        admin = connect_database(compose=args.compose)
        opened.append(admin)
        apply_migrations(admin.connection)
        configure_roles(admin.connection, compose_environment() if args.compose else None)
        seed_database(admin.connection)
        with admin.connection.cursor() as cursor:
            cursor.execute("DELETE FROM telemetry_measurements WHERE event_id = %s", (EVENT_ID,))
        admin.connection.commit()

        migrator = connect_database(compose=args.compose, role="migrator")
        opened.append(migrator)
        with migrator.connection.cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS m03_migration_probe (probe_id integer)")
            cursor.execute("DROP TABLE m03_migration_probe")
        migrator.connection.commit()

        writer = connect_database(compose=args.compose, role="writer")
        opened.append(writer)
        with writer.connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO telemetry_measurements
                    (event_id, device_id, recorded_at, metric, value, unit, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (EVENT_ID, "sensor-lab-01", "2026-09-03T18:01:00Z",
                  "temperature", 24.5, "celsius", '{"source":"synthetic-m03"}'))
        writer.connection.commit()

        reader = connect_database(compose=args.compose, role="reader")
        opened.append(reader)
        with reader.connection.cursor() as cursor:
            cursor.execute("""
                SELECT device_id, metric, value, unit
                FROM telemetry_measurements WHERE event_id = %s
            """, (EVENT_ID,))
            row = cursor.fetchone()

        operator = connect_database(compose=args.compose, role="operator")
        opened.append(operator)
        with operator.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM devices")
            device_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM telemetry_measurements")
            measurement_count = cursor.fetchone()[0]

        report.update(status="passed", operations={
            "migration": "create_and_drop_probe",
            "write": {"event_id": EVENT_ID, "result": "inserted"},
            "read": {"device_id": row[0], "metric": row[1],
                     "value": str(row[2]), "unit": row[3]},
            "operation": {"device_count": device_count,
                          "measurement_count": measurement_count},
        })
        return 0
    except Exception as exc:
        report.update(error_type=type(exc).__name__)
        return 1
    finally:
        if admin is not None and admin.connection and not admin.connection.closed:
            try:
                admin.connection.rollback()
                with admin.connection.cursor() as cursor:
                    cursor.execute("DELETE FROM telemetry_measurements WHERE event_id = %s", (EVENT_ID,))
                admin.connection.commit()
                report["synthetic_probe_removed"] = True
            except Exception:
                admin.connection.rollback()
                report["synthetic_probe_removed"] = False
        for db in reversed(opened):
            db.close()
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        (ROOT / "artifacts/m03-run.json").write_text(payload, encoding="utf-8")
        print(payload, end="", file=sys.stdout if report["status"] == "passed" else sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
