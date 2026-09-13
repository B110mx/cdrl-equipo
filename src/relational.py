"""DML y consultas de negocio M02; los valores nunca se concatenan al SQL."""
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def seed_database(connection):
    """Carga todos los seeds en orden, padres antes de hijos, en una transacción."""
    paths = sorted((ROOT / "db/seed").glob("*.sql"))
    if not paths:
        raise RuntimeError("No hay archivos de semilla")
    try:
        with connection.cursor() as cursor:
            for path in paths:
                cursor.execute(path.read_text(encoding="utf-8-sig"))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return [path.name for path in paths]


def _interval(start, end):
    for value in (start, end):
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("Las fechas deben incluir zona horaria")
    if start >= end:
        raise ValueError("El inicio debe ser anterior al fin")


def _rows(connection, query, parameters):
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        columns = [column.name for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def measurements_by_device(connection, device_id, start, end, limit=100):
    """Lecturas en [inicio, fin), ordenadas por fecha/UUID; límite de 1 a 1000.

    Un dispositivo inexistente o sin lecturas devuelve una lista vacía.
    """
    _interval(start, end)
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("Se requiere un identificador de dispositivo")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("El límite debe ser un entero de 1 a 1000")
    return _rows(connection, """
        SELECT event_id, device_id, recorded_at, metric, value, unit, metadata
        FROM telemetry_measurements
        WHERE device_id = %s AND recorded_at >= %s AND recorded_at < %s
        ORDER BY recorded_at, event_id
        LIMIT %s
    """, (device_id, start, end, limit))


def metric_summary(connection, device_id, start, end):
    """Resumen por métrica/unidad sin mezclar magnitudes físicas distintas."""
    _interval(start, end)
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("Se requiere un identificador de dispositivo")
    return _rows(connection, """
        SELECT device_id, metric, unit, COUNT(*) AS measurement_count,
               MIN(value) AS minimum, MAX(value) AS maximum, AVG(value) AS average
        FROM telemetry_measurements
        WHERE device_id = %s AND recorded_at >= %s AND recorded_at < %s
        GROUP BY device_id, metric, unit
        ORDER BY device_id, metric, unit
    """, (device_id, start, end))


def devices_by_status(connection, status):
    """Catálogo por estado con conteo histórico, incluidos dispositivos sin datos.

    'inactive' clasifica al dispositivo; el DDL no prohíbe nuevas mediciones.
    """
    if status not in ("active", "inactive"):
        raise ValueError("Estado permitido: active o inactive")
    return _rows(connection, """
        SELECT d.device_id, d.device_name, d.status,
               COUNT(t.event_id) AS measurement_count
        FROM devices AS d
        LEFT JOIN telemetry_measurements AS t ON t.device_id = d.device_id
        WHERE d.status = %s
        GROUP BY d.device_id, d.device_name, d.status
        ORDER BY d.device_id
    """, (status,))
