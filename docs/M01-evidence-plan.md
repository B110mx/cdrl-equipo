# M01 — Plan de requisitos y evidencias

## Alcance

Este documento separa las evidencias de preparación de la base y las evidencias
de la entrega final M01. No se usarán credenciales, tokens, datos personales ni
cadenas de conexión reales.

## Evidencia A — Preparación de la base

| Requisito | Evidencia esperada | Estado |
| --- | --- | --- |
| Partir de `CDRL-base-2026.zip` | Historial Git con commit inicial | Completo |
| Repositorio propio del equipo | <https://github.com/B110mx/cdrl-equipo> | Completo |
| Interfaz común | Salida de `make setup`, `make verify` y `make run` | Completo localmente; falta captura final consolidada |
| Respaldo reproducible | PostgreSQL y DynamoDB activos mediante Docker Compose | Completo localmente |
| Trabajo sin secretos | Revisión de archivos versionados y `.gitignore` | Sólo configuración sintética declarada; no versionar secretos reales |

## Evidencia B — Entrega final M01

| Requisito | Implementación | Evidencia de entrega | Estado |
| --- | --- | --- | --- |
| Contrato de telemetría | Esquema y documentación del contrato | ADR o reporte en `docs/` | Implementado; falta cierre Git |
| Base relacional compatible con cloud | PostgreSQL sin dependencias exclusivas del entorno local | Migraciones y reporte | Verificado en PostgreSQL 16 local |
| Migraciones reproducibles | Scripts idempotentes en `db/migrations/` | Ejecución automática repetida | Verificado con 2 ejecuciones |
| Seed reproducible | Datos sintéticos en `db/seed/` | Conteos y resultado verificable | Verificado con 2 ejecuciones y 3 filas estables |
| Caso normal | Prueba automática | Resultado de `make verify` | Implementado |
| Caso límite 1 | Prueba automática | Resultado de `make verify` | Implementado |
| Caso límite 2 | Prueba automática | Resultado de `make verify` | Implementado |
| Fallo declarado | Prueba automática que demuestre el rechazo esperado | Resultado de `make verify` | Implementado |
| Resultado machine-readable | JSON versionable en `artifacts/` | Archivo JSON válido | Generado automáticamente por `make verify` |
| Evidencia del hito | `evidence/m01-data-contract.json` | Archivo JSON válido | Se regenera con el SHA del checkout verificado |
| Reproducibilidad | `make setup && make verify && make run` | Salida final conservada | Verificado localmente: 31 pruebas aprobadas, ninguna omitida |
| Entrega Git | Repositorio, tag y commit inmutables | URL, `week-01-final` y SHA exacto | Pendiente |

## Regla de cierre

El tag `week-01-final` se creará sobre el commit final después de validar
las pruebas y GitHub Actions. Desde ese checkout se vuelve a ejecutar
`make verify`: el archivo de evidencia generado registra el SHA exacto
apuntado por el tag y se adjunta en Classroom junto con la salida de pruebas.
No se vuelve a confirmar ese archivo sólo para cambiar su propio SHA;
la copia versionada es histórica y la copia generada es la evidencia de entrega.
GitHub Actions también adjunta la evidencia generada a cada ejecución.
