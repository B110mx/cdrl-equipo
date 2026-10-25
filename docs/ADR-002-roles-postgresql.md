# ADR 002: Roles mínimos de PostgreSQL

**Estado:** Implementado

## Decisión

Se crean cuatro roles grupales sin inicio de sesión (`NOLOGIN`) para separar las
responsabilidades de la base de datos:

| Rol | Permisos mínimos |
| --- | --- |
| `cdrl_migrator` | `USAGE` y `CREATE` en el esquema actual para aplicar migraciones. |
| `cdrl_writer` | `INSERT` en `telemetry_measurements`. |
| `cdrl_reader` | `SELECT` en `devices` y `telemetry_measurements`. |
| `cdrl_operator` | `SELECT` únicamente en `cdrl_operational_summary`; no puede leer tablas de negocio. |

Ningún rol puede crear otros roles, crear bases de datos o ser superusuario.
La migración es repetible: crea cada rol solo si no existe y vuelve a aplicar los
permisos declarados. Los usuarios `cdrl_migrator_user`, `cdrl_writer_user`,
`cdrl_reader_user` y `cdrl_operator_user` se crean mediante variables de entorno
y reciben una sola membresía. El migrador es propietario de las tablas existentes
para poder aplicar cambios posteriores.

La vista `cdrl_operational_summary` expone solamente el total de mediciones y las
marcas de tiempo mínima, máxima y de última ingesta. No contiene identificadores,
métricas, valores, unidades ni metadata. Las pruebas usan conexiones reales y
comprueban operaciones permitidas y denegaciones: lector insertando, escritor
leyendo telemetría, operador leyendo directamente o modificando tablas, migrador
creando roles y acceso a un objeto futuro sin concesión explícita. Cada denegación
registra `status` y SQLSTATE `42501` en el reporte machine-readable.

La cobertura funcional de M03 incluye un caso normal con las cuatro conexiones,
dos límites inclusivos de temperatura (`-80` y `200`) y un fallo declarado:
`metric = NULL` debe producir SQLSTATE `23502`. El reporte machine-readable
clasifica estos casos como `normal`, `limits`, `declared_failure` y
`access_denied` para que puedan evaluarse automáticamente.

El configurador revoca primero las cuatro membresías conocidas de cada usuario y
después concede únicamente la que corresponde. Esto corrige configuraciones
anteriores y permite comprobar la separación efectiva.

`PUBLIC` no tiene privilegios sobre el esquema ni sobre tablas, secuencias o
funciones actuales. También se revocan los privilegios predeterminados sobre
objetos futuros creados tanto por el usuario que ejecuta las migraciones como bajo
`cdrl_migrator`; esto incluye funciones, que PostgreSQL normalmente permite ejecutar
a `PUBLIC`. Cada nueva migración debe conceder explícitamente el acceso mínimo necesario.

`make run` abre cuatro conexiones independientes. El migrador crea y elimina una
tabla de prueba, el escritor inserta una medición sintética, el lector recupera
esa medición y el operador consulta la vista operativa. Al terminar se elimina la medición
de demostración para que las ejecuciones repetidas conserven el mismo estado.

## Secretos y rotación

No se versionan contraseñas, tokens ni cadenas de conexión. PostgreSQL recibe la
configuración desde variables de entorno y `.env` está excluido por `.gitignore`.
Para rotar una credencial, genera una nueva fuera del repositorio y cambia la
variable correspondiente (`POSTGRES_MIGRATOR_PASSWORD`, `POSTGRES_WRITER_PASSWORD`,
`POSTGRES_READER_PASSWORD` o `POSTGRES_OPERATOR_PASSWORD`) en el entorno seguro.
Ejecuta `scripts/configure_roles.py --compose` con el usuario administrador; el
script aplica `ALTER ROLE` al usuario separado sin imprimir la contraseña. Reinicia
los clientes y revoca la credencial anterior cuando ya usen la nueva. Nunca
escribas el valor en SQL, documentación o reportes.

## Consecuencias

La separación reduce el impacto de una credencial comprometida y evita cambios
accidentales fuera de cada responsabilidad. A cambio, cada tabla nueva requiere
actualizar explícitamente sus permisos y mantener cuatro credenciales en el
entorno de despliegue.
