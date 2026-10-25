# Plan de correcciones para reevaluación

## M02 — modelo relacional

La corrección integra la verificación M02 en el flujo acumulado de `make verify`.
El verificador ejecuta las pruebas, genera `artifacts/m02-verify.json`, actualiza
`evidence/m02-relational-model.json` y exige los nombres reales de los tres
integrantes. La evidencia ya no se aprueba solamente porque el archivo exista.

Antes de solicitar la reevaluación se debe ejecutar con Docker disponible:

1. `make setup`
2. `make verify`
3. `make run`
4. Confirmar que M02 muestra estado `passed`, ninguna omisión y `source_dirty=false`
   después de crear el commit autorizado.

## M03 — roles y secretos

Correcciones a comprobar antes de aplicarlas:

- impedir que el rol operador lea directamente las mediciones de negocio;
- permitirle solo una vista operativa con contadores y marcas de tiempo;
- revocar permisos heredados de `PUBLIC`;
- configurar privilegios predeterminados para objetos futuros;
- ejecutar cada prueba negativa con una sesión del rol correspondiente;
- registrar resultado y código SQLSTATE de cada acceso denegado.

## M04 — comparación de almacenes

La calificación fue 7/8 y Classroom no incluyó una observación privada que
identifique la deducción. No se modificará el diseño por conjetura. Primero se
comparará la entrega contra todos los criterios y controles acumulados.

## M05 — almacén documental

Correcciones a comprobar antes de aplicarlas:

- normalizar todos los instantes a UTC antes de formar claves y rangos;
- probar que offsets distintos que representan el mismo instante producen el
  mismo resultado;
- incluir en `make verify` la regresión real de semanas anteriores;
- guardar en el reporte el SHA exacto y los comandos ejecutados.

## Criterio general

Cada corrección debe conservar la autoría existente, generar resultados
machine-readable y demostrar el comportamiento desde `make verify`; la mera
existencia de un archivo no cuenta como prueba.
