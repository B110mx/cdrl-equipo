# ADR-008 — Paginación estable y rendimiento documental

## Estado y autoría

Aceptado para M08 el 1 de noviembre de 2026.

- Abril Miranda Baltazar Varillas: contrato, clave de acceso y fixture sintético.
- Luis Bryan Rojas Rodriguez: API paginada, validación de cursor y benchmark.
- Edwin Yahir Cruz Flores: pruebas, verificación acumulada, ADR y evidencia.

## Contexto

La consulta operativa recupera eventos ordenados de un dispositivo. Materializar
la partición completa para devolver una página aumenta datos transferidos y
memoria conforme crece el historial. La decisión debe medirse en un entorno
reproducible y no convertirse en una afirmación de rendimiento de producción.

## Decisión

Se pagina con la clave primaria existente: `device_id` como partición y
`recorded_at_event_id` como ordenación. La segunda clave concatena el instante
UTC y el UUID, por lo que existe un orden total aun con timestamps repetidos.
No se crea un GSI redundante para esta consulta.

La API devuelve como máximo `page_size` eventos y un cursor Base64 URL-safe sin
padding. El cursor contiene versión, dispositivo, tamaño de página y la clave
exclusiva de continuación; es opaco, no es autenticación y se rechaza si está
malformado o se reutiliza con parámetros distintos. La consulta solicita un
elemento adicional para distinguir una página final llena sin producir un
cursor que lleve a una página vacía.

## Medición reproducible

`scripts/benchmark_m08.py` crea 240 eventos sintéticos deterministas en una
partición dedicada. Compara:

1. Línea base: consulta y materialización de los 240 documentos antes de
   recortar los primeros 25 en el cliente.
2. Alternativa elegida: consulta limitada que devuelve 25 y usa cursor.

Cada variante ejecuta cinco calentamientos excluidos y 40 repeticiones medidas
con `time.perf_counter_ns`. Los percentiles p50 y p95 usan *nearest-rank*. El
entorno, muestra, método, resultados y equivalencia de la primera página quedan
en `artifacts/m08-benchmark.json`. Los números son observaciones locales y no
una garantía de latencia en AWS o producción.

## Escala, consistencia, costo y fallos

- Escala: cada respuesta queda acotada a 1–100 documentos y el cursor permite
  avanzar sin conservar toda la partición en memoria.
- Consistencia: las pruebas usan lectura consistente, pero el cursor representa
  una posición, no una instantánea. Una inserción anterior no aparece después;
  una posterior puede aparecer. Una eliminación concurrente puede omitir un
  documento esperado.
- Costo: limitar la consulta reduce documentos materializados y transferidos;
  a cambio se lee un elemento de anticipación y cada página requiere otra
  solicitud. No se añade costo de escritura o almacenamiento por un GSI nuevo.
- Fallos: cursores alterados, incompletos, de otra versión, dispositivo o tamaño
  se rechazan explícitamente. No se reinicia silenciosamente desde el inicio.

## Alternativas descartadas

- `offset/limit`: DynamoDB no ofrece un offset estable y las inserciones cambian
  las posiciones lógicas.
- `Scan` con filtro: examina datos ajenos al dispositivo y no aprovecha la clave
  de partición.
- GSI adicional: duplica almacenamiento y costo de escritura sin mejorar este
  patrón, ya cubierto por la clave primaria.

## Consecuencias y límites

El recorrido sin escrituras concurrentes es ordenado y sin duplicados. No se
puede saltar directamente a una página arbitraria, el cursor no congela los
datos y los resultados del benchmark solo describen la muestra y el entorno
registrados. La decisión deberá reevaluarse con carga y métricas de AWS antes de
hacer afirmaciones sobre producción.
