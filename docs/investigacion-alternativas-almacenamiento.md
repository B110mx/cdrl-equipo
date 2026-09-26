# Investigación y comparación de alternativas de almacenamiento

## Alcance

Este documento compara cuatro familias de almacenamiento solicitadas: Document Store, Graph Store, Column Store y Object Store. Se usan servicios de AWS como ejemplos concretos por ser el entorno contemplado por el proyecto; no se propone cambiar la implementación relacional actual.

## Carga CDRL usada para comparar

La unidad de información es el evento sintético de telemetría del contrato M01: `event_id`, `device_id`, `recorded_at`, `metric`, `value`, `unit` y `metadata`; `ingested_at` registra cuándo se almacena. La comparación considera estos patrones que ya aparecen en el modelo M02:

- Insertar y consultar un evento por su identificador único.
- Consultar eventos de un dispositivo dentro de un intervalo de tiempo, ordenados por fecha.
- Resumir cantidad, mínimo, máximo y promedio por métrica y unidad para un dispositivo e intervalo.
- Consultar dispositivos por estado incluyendo los que todavía no tienen eventos.

La relación presente en el modelo es dispositivo → eventos. No se asumen relaciones adicionales entre dispositivos. Por tanto, el beneficio de recorridos de varios saltos en Graph Store es una posibilidad para requisitos futuros, no una necesidad demostrada por el esquema actual.

**Interpretación de Column Store:** aquí se entiende como una base de datos wide-column o de familias de columnas, representada por Amazon Keyspaces. En otros contextos, “columnar” puede referirse a formatos/almacenes analíticos orientados a columnas, que son una alternativa distinta y requerirían otra comparación.

## Criterios

- **Consultas:** qué tipos de acceso y relaciones son naturales y qué consultas requieren índices, escaneos o componentes adicionales.
- **Escalabilidad:** cómo se amplían datos y capacidad, y qué decisiones de distribución quedan a cargo del diseño.
- **Consistencia:** qué garantías ofrecen las lecturas/escrituras y dónde hay límites.
- **Costo:** principales unidades que generan cobro y qué carga de trabajo habría que medir. No se comparan precios absolutos porque dependen de región, configuración y uso.
- **Fallos:** comportamiento o límites que pueden afectar disponibilidad o integridad; se distinguen hechos documentados e hipótesis que deben probarse.

## Matriz de comparación

| Criterio | Document Store (DynamoDB) | Graph Store (Neptune) | Column Store / wide-column (Keyspaces) | Object Store (S3) |
|---|---|---|---|---|
| **Consultas** | El evento puede modelarse como elemento y consultarse por clave. Para el patrón CDRL dispositivo + intervalo temporal, la clave de partición/ordenamiento debe permitir ese acceso; los resúmenes y consulta de dispositivos requieren índices u operaciones adicionales según el diseño. [D1] | Puede representar `Device -PRODUCED-> Event` y consultar eventos relacionados con un dispositivo; los recorridos adicionales solo aportan valor si existen relaciones CDRL más allá de esa relación directa. Admite Gremlin, openCypher y SPARQL. [G1] | Las tablas y claves deben diseñarse para los patrones: eventos por dispositivo/tiempo y, posiblemente, una tabla/materialización distinta para resúmenes. No asumir que el patrón de agregación queda resuelto por una sola consulta; validar restricciones de Keyspaces. [C1] | Los eventos podrían guardarse como objetos individuales o lotes, localizables por bucket/clave. Consultar rangos y calcular resúmenes sobre los eventos suele requerir organización por clave/prefijo o un servicio analítico adicional. [O1] |
| **Escalabilidad** | Distribuye datos por clave de partición y administra particiones automáticamente; una mala distribución de claves es un riesgo de diseño. [D2] | El almacenamiento administrado crece automáticamente; la capacidad de cómputo y el rendimiento deben dimensionarse y comprobarse para la carga elegida. [G2] | Servicio administrado sin servidores que escala tablas según el tráfico; validar límites/cuotas y comportamiento con la carga del equipo. [C1] | Permite almacenar objetos a gran escala y ofrece clases de almacenamiento para distintos patrones de acceso; la selección de clase afecta latencia y costo. [O1] |
| **Consistencia** | Las lecturas de tabla pueden ser eventualmente consistentes (predeterminado) o fuertemente consistentes; los índices globales no admiten lecturas fuertemente consistentes. [D3] | Neptune define semántica transaccional e aislamiento para cargas OLTP de grafos. [G3] | La consistencia depende de las garantías y niveles soportados por el servicio compatible con Cassandra; confirmar niveles admitidos por Keyspaces y el controlador en uso antes de fijar requisitos. [C2] | S3 ofrece consistencia fuerte de lectura tras escritura para objetos y operaciones PUT/DELETE; escrituras concurrentes sobre una clave no tienen bloqueo y no hay atomicidad entre varias claves. [O2] |
| **Costo** | Medir solicitudes de lectura/escritura, modo de capacidad, almacenamiento, índices y transferencia. Una lectura fuertemente consistente cuesta más que una eventualmente consistente. [D3][D4] | Comparar costo de cómputo/instancias, almacenamiento, E/S y respaldos con la carga prevista; el tamaño del clúster importa. [G2][G4] | Comparar solicitudes o capacidad aprovisionada, almacenamiento, transferencia y respaldos según modo y carga; contrastar con los precios de la región elegida. [C1][C3] | Medir GB-mes por clase, solicitudes, recuperación de archivo, transferencia y replicación. Hay varias clases y cargos, por lo que “más barato” depende del acceso. [O1][O3] |
| **Fallos y límites** | La disponibilidad administrada no elimina errores de diseño: una clave caliente o capacidad insuficiente puede limitar solicitudes; probar throttling y recuperación con carga representativa. La distribución depende de la clave. [D2] | Hay que probar pérdida de conexión, failover y recuperación con la configuración elegida; la documentación describe replicación de almacenamiento entre zonas, pero no sustituye una prueba del clúster. [G2] | Probar throttling, timeout y recuperación del cliente, además de particiones desbalanceadas. Son hipótesis operativas: el efecto depende del esquema, cuotas y configuración. | Versioning puede ayudar a recuperar versiones anteriores, pero no impide por sí mismo sobrescrituras concurrentes; tampoco hay transacción entre claves. Probar borrado, sobrescritura y acceso durante fallos de red. [O1][O2] |

## Hipótesis comprobables para el equipo

Estas pruebas permiten contrastar la matriz sin desplegar infraestructura de pago: usar la documentación para predecir el resultado y, si AWS Academy está habilitado, ejecutar una prueba pequeña dentro de sus límites. No crear recursos de pago con cuentas personales.

| Criterio | Hipótesis | Comprobación mínima |
|---|---|---|
| Consultas | Para cada alternativa se podrá resolver el acceso por `event_id` y el rango de eventos por dispositivo; el resumen por métrica/unidad y el conteo de dispositivos sin eventos pueden requerir estructuras o servicios adicionales. | Mapear los cuatro patrones CDRL anteriores a operaciones nativas y registrar índices, tablas/materializaciones, escaneos o servicios adicionales que exige cada una. |
| Escalabilidad | Al aumentar datos y solicitudes, la distribución de claves y los límites/cuotas influirán en latencia y throttling. | Repetir una carga sintética pequeña con dos distribuciones de clave y comparar latencia p95, errores y throughput. |
| Consistencia | Una escritura confirmada de un evento debe poder verificarse según las garantías documentadas por cada alternativa; las garantías pueden diferir entre un único evento y operaciones sobre varios objetos/elementos. | Insertar un evento sintético y leerlo inmediatamente por ID; intentar el mismo caso concurrentemente y registrar duplicados, conflicto o valor observado. Para Keyspaces, verificar primero niveles soportados. |
| Costo | El costo relativo cambiará con el patrón de solicitudes, retención, índices/almacenamiento y transferencia; no se puede establecer un ganador sin una carga y región comunes. | Introducir el mismo volumen estimado, frecuencia de acceso, retención y región en las páginas oficiales de precios/calculadoras y guardar supuestos junto al resultado. |
| Fallos | Un timeout, pérdida de conexión o exceso de solicitudes puede producir respuestas distintas según el servicio y la estrategia de reintentos. | Interrumpir o limitar una prueba local/sintética, registrar errores, reintentos, duplicados y tiempo de recuperación; no provocar fallos en recursos compartidos. |

## Fuentes

- **[D1]** AWS, [Particiones y distribución de datos en DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.Partitions.html).
- **[D2]** AWS, [Particiones y distribución de datos en DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.Partitions.html).
- **[D3]** AWS, [Consistencia de lectura en DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html).
- **[D4]** AWS, [Precios de DynamoDB](https://aws.amazon.com/dynamodb/pricing/).
- **[G1]** AWS, [Funciones de Amazon Neptune](https://docs.aws.amazon.com/neptune/latest/userguide/feature-overview.html) y [acceso con openCypher](https://docs.aws.amazon.com/neptune/latest/userguide/access-graph-opencypher.html).
- **[G2]** AWS, [Almacenamiento, confiabilidad y disponibilidad de Neptune](https://docs.aws.amazon.com/neptune/latest/userguide/feature-overview-storage.html).
- **[G3]** AWS, [Semántica transaccional de Neptune](https://docs.aws.amazon.com/neptune/latest/userguide/transactions.html).
- **[G4]** AWS, [Precios de Neptune](https://aws.amazon.com/neptune/pricing/).
- **[C1]** AWS, [Qué es Amazon Keyspaces](https://docs.aws.amazon.com/keyspaces/latest/devguide/what-is-keyspaces.html).
- **[C2]** AWS, [Consistencia de lectura en Amazon Keyspaces](https://docs.aws.amazon.com/keyspaces/latest/devguide/ReadConsistency.html). Confirmar ahí los niveles vigentes para el servicio y región utilizados.
- **[C3]** AWS, [Precios de Amazon Keyspaces](https://aws.amazon.com/keyspaces/pricing/).
- **[O1]** AWS, [Qué es Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html).
- **[O2]** AWS, [Modelo de consistencia de datos de S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel).
- **[O3]** AWS, [Precios de Amazon S3](https://aws.amazon.com/s3/pricing/).

## Conclusión

Este documento entrega la comparación cualitativa y sus bases para los patrones de eventos CDRL descritos arriba. No asigna pesos ni recomienda una alternativa: el integrante 2 puede consolidar la matriz ponderada y tomar la decisión en el ADR con los resultados de las pruebas del integrante 3.