# ADR 008: Estrategia de Paginación, Índices y Rendimiento

## Estado
Aceptado (Semana 09)

## Contexto
El crecimiento del volumen de documentos requiere una estrategia de lectura eficiente que evite desbordamientos de memoria y timeouts. Se necesita implementar paginación estable, soportar inserciones concurrentes sin duplicar registros, y garantizar tiempos de respuesta aceptables (p50/p95) mediante índices adecuados.

## Decisión
1. **Paginación Estable (Cursor-based):** Se implementa paginacion por cursor (`LastEvaluatedKey`) en lugar de `offset/limit`. Esto garantiza un orden total estricto y previene que los registros se omitan o dupliquen si ocurren inserciones o eliminaciones entre llamadas.
2. **Desempate y Orden Total:** Se utiliza una clave compuesta (ej. `timestamp` + `id`) para desempatar registros creados en el mismo milisegundo, asegurando un orden determinista.
3. **Índices (GSI):** Se definieron Índices Secundarios Globales (GSIs) para soportar los patrones de acceso de lectura sin requerir escaneos completos de la tabla (Full Table Scan).
4. **Medición de Rendimiento (Benchmark):** Se estableció una línea base de rendimiento. Las optimizaciones se validan midiendo los percentiles p50 y p95 bajo carga sintética con calentamiento previo (warm-up) para mitigar el cold-start.

## Consecuencias
* **Positivas:** Lecturas predecibles, bajo consumo de memoria en la aplicación y tiempos de respuesta consistentes (p95 controlado).
* **Negativas:** La paginación por cursor impide saltar directamente a una página específica (ej. "Ir a la página 10"). Los índices adicionales incrementan ligeramente el costo de escritura y almacenamiento.