# ADR 007: Evolución Compatible y Estrategia de Migración

## Estado
Aceptado (Semana 07)

## Contexto
Se requiere introducir una nueva versión del esquema documental (v3) sin romper a los consumidores existentes de v1/v2, garantizando una migración idempotente y la capacidad de realizar un rollback seguro en caso de falla.

## Decisión
1. **Compatibilidad:** Los documentos antiguos mantienen su legibilidad. La capa de acceso a datos transforma los esquemas temporalmente o mediante un proceso batch (`document_migration.py`).
2. **Idempotencia:** Si la migración se ejecuta dos veces, el sistema verifica el contrato y no duplica ni corrompe los documentos ya migrados.
3. **Rollback:** Se implementó una estrategia de restauración usando los fixtures originales (`m07-document-data-transition-v2.json`) para revertir el estado de la base de datos si la migración falla.
4. **Retiro de versiones antiguas:** Las versiones previas se mantendrán hasta confirmar que no hay escrituras en esquemas antiguos durante un ciclo operativo completo.

## Consecuencias
* **Positivas:** Cero pérdida de datos y transiciones seguras.
* **Negativas:** Mayor complejidad temporal en el código de lectura al manejar múltiples esquemas de forma simultánea.