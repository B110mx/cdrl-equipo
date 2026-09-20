# ADR 002: Implementación de Control de Acceso Basado en Roles (RBAC) en PostgreSQL

## Estado
Aceptado

## Contexto
El sistema requiere acceso a la base de datos para distintas funciones operativas: ejecución de migraciones (DDL), ingesta de telemetría, y consulta de datos. Utilizar un superusuario único o el propietario de la base de datos para todas las conexiones de la aplicación incrementa exponencialmente el riesgo de seguridad. Un compromiso de las credenciales de la aplicación o una vulnerabilidad de inyección SQL podría resultar en la pérdida total, alteración masiva o exposición de la estructura de la base de datos. 

## Decisión
Se decidió implementar el Principio de Privilegio Mínimo (PoLP) mediante la creación de roles específicos en PostgreSQL, separando las responsabilidades de acceso:

1. **Rol de Migración (`migrator`):** Propietario de los esquemas. Es el único rol autorizado para ejecutar comandos DDL (`CREATE`, `ALTER`, `DROP`). No se utiliza en la ejecución normal de la aplicación.
2. **Rol de Escritura (`writer`):** Utilizado por los servicios de ingesta. Limitado estrictamente a permisos DML de `INSERT` (y `UPDATE` si la lógica de negocio lo requiere) sobre las tablas operativas. No puede alterar la estructura.
3. **Rol de Lectura (`reader`):** Utilizado por los servicios de consulta, tableros y análisis. Limitado exclusivamente a comandos `SELECT`. No puede modificar datos.
4. **Rol de Operación (`operator`):** Destinado a tareas de mantenimiento o administración delegada, con permisos acotados y sin privilegios de superusuario.

Las credenciales para estos roles se inyectan en la aplicación a través de variables de entorno, evitando quemar contraseñas en el código fuente.

## Consecuencias

### Positivas
* **Reducción del radio de impacto:** Si una credencial de lectura es comprometida, el atacante no puede alterar ni borrar la base de datos.
* **Prevención de errores humanos:** Protege contra sentencias `DROP` o `TRUNCATE` accidentales desde la aplicación.
* **Cumplimiento y Auditoría:** Facilita la trazabilidad de qué componente del sistema ejecuta qué acción.

### Negativas
* **Mayor complejidad operativa:** Requiere gestionar múltiples cadenas de conexión y variables de entorno en el despliegue.
* **Mantenimiento adicional:** Cualquier nueva tabla o vista requiere actualizar la asignación de permisos (`GRANT`) para los roles correspondientes.
