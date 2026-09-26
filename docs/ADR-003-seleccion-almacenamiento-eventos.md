# ADR-003 — Selección de almacenamiento para eventos CDRL

**Estado:** Propuesto; pendiente de contrastar con las pruebas M04

**Autoría técnica:** Luis Bryan Rojas Rodriguez (Integrante 2)

**Fecha:** 26 de septiembre de 2026

## Contexto

CDRL necesita seleccionar una familia de almacenamiento para sus eventos de
telemetría. La investigación de M04 compara Document Store (DynamoDB), Graph
Store (Neptune), Column Store entendido como *wide-column* (Keyspaces) y Object
Store (S3). La decisión se limita al almacenamiento operativo principal; no
elimina PostgreSQL de los hitos anteriores ni impide usar S3 como archivo en el
futuro.

Los patrones prioritarios son: escritura idempotente por `event_id`, consulta
por evento, rango temporal por dispositivo, resúmenes por métrica y consulta de
dispositivos sin eventos. No existe por ahora un requisito demostrado de
recorridos de relaciones de varios saltos.

## Método de decisión

Cada alternativa recibe una puntuación de 1 a 5: 1 significa ajuste muy bajo y
5 ajuste muy alto para CDRL. Los pesos suman 100 %. La puntuación total se
calcula como `suma(peso × puntuación) / 100`. Los valores son hipótesis de diseño
basadas en la investigación del integrante 1; las pruebas del integrante 3
deberán confirmarlos o motivar una revisión antes de aceptar este ADR.

| Criterio | Peso | Razón del peso |
| --- | ---: | --- |
| Consultas | 30 % | Los cuatro patrones de acceso CDRL deben resolverse sin escaneos sistemáticos ni una plataforma analítica adicional. |
| Escalabilidad | 20 % | El volumen y la tasa de eventos pueden crecer, y la distribución debe poder comprobarse con claves sintéticas. |
| Consistencia | 20 % | La idempotencia y la lectura posterior a escritura afectan la confiabilidad del evento. |
| Costo | 15 % | Debe medirse con la misma región, retención y carga; no se asume un precio absoluto. |
| Fallos | 15 % | Se valoran límites conocidos, recuperación y comportamiento observable ante timeout o throttling. |

## Matriz ponderada consolidada

| Alternativa | Consultas 30 % | Escala 20 % | Consistencia 20 % | Costo 15 % | Fallos 15 % | Total / 5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Document Store — DynamoDB | 4 | 5 | 4 | 4 | 4 | **4.20** |
| Graph Store — Neptune | 2 | 3 | 5 | 1 | 4 | **2.95** |
| Column Store — Keyspaces | 3 | 5 | 3 | 3 | 3 | **3.40** |
| Object Store — S3 | 2 | 5 | 3 | 5 | 4 | **3.55** |

El cálculo de DynamoDB, por ejemplo, es
`(4×30 + 5×20 + 4×20 + 4×15 + 4×15) / 100 = 4.20`.

### Trazabilidad de las puntuaciones

- **DynamoDB:** la clave compuesta permite modelar dispositivo y tiempo para
  consultas de rango [D1]; la distribución y el riesgo de claves calientes se
  apoyan en [D2]. La consistencia configurable y su diferencia en costo están
  documentadas en [D3] y los componentes cobrables en [D4]. Debe probarse que
  los resúmenes no introduzcan escaneos inaceptables.
- **Neptune:** obtiene puntuación alta en consistencia por sus transacciones
  [G3], pero baja en consultas y costo porque CDRL solo demuestra una relación
  directa dispositivo-evento y no recorridos de grafos [G1][G4]. El failover y
  la capacidad elegida siguen siendo hipótesis que deben medirse [G2].
- **Keyspaces:** favorece escala administrada [C1], pero obliga a diseñar tablas
  según cada patrón y a confirmar niveles de consistencia soportados [C2]. Su
  costo se mantiene neutral hasta medir solicitudes, capacidad y almacenamiento
  bajo los mismos supuestos [C3].
- **S3:** destaca en escala y costo potencial [O1][O3], pero consultar rangos y
  producir resúmenes necesita organización por claves o servicios adicionales.
  La consistencia es fuerte por objeto, no una transacción entre varios objetos
  [O2]; el versionado mitiga borrados o sobrescrituras, sujeto a validación [O4].

Las etiquetas `[D1]` a `[O4]` corresponden a las fuentes oficiales enumeradas en
`docs/investigacion-alternativas-almacenamiento.md`. Las hipótesis de latencia,
throttling, concurrencia y costo deben enlazarse con el resultado machine-readable
de M04 cuando el integrante 3 lo genere.

## Decisión

Seleccionar **Document Store mediante DynamoDB** como alternativa principal para
los eventos CDRL. El diseño candidato usará `device_id` como base de la clave de
partición y `recorded_at#event_id` como clave de ordenación, con una estructura
adicional para resolver la consulta directa por `event_id`. La forma exacta de
esa estructura queda sujeta a las pruebas: puede ser un índice o un elemento de
mapeo, pero debe evitar duplicados y registrar su costo.

La decisión se justifica porque DynamoDB ofrece el mejor equilibrio ponderado:
las consultas operativas dominantes pueden expresarse con claves, escala sin
administrar servidores, permite escoger consistencia fuerte cuando sea necesaria
y cobra según capacidad/solicitudes medibles. Sus fallos previsibles —clave
caliente, throttling, timeout y reintentos— pueden reproducirse con fixtures
sintéticos y requieren idempotencia mediante `event_id`.

## Alternativa descartada

Se descarta **Neptune como almacén operativo principal**. Aunque sus transacciones
y recorridos son valiosos para grafos conectados, el modelo CDRL actual solo
presenta la relación directa dispositivo-evento. Adoptarlo ahora añadiría costo
y complejidad sin una consulta de varios saltos que lo justifique. Esta decisión
se revisará si aparecen relaciones entre dispositivos, ubicaciones, incidentes o
dependencias que deban recorrerse como grafo.

S3 no se descarta como complemento: puede evaluarse posteriormente para archivo
de bajo costo o análisis por lotes, pero no sustituye por sí solo las consultas
operativas seleccionadas.

## Consecuencias y validación pendiente

- El esquema dependerá de los patrones de consulta; añadir uno nuevo puede exigir
  un índice o una materialización adicional.
- La elección de partición debe distribuir la carga y evitar dispositivos
  excesivamente calientes.
- Los resúmenes pueden requerir agregados mantenidos o un flujo analítico; no se
  afirma que DynamoDB ejecute agregaciones equivalentes a SQL de forma nativa.
- El costo final debe recalcularse con igual región, volumen, retención y nivel de
  consistencia para las cuatro opciones.
- El ADR solo pasará a **Aceptado** si las pruebas M04 conservan el orden de la
  matriz o documentan y justifican cualquier cambio de puntuación.
