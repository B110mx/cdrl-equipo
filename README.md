# CDRL — Base inicial del proyecto

Esta carpeta es la base común del proyecto **Cloud Data Reliability Lab (CDRL)** para la asignatura **Bases de datos en la nube**.

## Flujo de inicio

1. Descarga esta base desde Google Classroom.
2. Crea un repositorio GitHub propio para tu equipo; no trabajes sobre el repositorio del curso.
3. Copia el contenido de esta carpeta al repositorio del equipo.
4. Agrega únicamente a los integrantes del equipo, con un máximo de tres personas.
5. Ejecuta `make setup`, `make verify` y `make run`.
6. Completa el hito semanal y conserva evidencia técnica individual de tu contribución.

El lenguaje de la aplicación lo selecciona el equipo y debe documentarse en un ADR. La interfaz mínima común del repositorio es:

```text
make setup
make verify
make run
```

## Entornos

- AWS Academy Learner Lab es el entorno cloud oficial cuando el servicio esté habilitado.
- Docker Compose/PostgreSQL y el emulador local declarado por el equipo son el respaldo reproducible.
- No uses cuentas personales con facturación, ni subas credenciales, tokens o datos sensibles.

## Primera entrega

El hito M01 transforma esta base en un contrato de datos ejecutable: agrega el esquema relacional, migraciones idempotentes, seed sintético, pruebas, reporte y ADR. La base inicial solamente verifica la estructura de arranque; no es una solución terminada.

La implementación usa Python 3 y PostgreSQL 16. El contrato y sus decisiones se
documentan en `docs/M01-data-contract.md` y `docs/ADR-001-python.md`. El flujo reproducible es:

```text
make setup
make verify
make run
```

En el hito M01, `make setup` instalaba las dependencias en un entorno virtual `.venv`.
El verificador M01 (`scripts/verify_m01.py`) inicia PostgreSQL y ejecuta las pruebas
(`tests/test_telemetry.py` y `tests/test_integration.py`).
La integración repite dos veces la migración y el seed en un esquema temporal,
compara las tres filas completas y elimina ese esquema incluso si falla una prueba.
Una base inaccesible o una prueba omitida hace fallar la verificación.
El resultado se guarda en `artifacts/m01-verify.json` y la salida en
`artifacts/make-verify-output.txt`, también cuando hay fallos.
Las pruebas M01 se conservan como regresión; sus reportes históricos no sustituyen
la evidencia de M02.

## Segunda entrega: M02 (flujo actual)

```text
make setup
make verify
make run
```

En shells que soportan `&&`, también se puede ejecutar
`make setup && make verify && make run`. En PowerShell antiguo, ejecutar cada
comando y continuar únicamente si terminó sin errores.

- `make setup`: instala dependencias, inicia PostgreSQL y aplica las dos migraciones
  idempotentes, preservando las mediciones M01 al agregar la FK de dispositivos.
- `make verify`: ejecuta M01 y M02 contra esquemas temporales. Comprueba casos
  normales, vacíos, límites, el fallo declarado y reproducibilidad. Genera los
  reportes M02 incluso si hay fallos, que producen código de salida distinto de cero.
- `make run`: inicia los servicios, repite migraciones/semilla y ejecuta las tres
  consultas parametrizadas. Imprime JSON y guarda `artifacts/m02-run.json`.

El diseño y las decisiones están en `docs/ADR-001-relacional-model.md`.
Las pruebas M02 están en `tests/test_relational.py`, con los casos SQL adicionales
conservados en `artifacts/test_cases.sql`. La verificación no borra datos públicos.

Para cambiar los parámetros de la demostración, después de `make setup`:

```text
.venv/Scripts/python.exe scripts/run_m02.py --compose --device-id sensor-lab-03 --status inactive
```

En Linux/macOS sustituir el ejecutable por `.venv/bin/python`. También se admiten
`--start`, `--end` (ISO 8601 con zona horaria) y `--limit` (1–1000).
El intervalo incluye el inicio y excluye el fin. Los decimales del JSON son cadenas
para conservar precisión. La carga utiliza únicamente datos sintéticos.

Los scripts `migrate.py`, `run_m02.py` y `verify_m02.py` admiten omitir `--compose`
para usar una conexión PostgreSQL configurada mediante variables de entorno.
Eso no acredita que se haya utilizado AWS Academy: se debe ejecutar y comprobar
en el laboratorio si está habilitado, sin versionar secretos.

## Entrega de cada hito

Después de obtener el commit final, ejecutar otra vez `make verify`.
Para M02, el comando genera `evidence/m02-relational-model.json` con el SHA de ese checkout;
ese archivo generado es el que se adjunta en Classroom junto con el reporte.
La copia versionada conserva una ejecución anterior: un archivo no puede
contener literalmente el hash del commit que lo incluye sin cambiar ese hash.
No se debe crear otro commit sólo para incorporar el SHA generado.
GitHub Actions ejecuta setup/verify/run y conserva la evidencia regenerada en el
paquete `m02-verification`, junto con `m02-verify.json`, `m02-run.json`, la salida de
verificación y el fallo declarado. M01 mantiene sus archivos históricos aparte.

`source_dirty=true` identifica pruebas sobre cambios locales de código sin commit;
no deben presentarse como resultado de un checkout limpio. Los reportes/evidencias
generados se excluyen de ese indicador para evitar que su propia actualización
marque la ejecución como sucia. La evidencia de entrega se vuelve a generar después
del commit final, sin crear otro commit únicamente para actualizar su SHA.

Antes de entregar M02, confirmar que `week-02-final` apunta al SHA aprobado, que
setup/verify/run terminaron correctamente y que la evidencia corresponde a ese SHA.
La existencia del tag o un resultado M01 en verde no bastan para acreditar M02.

## Tercera entrega: M03 (roles y secretos)

M03 separa migración, escritura, lectura y operación mediante cuatro usuarios de
PostgreSQL. Sus nombres y contraseñas se reciben por variables de entorno;
`.env.example` contiene marcadores o valores sintéticos para desarrollo.

- `make setup` aplica migraciones y configura cada usuario con una sola membresía.
- `make verify` ejecuta la suite completa, las pruebas negativas de permisos y
  la revisión automática de patrones de secretos versionados.
- `make run` demuestra las cuatro conexiones y guarda `artifacts/m03-run.json`.

La matriz de permisos y la rotación están en `docs/ADR-002-roles-postgresql.md`.
El reporte se guarda en `artifacts/m03-verify.json` y la evidencia en
`evidence/m03-role-separation.json`. Los reportes no imprimen contraseñas.

En Classroom entrega el repositorio propio del equipo, el tag semanal solicitado, el SHA exacto y el reporte de `make verify`. El repositorio debe conservar el historial y la evidencia de participación técnica de cada integrante.
