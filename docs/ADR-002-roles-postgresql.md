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
| `cdrl_operator` | `SELECT` en `devices` y `telemetry_measurements`. |

Ningún rol puede crear otros roles, crear bases de datos o ser superusuario.
La migración es repetible: crea cada rol solo si no existe y vuelve a aplicar los
permisos declarados. Los usuarios `cdrl_migrator_user`, `cdrl_writer_user`,
`cdrl_reader_user` y `cdrl_operator_user` se crean mediante variables de entorno
y reciben una sola membresía. El migrador es propietario de las tablas existentes
para poder aplicar cambios posteriores.

Las pruebas usan conexiones reales y comprueban operaciones permitidas y cuatro
denegaciones: lector insertando, escritor leyendo telemetría, operador actualizando
dispositivos y migrador creando roles.

La cobertura funcional de M03 incluye un caso normal con las cuatro conexiones,
dos límites inclusivos de temperatura (`-80` y `200`) y un fallo declarado:
`metric = NULL` debe producir SQLSTATE `23502`. El reporte machine-readable
clasifica estos casos como `normal`, `limits`, `declared_failure` y
`access_denied` para que puedan evaluarse automáticamente.

El configurador revoca primero las cuatro membresías conocidas de cada usuario y
después concede únicamente la que corresponde. Esto corrige configuraciones
anteriores y permite comprobar la separación efectiva.

`make run` abre cuatro conexiones independientes. El migrador crea y elimina una
tabla de prueba, el escritor inserta una medición sintética, el lector recupera
esa medición y el operador consulta conteos. Al terminar se elimina la medición
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
