# ADR 001: Diseño del Modelo Relacional Operativo CDRL

**Estado:** Aceptado
**Fecha:** 2026-09-12

## Contexto
Se requiere diseñar el modelo relacional operativo para el sistema CDRL. El diseño debe garantizar la integridad de los datos mediante invariantes (restricciones/constraints) que rechacen información inválida a nivel de base de datos, asegurando la consistencia antes de que la información llegue a la aplicación.

## Decisión
1. Se establecieron llaves primarias (PK) y foráneas (FK) estrictas para mantener la integridad referencial.
2. Se implementaron restricciones `CHECK` para evitar valores ilógicos (ej. fechas negativas, montos menores a cero o estados inválidos).
3. Se garantizó la idempotencia en las migraciones DDL (ej. uso de `CREATE TABLE IF NOT EXISTS` o eliminación previa segura).

## Consecuencias
* **Positivas:** Los datos son consistentes desde la capa de persistencia. El sistema es robusto ante inserciones erróneas.
* **Negativas:** La inserción de datos requiere un orden estricto (por las dependencias de las llaves foráneas), lo que hace que los scripts de poblamiento (semillas) deban ser cuidadosos.