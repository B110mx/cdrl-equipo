# ADR 002: Roles mínimos de PostgreSQL

**Estado:** Implementado

## Decisión

Se crean cuatro roles grupales sin inicio de sesión (`NOLOGIN`) para separar las
responsabilidades de la base de datos:

| Rol | Permisos mínimos |
| --- | --- |
| `cdrl_migrator` | `USAGE` y `CREATE` en el esquema actual para aplicar migraciones. |
| `cdrl_writer` | `INSERT` en `telemetry_measurements`. |
| `cdrl_reader` | `SELECT` en `devices`. |
| `cdrl_operator` | `SELECT` en `devices` y `telemetry_measurements`. |

Ningún rol puede crear otros roles, crear bases de datos o ser superusuario.
La migración es repetible: crea cada rol solo si no existe y vuelve a aplicar los
permisos declarados. Las pruebas también comprueban tres accesos rechazados:
lector insertando, escritor leyendo telemetría y operador actualizando dispositivos.

El usuario configurado por el entorno recibe membresía de los cuatro roles solo
para poder ejecutar las pruebas locales con `SET ROLE`. En un despliegue real,
cada aplicación debe usar un usuario separado y recibir únicamente la membresía
que necesita.

## Secretos y rotación

No se versionan contraseñas, tokens ni cadenas de conexión. PostgreSQL recibe la
configuración desde variables de entorno y `.env` está excluido por `.gitignore`.
Para rotar una credencial, genera una nueva fuera del repositorio, cambia
`POSTGRES_PASSWORD` en el entorno seguro, actualiza la contraseña del usuario
con `ALTER ROLE nombre_de_usuario PASSWORD 'nueva-credencial'` mediante un canal
administrativo y reinicia el servicio. Revoca la credencial anterior cuando los
clientes ya usen la nueva; nunca escribas el valor en SQL, documentación o
reportes.