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

`make setup` instala las dependencias en un entorno virtual `.venv`.
`make verify` inicia PostgreSQL y ejecuta las pruebas del integrante 3
(`tests/test_telemetry.py` y `tests/test_integration.py`).
La integración repite dos veces la migración y el seed en un esquema temporal,
compara las tres filas completas y elimina ese esquema incluso si falla una prueba.
Una base inaccesible o una prueba omitida hace fallar la verificación.
El resultado se guarda en `artifacts/m01-verify.json` y la salida en
`artifacts/make-verify-output.txt`, también cuando hay fallos.
`make run` deja los servicios de Docker Compose activos en segundo plano
y espera a que estén disponibles.

## Entrega de cada hito

Después de obtener el commit final, ejecutar otra vez `make verify`.
El comando genera `evidence/m01-data-contract.json` con el SHA de ese checkout;
ese archivo generado es el que se adjunta en Classroom junto con el reporte.
La copia versionada conserva una ejecución anterior: un archivo no puede
contener literalmente el hash del commit que lo incluye sin cambiar ese hash.
No se debe crear otro commit sólo para incorporar el SHA generado.
GitHub Actions conserva la evidencia regenerada como un artefacto descargable.

En Classroom entrega el repositorio propio del equipo, el tag semanal solicitado, el SHA exacto y el reporte de `make verify`. El repositorio debe conservar el historial y la evidencia de participación técnica de cada integrante.
