# ADR 009: Acceso mínimo y auditoría por colección

**Estado:** Aceptado

## Contexto

DynamoDB Local reproduce las tablas y consultas del proyecto, pero no aplica
políticas de identidad AWS. Se requiere negar accesos no autorizados también en
desarrollo y mantener una política equivalente para AWS sin versionar
credenciales.

La decisión aplica **mínimo privilegio**: cada identidad puede ejecutar
únicamente las acciones declaradas para su rol y todo intento fuera de ese
alcance se rechaza antes de invocar el almacén.

## Decisión

La matriz de [src/access-control-policy.json](../src/access-control-policy.json)
es la única fuente de permisos para la fachada
`AuthorizedDocumentStore` y para
`scripts/render_dynamodb_iam_policy.py`.

| Rol | Eventos | Auditoría |
| --- | --- | --- |
| `reader` | leer | sin acceso |
| `writer` | leer y escribir | sin acceso |
| `administrator` | leer, escribir y administrar/eliminar documentos | sin acceso |
| `auditor` | sin acceso | consultar, sin modificar |
| `audit_writer` | sin acceso | anexar eventos, sin consultar |

`append_audit` es una operación distinta de administración: no concede
modificación ni consulta del registro. La fachada deniega antes de invocar el
almacén, y registra el resultado sin copiar payloads. Para evitar omisiones, los
consumidores deben recibir la fachada y no exponer directamente el cliente
DynamoDB. El rol y actor se obtienen del contexto confiable de autenticación,
nunca de campos enviados por el cliente. El `audit_sink` se ejecuta con la
identidad separada `audit_writer`;
así una solicitud denegada también puede dejar evidencia sin conceder al lector
ni al escritor acceso de modificación de auditoría. Las tareas de
inicialización y migración operan con permisos de infraestructura fuera de la
identidad de la aplicación.

El esquema [audit-event-schema.json](./audit-event-schema.json) permite solo
`actor`, `action`, `resource`, `result` y `occurred_at`. Actor y recurso son
identificadores técnicos restringidos; credenciales, tokens, valores del evento,
metadata y datos personales no forman parte del contrato. Los registros de
auditoría existentes conservan sus campos históricos y agregan estos campos.

Las políticas AWS se renderizan por rol con:

```powershell
$env:DYNAMODB_EVENTS_TABLE_ARN = "arn:aws:dynamodb:us-east-1:123456789012:table/cdrl-events"
$env:DYNAMODB_AUDIT_TABLE_ARN = "arn:aws:dynamodb:us-east-1:123456789012:table/cdrl-audit"
python scripts/render_dynamodb_iam_policy.py --role writer
```

Los ARN son ejemplos sintéticos. En el entorno AWS se proporcionan los ARN
reales mediante el entorno de ejecución; no se guardan claves de acceso ni
secretos. La política limita `Query` a las tablas/índices, `PutItem` y
`TransactWriteItems` a escritura, y `DeleteItem` a administración de eventos.
La acción IAM `PutItem` de auditoría debe usarse con la escritura condicional
que impide reutilizar `audit_id`; IAM no ofrece por sí solo semántica append-only
para una tabla DynamoDB.

Docker Compose usa `DYNAMODB_PORT`, `AWS_REGION` y los nombres de tablas
`DYNAMODB_*_TABLE`; la aplicación en host usa
`DYNAMODB_ENDPOINT_URL=http://localhost:8000`. DynamoDB Local recibe
credenciales ficticias solo por compatibilidad del SDK y no emula IAM; la
fachada es el control efectivo en local.

## Remediación y verificación

La remediación para el acceso directo no autorizado es imponer la fachada con
un rol explícito antes de cualquier operación. Las pruebas verifican que las
lecturas/escrituras/admin no permitidas levantan `AccessDeniedError`, no invocan
el almacén subyacente y producen un evento de denegación. También se valida un
caso normal, dos límites de separación de roles y un fallo declarado de
administración indebida. La salida reproducible se genera en `artifacts/` y
`evidence/`.

Cada denegación expone el código estable `ACCESS_DENIED` a la capa que registra
el resultado de la prueba, sin añadir mensajes internos ni secretos al evento
de auditoría. `scripts/run_m09.py` demuestra el abuso controlado mediante una
lectura directa con datos sintéticos y después aplica la remediación: el mismo
actor recibe únicamente `AuthorizedDocumentStore`, la operación se rechaza
antes de alcanzar el backend y la denegación queda auditada. Repetir la
demostración reutiliza identificadores de auditoría estables y nunca sobrescribe
un registro distinto.

La verificación final vive en `scripts/verify_m09.py`, se ejecuta desde
`make verify` y produce `artifacts/m09-verify.json`,
`artifacts/make-verify-output-m09.txt` y
`evidence/m09-nosql-security-audit.json`. El reporte conserva el código esperado
de cada prueba negativa, los comandos ejecutados, el SHA y la autoría técnica.

## Autoría técnica

- **Abril Miranda Baltazar Varillas:** matriz de permisos, contrato de auditoría,
  políticas IAM y fixtures sintéticos.
- **Luis Bryan Rojas Rodriguez:** fachada autorizada, persistencia idempotente,
  ejecución machine-readable y remediación.
- **Edwin Yahir Cruz Flores:** pruebas negativas, verificador, ADR y evidencia.

## Consecuencias

Los permisos se pueden revisar y probar fuera de AWS; AWS aplica el mismo
alcance a nivel de identidad y recurso. Añadir colecciones u operaciones exige
actualizar la matriz y su mapeo IAM. La aplicación debe inyectar un destino de
auditoría durable al construir la fachada.
