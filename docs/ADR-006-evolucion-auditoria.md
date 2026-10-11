# ADR 006: Estrategia de Evolución, Auditoría y Recuperación

## Estado
Aceptado (Semana 06)

## Contexto
El sistema en su Módulo 06 requiere manejar la evolución de la estructura de datos (esquemas antiguos vs. nuevos), implementar un registro de auditoría seguro y garantizar la recuperación ante fallas mediante un fixture sintético. Todo esto manteniendo la inmutabilidad de la infraestructura y evitando la fuga de credenciales.

## Decisión

1. **Evolución Documental (Convivencia de versiones):**
   Dado que utilizamos DynamoDB (base de datos NoSQL), se optó por una **estrategia de convivencia** en lugar de una migración forzada. Los documentos ahora incluyen un campo `schema_version`. El código de la aplicación (capa de lectura) se encarga de aplicar valores por defecto a los documentos `v1` para que cumplan con el contrato de `v2` en tiempo de ejecución. Esto garantiza cero tiempo de inactividad (Zero Downtime).

2. **Auditoría Estructurada y Segura:**
   Se implementó un decorador/middleware en las operaciones de escritura y consulta. Cada acción genera un registro que contiene: `action` (ej. CREATE, RECOVER), `timestamp`, `result` (SUCCESS/FAILED) y `technical_id`. 
   **Seguridad:** Antes de guardar la auditoría, una función de saneamiento limpia explícitamente cualquier campo llamado `password`, `token`, `secret` o `api_key`.

3. **Falla Controlada y Recuperación:**
   Se automatizó un procedimiento que simula una pérdida de datos (limpieza de tabla) y ejecuta un script de recuperación inyectando el archivo `fixtures/document_data.json`. Al finalizar, el script genera un archivo `artifacts/m06-run.json` (machine-readable) que documenta el tiempo de duración de la recuperación y el recuento total de registros recuperados.

## Consecuencias
* **Positivas:** Alta tolerancia a cambios de esquema futuros. Trazabilidad completa de operaciones críticas para auditorías de seguridad.
* **Negativas:** La lógica de la aplicación en Python se vuelve ligeramente más compleja al tener que interpretar múltiples versiones de esquemas de forma simultánea.