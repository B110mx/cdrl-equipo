# M01 — Plan de requisitos y evidencias

## Alcance

Este documento separa las evidencias de preparación de la base y las evidencias
de la entrega final M01. No se usarán credenciales, tokens, datos personales ni
cadenas de conexión reales.

## Evidencia A — Preparación de la base

| Requisito | Evidencia esperada | Estado |
| --- | --- | --- |
| Partir de `CDRL-base-2026.zip` | Historial Git con commit inicial | Completo |
| Repositorio propio del equipo | URL del remoto GitHub | Pendiente |
| Interfaz común | Salida de `make setup`, `make verify` y `make run` | Completo localmente; falta captura final consolidada |
| Respaldo reproducible | PostgreSQL y DynamoDB activos mediante Docker Compose | Completo localmente |
| Trabajo sin secretos | Revisión de archivos versionados y `.gitignore` | Pendiente de revisión final |

## Evidencia B — Entrega final M01

| Requisito | Implementación | Evidencia de entrega | Estado |
| --- | --- | --- | --- |
| Contrato de telemetría | Esquema y documentación del contrato | ADR o reporte en `docs/` | Pendiente |
| Base relacional compatible con cloud | PostgreSQL sin dependencias exclusivas del entorno local | Migraciones y reporte | Pendiente |
| Migraciones reproducibles | Scripts idempotentes en `db/migrations/` | Ejecución automática repetida | Pendiente |
| Seed reproducible | Datos sintéticos en `db/seed/` | Conteos y resultado verificable | Pendiente |
| Caso normal | Prueba automática | Resultado de `make verify` | Pendiente |
| Caso límite 1 | Prueba automática | Resultado de `make verify` | Pendiente |
| Caso límite 2 | Prueba automática | Resultado de `make verify` | Pendiente |
| Fallo declarado | Prueba automática que demuestre el rechazo esperado | Resultado de `make verify` | Pendiente |
| Resultado machine-readable | JSON versionable en `artifacts/` | Archivo JSON válido | Pendiente |
| Evidencia del hito | `evidence/m01-data-contract.json` completo | Archivo JSON válido | Pendiente |
| Reproducibilidad | `make setup && make verify && make run` | Salida final conservada | Pendiente |
| Entrega Git | Repositorio, tag y commit inmutables | URL, `week-01-final` y SHA exacto | Pendiente |

## Regla de cierre

El tag `week-01-final` solo se creará después de ejecutar todas las pruebas,
validar los JSON, comprobar que no existen secretos y confirmar que el árbol de
trabajo está limpio. El SHA registrado será el commit exacto apuntado por ese
tag.
