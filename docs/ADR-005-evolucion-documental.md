# ADR 005: Evolución del esquema documental

## Estado
Aceptado

## Contexto
M06 agrega una nueva versión del contrato de eventos mientras M05 ya tiene
documentos persistidos que no incluyen `schema_version`. Sobrescribir el
esquema anterior o reescribir todos los documentos durante el arranque
introduciría riesgo de incompatibilidad y haría que `make setup` dependiera de
una migración destructiva.

## Decisión
Se mantiene **convivencia versionada** en la tabla de eventos:

- Un evento que no contiene `schema_version` es v1 legado. El esquema v1 acepta
  esa forma histórica y también acepta `schema_version: 1`.
- Un evento v2 debe declarar `schema_version: 2`; el esquema v2 conserva las
  restricciones de campos y rangos de medición del contrato previo.
- Los documentos almacenados no se reescriben ni se eliminan al inicializar.
  El inicializador valida cada fixture con el esquema que corresponda y lo
  inserta idempotentemente.

`scripts/init_document_store.py` valida ambos JSON Schema Draft 2020-12 antes
de conectarse, crea de forma idempotente las tablas e índices requeridos, espera
a que DynamoDB Local acepte conexiones y comprueba las versiones de los
fixtures M05 y M06 (incluido un documento sintético v2). Una clave primaria o
índice existente incompatible provoca un error explícito; no se intenta
cambiarlo ni se ignora el error.

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

- v1 y v2 pueden coexistir sin una conversión masiva ni pérdida de datos.
- Cada versión conserva su propio contrato validable durante el arranque.
- El volumen local protege contra la recreación del contenedor, pero no es un
  respaldo independiente. La restauración de fixtures y la medición de
  recuperación se prueban por separado en la actividad.
- Una futura retirada de v1 requiere una decisión y una migración controlada;
  no se elimina automáticamente al desplegar v2.
