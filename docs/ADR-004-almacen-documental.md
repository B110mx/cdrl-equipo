# ADR 004: Diseño del Almacén Documental de Telemetría

## Estado
Aceptado

## Contexto
El sistema requiere almacenar de forma persistente y estructurada los eventos de telemetría provenientes de los dispositivos, garantizando la integridad de los datos, previniendo duplicados e implementando un esquema estricto de validación. Además, las consultas requeridas por el negocio dictan la forma en que los datos deben ser indexados.

## Decisión
Se implementó el almacén documental utilizando **Amazon DynamoDB** (mediante emulación local en el entorno de desarrollo), adoptando las siguientes decisiones técnicas:

1. **Esquema de Datos (JSON Schema):** Se definió un esquema riguroso (`M05-event-document-schema.json`) basado en Draft 2020-12 para validar los eventos en la capa de aplicación antes de su persistencia. Campos requeridos incluyen `event_id` (UUID), `device_id`, `recorded_at`, `metric`, `value` y `unit`.
2. **Índices de Consulta:**
   * **Clave Primaria Compuesta:** Partición por `device_id` y ordenación por `recorded_at#event_id` para resolver consultas cronológicas por dispositivo de forma nativa.
   * **EventIdIndex (Índice Secundario Global):** Para recuperar eventos específicos en tiempo constante (O(1)) evitando escaneos de tabla (`Scan`).
   * **MetricUnitTimeIndex:** Partición por `metric#unit` y ordenación por `recorded_at#event_id` para generar reportes analíticos agregados.
3. **Idempotencia y Prevención de Duplicados:** La operación de creación de eventos utiliza bloqueos distribuidos (locks) y transacciones atómicas (`TransactWriteItems`) con condiciones (`attribute_not_exists`) para garantizar que un mismo `event_id` no se inserte dos veces, arrojando `DuplicateEventError` cuando detecta colisiones maliciosas, o respondiendo de manera idempotente si el payload es idéntico.

## Consecuencias
* **Positivas:** Las consultas son altamente eficientes gracias a la indexación directa. La base de datos no sufrirá de corrupción de datos gracias a la validación estricta del esquema.
* **Negativas:** La lógica transaccional de DynamoDB en la aplicación es ligeramente más compleja y la validación en código añade una pequeña sobrecarga de procesamiento antes del guardado.