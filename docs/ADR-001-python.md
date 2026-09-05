# ADR-001 - Elección de Python

## Estado

Aceptado para M01.

## Contexto

El equipo necesita implementar las validaciones del contrato de telemetría y sus pruebas automáticas de forma reproducible en distintos sistemas operativos. La solución también debe integrarse con PostgreSQL y permitir que el proyecto se amplíe en hitos posteriores.

## Decisión

El equipo utilizará Python 3 para validar el contrato y ejecutar las pruebas automáticas.

Se eligió Python porque su sintaxis facilita la creación y el mantenimiento del código. Es multiplataforma, versátil y cuenta con un ecosistema amplio de bibliotecas y herramientas. También ofrece soporte para trabajar con UUID, fechas, valores decimales y objetos JSON, además de facilitar la integración con bases de datos y API.

Para M01, la validación del contrato utilizará la biblioteca estándar de Python siempre que sea posible, evitando dependencias externas innecesarias.

## Consecuencias

- El mismo código de validación puede ejecutarse localmente y en la automatización del repositorio.
- Las pruebas pueden ejecutarse mediante la interfaz común `make verify`.
- El equipo debe mantener coordinadas las reglas implementadas en Python, la documentación y las restricciones de PostgreSQL.

## Alternativas consideradas

- **JavaScript o TypeScript:** son opciones multiplataforma, pero el equipo prefirió la sencillez de Python para las validaciones y pruebas iniciales.
- **Validar solamente en PostgreSQL:** protegería la persistencia, pero no permitiría rechazar todos los errores antes de intentar almacenar el evento.
