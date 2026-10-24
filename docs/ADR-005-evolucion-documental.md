# ADR 005: Evolución del esquema documental

## Estado
Aceptado

## Autoría técnica
Abril Miranda Baltazar Varillas: contrato v3, fixtures, inicialización
idempotente y evidencia de verificación documental.

## Contexto
M07 introduce v3 mientras existen documentos v1 (sin marcador o con
`schema_version: 1`) y v2. Sobrescribir esquemas anteriores o reescribir
documentos durante el arranque rompería consumidores y haría `make setup`
destructivo.

## Decisión
Se mantiene **convivencia versionada** en la tabla de eventos:

- Un evento que no contiene `schema_version` es v1 legado. El esquema v1 acepta
  esa forma histórica y también acepta `schema_version: 1`.
- Un evento v2 declara `schema_version: 2`; v3 declara `schema_version: 3`.
- El único cambio de contrato de v2 a v3 es ese marcador. El esquema v3 conserva
  exactamente los campos, tipos, obligatoriedad, restricciones y rangos de v2.
  No se agregan, eliminan ni renombran campos.
- `event_id`, `device_id`, `recorded_at`, `metric`, `value` y `unit` siguen
  requeridos. `metadata` e `ingested_at` siguen siendo opcionales en v1, v2 y
  v3. La aplicación normaliza la ausencia de `metadata` a `{}` antes de
  persistir.
- La versión determina el esquema: v1 permite marcador ausente o igual a 1;
  v2 requiere 2; v3 requiere 3. Los esquemas son cerrados
  (`additionalProperties: false`), así que futuros campos o cambios de tipo
  requieren otra versión contractual.
- Los fixtures son sintéticos: `document_data.json` representa v1 legado,
  `m07-document-data-transition-v2.json` representa el estado v2 de transición,
  `m06-document-data-v2.json` conserva la muestra previa v2 y
  `m07-document-data-v3.json` representa la versión nueva.
- `make setup` valida los esquemas v1/v2/v3 y ejecuta la inicialización
  idempotente de DynamoDB. Los documentos almacenados no se reescriben ni se
  eliminan al inicializar. Los fixtures se insertan idempotentemente; si una
  clave ya existe con contenido diferente, el arranque falla explícitamente y
  no sobrescribe ni borra el documento.

`scripts/init_document_store.py` valida los tres JSON Schema Draft 2020-12 antes
de conectarse, crea de forma idempotente las tablas e índices requeridos, espera
a que DynamoDB Local acepte conexiones y valida los fixtures de las versiones.
Una clave primaria o índice existente incompatible provoca un error explícito;
no se intenta cambiarlo ni se ignora el error.

La tabla de auditoría se configura con `DYNAMODB_AUDIT_TABLE` y tiene clave
primaria `audit_id` más `EventTimeIndex` (`event_id`,
`occurred_at_audit_id`). Docker Compose conserva los datos de DynamoDB Local en
el volumen nombrado `dynamodb_data`; `make setup` vuelve a comprobar tablas,
índices y fixtures sin sobrescribir documentos existentes. No ejecutar
`docker compose down -v` si se necesita conservar ese estado.

Los endpoints, región y nombres de tabla se configuran por variables de entorno
o `.env` local. `.env.example` contiene solo valores sintéticos de desarrollo;
no se deben copiar credenciales reales, tokens ni cadenas de conexión al
repositorio.

## Consecuencias

- Los documentos v1/v2 continúan existiendo y la evolución de esquema no exige
  convertirlos durante `make setup`.
- Productores v3 solo deben habilitarse cuando los consumidores puedan leer
  v1/v2/v3. La lógica de lectura dual y la conversión de documentos pertenecen
  al flujo M07 de migración, no a la inicialización de esquemas.
- Para rollback de productores, se puede volver a emitir v2 mientras se
  conserva un lector compatible con v3; no se degradan ni eliminan documentos
  v3. No desplegar un lector v2 exclusivo mientras haya documentos v3 que deba
  consumir.
- La retirada de v1 o v2 requiere confirmar que no quedan documentos de esa
  versión, que ningún productor ni consumidor los necesita, que existe respaldo
  restaurable y que una migración explícita fue verificada. No se retiran
  automáticamente al desplegar v3.
- El volumen local protege contra la recreación del contenedor, pero no es un
  respaldo independiente. La restauración de fixtures y la medición de
  recuperación se prueban por separado en la actividad.
