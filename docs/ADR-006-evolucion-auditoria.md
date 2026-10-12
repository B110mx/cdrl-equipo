# ADR 006: Auditoría y recuperación controlada

## Estado

Aceptado para M06.

## Contexto

La convivencia de documentos v1 y v2 está definida en ADR-005. M06 también
requiere demostrar una operación auditada sin secretos y recuperar un fixture
después de una falla controlada, con un resultado medible y reproducible.

## Decisión

Las operaciones auditadas registran únicamente identificadores técnicos,
instante UTC, nombre de la operación, resultado y nombres de campos modificados.
No copian valores del evento ni metadatos, por lo que contraseñas, tokens,
secretos o cadenas de conexión no forman parte del registro de auditoría.

La falla controlada elimina exclusivamente el fixture sintético v2. La
recuperación vuelve a insertarlo de forma idempotente y compara un SHA-256 del
documento esperado con el documento recuperado. El resultado incluye duración
en milisegundos y cantidad de registros recuperados en `artifacts/m06-run.json`.

Los instantes se normalizan a UTC antes de formar claves ordenables o límites de
consulta. Así, dos representaciones con zonas horarias distintas que describen
el mismo instante producen la misma clave y el mismo resultado de consulta.

## Alternativas descartadas

- Guardar el payload completo en la auditoría: facilita diagnóstico, pero puede
  copiar secretos o datos innecesarios y aumenta el costo de almacenamiento.
- Reconstruir toda la tabla para demostrar recuperación: amplía el impacto de la
  falla y no es necesario para probar el procedimiento con un fixture sintético.

## Consecuencias

- La auditoría es verificable sin exponer valores del evento.
- La recuperación es acotada, repetible y medible.
- La regresión acumulada detecta incompatibilidades con hitos anteriores.
