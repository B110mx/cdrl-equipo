# ADR 007: Evolución compatible y estrategia de migración documental

## Estado

Aceptado para M07.

## Autoría técnica

- Abril Miranda Baltazar Varillas: contrato v3, fixtures e inicialización
  idempotente.
- Luis Bryan Rojas Rodriguez: lectura multiversión, migración repetible y
  rollback.
- Edwin Yahir Cruz Flores: verificación acumulada, cobertura y evidencia
  machine-readable.

## Contexto

El almacén contiene documentos v1 sin marcador, documentos v2 con
`schema_version: 2` y nuevos documentos v3. M07 debe introducir un cambio real
sin impedir que los consumidores existentes lean las versiones anteriores. Los
datos usados para la demostración son sintéticos.

## Decisión

Se adopta la estrategia **expandir, migrar y revertir** descrita técnicamente en
ADR-005:

1. El lector acepta y valida v1, v2 y v3 antes de habilitar productores v3.
2. v3 agrega `quality`, obligatorio y limitado a `good`, `uncertain` o
   `unknown`; la migración de v1/v2 utiliza `unknown` cuando no existe esa
   información.
3. La migración conserva identificadores, claves, fecha, métrica, valor, unidad,
   metadatos e instante de ingestión. Repetirla sobre v3 no vuelve a escribir el
   documento.
4. El rollback real elimina `quality` y restaura v2 o la forma v1 sin marcador.
   Repetirlo sobre la versión objetivo tampoco vuelve a escribir.
5. `make setup` carga esquemas y fixtures idempotentemente, pero no realiza una
   migración masiva. `make run` demuestra el cambio controlado y restaura el
   fixture v2 al terminar.

La transición se comprueba con un caso normal, dos límites, un fallo declarado
y rollback, todos ejecutados contra DynamoDB Local. `make verify` ejecuta además
la regresión acumulada M01–M07, comprueba ausencia de secretos y genera los
resultados machine-readable.

## Compatibilidad y límites

| Versión | Marcador | Cambio | Lectura durante transición |
| --- | --- | --- | --- |
| v1 | ausente o `1` | contrato legado | permitida |
| v2 | `2` | contrato previo | permitida |
| v3 | `3` | agrega `quality` | permitida |

- No se retiran v1/v2 mientras existan consumidores o documentos que los usen.
- Los esquemas son cerrados; un campo nuevo requiere otra versión.
- El reemplazo evita cambios de identidad, pero la implementación local no
  resuelve migradores concurrentes. Producción requiere condición de versión o
  bloqueo.
- Los fixtures permiten una demostración reproducible, pero no sustituyen un
  respaldo operativo independiente.

## Alternativa descartada

Se descartó migrar todos los documentos durante `make setup`. Aunque reduce
rápidamente la variedad de versiones, vuelve destructivo el arranque, dificulta
el rollback y puede romper consumidores que todavía esperan v1/v2.

## Consecuencias

La convivencia temporal aumenta la lógica de validación, pero mantiene
compatibilidad hacia atrás, permite repetir la migración sin corrupción y deja
una ruta de rollback probada. El retiro de versiones antiguas será una decisión
posterior respaldada por inventario, observabilidad y respaldo restaurable.
