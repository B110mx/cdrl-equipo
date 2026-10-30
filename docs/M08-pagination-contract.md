# M08: Contrato de paginación documental

## Alcance

Este contrato define la lectura paginada de los eventos de un dispositivo en
DynamoDB. No cambia el CRUD ni promete una instantánea del conjunto de datos.
Los documentos y fixtures usados para validarlo son sintéticos.

## Autoría técnica

Abril Miranda Baltazar Varillas: contrato de paginación, decisión de índice y
fixture sintético M08.

## Consulta e índice

- La consulta requiere un `device_id` y recorre los eventos de ese dispositivo.
- Se usa la clave primaria compuesta ya declarada para la tabla de eventos:
  `device_id` como partición y `recorded_at_event_id` como ordenación.
- `recorded_at_event_id` tiene el formato
  `<recorded_at-UTC-normalizado>#<event_id>`. La normalización UTC y el sufijo
  único dan un orden total y determinista, incluso cuando varios eventos tienen
  el mismo `recorded_at`.
- La consulta avanza en orden ascendente y usa el último valor evaluado como
  posición exclusiva de continuación. No usa `Scan`, ni un índice secundario
  global para esta consulta.
- La clave primaria existente satisface este patrón; no se agrega un índice
  redundante. `EventIdIndex`, `DeviceMetricTimeIndex` y `MetricUnitTimeIndex`
  conservan sus usos actuales.

## Tamaño y respuesta

- `page_size` es un entero entre 1 y 100, inclusivo; el valor predeterminado es
  25.
- La respuesta contiene `items` y `next_cursor`. `next_cursor` es nulo cuando
  no hay otra página.
- Una página puede estar vacía si no hay eventos para el dispositivo. Para una
  consulta válida sin resultados no hay cursor siguiente.
- No se filtran resultados después de aplicar el límite: el límite es el
  máximo de eventos devueltos en la página.

## Cursor

- El cursor es opaco para quien consume la API: un token Base64 URL-safe sin
  padding que representa JSON UTF-8.
- La carga tiene `version: 1`, el `device_id`, el `page_size` de la consulta y
  la clave exclusiva de continuación (`device_id` y
  `recorded_at_event_id`).
- El cursor solo se reutiliza con el mismo dispositivo y tamaño de página. Un
  token malformado, de versión desconocida, incompleto o incompatible con los
  parámetros de consulta se rechaza explícitamente; no se reinicia la lectura
  silenciosamente ni se interpreta el token como una clave parcial.
- El cursor no es una credencial ni contiene secretos. La API no debe tratarlo
  como autenticación o autorización.

## Inserciones y límites de consistencia

La paginación no congela el conjunto de resultados entre páginas. El cursor
representa una posición de orden, no una instantánea:

- Una inserción cuya clave de ordenación sea menor o igual a la posición
  exclusiva actual no aparecerá en las páginas siguientes de ese recorrido.
- Una inserción cuya clave sea mayor que esa posición puede aparecer en una
  página posterior, según el momento en que la consulta la observe.
- Si dos eventos tienen el mismo timestamp, el `event_id` decide a qué lado del
  cursor cae cada inserción.
- Una eliminación concurrente puede hacer que un evento ya esperado no
  aparezca; el contrato no ofrece aislamiento de instantánea ni garantiza
  visibilidad inmediata de escrituras.

Por lo tanto, un recorrido sin cambios en los datos devuelve cada evento una
sola vez y en orden total. Con escrituras concurrentes, la garantía es
posicional según la clave, no una instantánea inmutable.

## Fixture reproducible

`fixtures/m08-pagination.json` se genera junto con los fixtures existentes al
ejecutar `fixtures/generate_fixtures.py` (también lo hace `make setup`). Contiene
24 eventos v3 de prueba para un mismo dispositivo, grupos con timestamps
repetidos, un tamaño de página de 5 y dos eventos de inserción sintéticos:

- `before_cursor` ordena antes del primer evento del fixture.
- `after_cursor` comparte el timestamp de un evento que queda en la primera
  página y ordena después de él por `event_id`.

El fixture permite reproducir tanto empates entre páginas como los dos
resultados posicionales de una inserción entre páginas. No se carga
automáticamente en el almacén; el ejecutor de consultas puede cargarlo en una
tabla local de prueba sin modificar los datos de otros hitos.
