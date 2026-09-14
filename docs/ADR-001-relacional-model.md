# ADR 001: Diseño del Modelo Relacional Operativo CDRL

**Estado:** Implementado y sujeto a la verificación del checkout de entrega
**Fecha:** 2026-09-12

## Contexto
Se requiere diseñar el modelo relacional operativo para el sistema CDRL. El diseño debe garantizar la integridad de los datos mediante invariantes (restricciones/constraints) que rechacen información inválida a nivel de base de datos, asegurando la consistencia antes de que la información llegue a la aplicación.

## Decisión
1. Se establecieron llaves primarias (PK) y foráneas (FK) estrictas para mantener la integridad referencial.
2. Se implementaron restricciones `CHECK` sobre identificadores, nombres no vacíos, estados válidos y la combinación métrica/unidad/rango. El modelo registra telemetría, no montos ni “fechas negativas”.
3. Las migraciones usan `CREATE TABLE/INDEX IF NOT EXISTS` y comprueban la existencia de la FK antes de agregarla. No borran tablas para repetir la instalación.
4. Se conserva Python 3 con `psycopg2` y PostgreSQL 16. Las consultas separan el SQL de sus parámetros mediante `cursor.execute(sql, parámetros)`.

## Modelo e invariantes

La relación es **devices (1) → telemetry_measurements (N)**. Un dispositivo puede
tener cero mediciones; toda medición debe pertenecer a un dispositivo registrado.

| Tabla | Clave y campos | Reglas principales |
| --- | --- | --- |
| `devices` | `device_id varchar(64)` PK; `device_name varchar(100)`; `status varchar(16)`; `created_at timestamptz` | Identificador alfanumérico con punto, guion o guion bajo; nombre no vacío tras `btrim`; estado `active` o `inactive`; campos obligatorios. |
| `telemetry_measurements` | `event_id uuid` PK; `device_id` FK; `recorded_at timestamptz`; `metric`; `value numeric`; `unit`; `metadata jsonb`; `ingested_at timestamptz` | Contrato M01: datos obligatorios, metadata objeto de hasta 2048 bytes según representación SQL, y combinación métrica/unidad/rango válida. |

Se conservan los intervalos inclusivos M01: `temperature/celsius` de -80 a 200,
`humidity/percent` de 0 a 100 y `battery_voltage/volt` de 0 a 1000.
`telemetry_measurements_device_fk` usa `ON UPDATE CASCADE` para propagar cambios
del identificador y `ON DELETE RESTRICT` para impedir borrar dispositivos con
mediciones. El estado `inactive` es una clasificación: no prohíbe insertar lecturas.

Los índices son `telemetry_device_time_idx(device_id, recorded_at DESC)` para
consultas por dispositivo/fecha y `devices_status_idx(status)` para el catálogo.
Con tres dispositivos, el optimizador puede preferir un recorrido completo;
tener un índice no obliga a que PostgreSQL lo use en cada consulta.

## Migraciones, DML y conservación de datos

`scripts/migrate.py` aplica `001_telemetry.sql` y `002_relational_model.sql` en ese
orden. Antes de crear la FK, la segunda migración registra los dispositivos que
aparecen en mediciones M01. Usa el identificador como nombre inicial y no sustituye
los nombres o estados ya existentes. Así puede actualizar una base poblada.

`seed_database` ejecuta los archivos de `db/seed/` en orden dentro de una
transacción: primero `000_devices_seed.sql` y luego `001_telemetry_seed.sql`.
La semilla M02 agrega tres dispositivos sintéticos; el tercero, inactivo, no tiene
lecturas. La semilla M01 conserva sus tres mediciones de UUID fijo. Los dispositivos
existentes no se reemplazan; las mediciones con los UUID del seed se actualizan
con los valores sintéticos definidos. No se borran registros adicionales.
Repetir la carga conserva las filas completas, incluidos sus tiempos de ingesta.
Cada archivo de migración controla su propia transacción; un error posterior no
deshace las migraciones anteriores, y se puede reintentar tras corregirlo.

## Consultas parametrizadas y resultados

| Función en `src/relational.py` | Parámetros | Semántica |
| --- | --- | --- |
| `measurements_by_device` | Dispositivo, inicio, fin, límite | Intervalo `[inicio, fin)`, fechas con zona horaria, límite entero 1–1000; orden por fecha y UUID. |
| `metric_summary` | Dispositivo, inicio, fin | Cantidad, mínimo, máximo y promedio por métrica/unidad; no mezcla magnitudes distintas. |
| `devices_by_status` | `active` o `inactive` | `LEFT JOIN` y `COUNT(event_id)` para conservar dispositivos sin mediciones con conteo cero; conteo histórico, sin filtro de fecha. |

Un dispositivo inexistente o un intervalo sin lecturas produce `[]` en las dos
primeras consultas. Inicio igual o posterior al fin, fechas sin zona y límites
inválidos se rechazan. Los valores de parámetros nunca se interpolan en SQL.
El JSON expresa decimales como cadenas para conservar precisión y fechas en UTC.

## Pruebas reproducibles y fallo declarado

`make verify` ejecuta las pruebas M01 existentes, `tests/test_relational.py` y
`tests/test_verification.py` (controles contra falsos positivos y errores sensibles).
Cada prueba M02 usa su propio esquema aleatorio, que se elimina al terminar incluso
si falla. No se vacía el esquema público. La limpieza se verifica y se registra.
El archivo `artifacts/test_cases.sql` del equipo se conserva como conjunto SQL
adicional, ejecutado automáticamente dentro de uno de esos esquemas temporales.

| Caso | Comprobación |
| --- | --- |
| Normal | Dos lecturas de sensor-lab-01 y resumen coherente de temperatura/humedad. |
| Vacío | Dispositivo inexistente, dispositivo sin lecturas e intervalo sin resultados. |
| Límites | Inicio incluido y fin excluido, límites de filas 1 y 1000, extremos de las tres métricas. |
| Fallo declarado | Insertar una medición válida para `nonexistent-device`; debe producir `ForeignKeyViolation`, SQLSTATE `23503`, sobre `telemetry_measurements_device_fk`. |
| Adicionales | Inyección tratada como dato, unidad incorrecta, estados/nombres/PK/NOT NULL, borrado restringido, actualización en cascada, repetición y actualización desde M01. |

El fallo declarado es una **prueba aprobada cuando PostgreSQL rechaza la operación
esperada**; no se acepta cualquier excepción como prueba de integridad.
`make verify` termina con código distinto de cero si faltan casos obligatorios,
hay pruebas fallidas/omitidas, la base no responde o no se limpia un esquema.

## Reportes y trazabilidad

- `artifacts/m02-verify.json`: resultado global, casos individuales, cobertura,
  regresión M01 y conteo de esquemas temporales creados/eliminados.
- `artifacts/make-verify-output.txt`: salida de la verificación M02.
- `artifacts/failure_result.txt`: resultado observado del fallo declarado, generado
  por el verificador; no es un texto escrito a mano para simular una ejecución.
- `artifacts/m02-run.json`: salida de las consultas de `make run`.
- `evidence/m02-relational-model.json`: evidencia regenerada con SHA, entorno,
  resultados y rutas de los archivos anteriores de verificación.

Los reportes identifican el SHA base y `source_dirty`. Mientras haya cambios de
código sin commit, `source_dirty=true`: son pruebas locales, no una entrega final.
Tras publicar el commit autorizado hay que ejecutar el flujo desde ese checkout
limpio y descargar la evidencia regenerada. Un archivo versionado no puede contener
el hash del commit que lo incluye sin modificarlo; no se hacen commits sucesivos
solo para perseguir ese hash. El tag `week-02-final` debe apuntar al commit realmente
verificado, y su cambio requiere coordinación explícita con el equipo.

## Consecuencias
* **Positivas:** Los datos son consistentes desde la capa de persistencia. El sistema es robusto ante inserciones erróneas.
* **Negativas:** La inserción de datos requiere un orden estricto (por las dependencias de las llaves foráneas), lo que hace que los scripts de poblamiento (semillas) deban ser cuidadosos.

Se utiliza Docker Compose como respaldo reproducible; estos resultados no acreditan
un despliegue en AWS Academy. Si el laboratorio está habilitado, se debe configurar
PostgreSQL mediante variables de entorno y registrar la ejecución real allí.
Los scripts Python admiten conexión por entorno sin `--compose`; los comandos make
de este repositorio seleccionan el respaldo local. DynamoDB se conserva del proyecto
base, pero no forma parte del modelo relacional M02. No se incluyen personas,
credenciales reales ni cadenas de conexión en los datos o reportes. Los errores se
registran por tipo sin mensajes SQL sensibles. El desfase futuro de cinco minutos
sigue validándose en Python M01, no mediante un CHECK SQL dependiente del reloj.
