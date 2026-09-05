# M01 - Contrato de datos de telemetría

El objetivo principal es definir la estructura y las reglas que deben cumplir los eventos de telemetría antes de almacenarse.

## ¿Qué es un evento de telemetría?

Es un registro que permite recopilar datos sobre lo que sucede en un sistema para posteriormente analizarlo, monitorearlo o detectar problemas.

## Ejemplo

```json
{
  "event_id": "018f47a0-79f2-7c19-bc7f-1a26d47e9123",
  "device_id": "sensor-lab-01",
  "recorded_at": "2026-09-03T17:59:30Z",
  "metric": "temperature",
  "value": 23.75,
  "unit": "celsius",
  "metadata": {
    "source": "synthetic"
  }
}
```

## Campos del contrato

| Campo | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `event_id` | UUID | Sí | Identificador único del evento y clave de idempotencia. |
| `device_id` | Texto, máximo 64 caracteres | Sí | Identificador del dispositivo que produjo la medición. |
| `recorded_at` | Fecha y hora con zona horaria | Sí | Momento en que se realizó la medición. |
| `metric` | Texto, máximo 32 caracteres | Sí | Tipo de medición registrada. |
| `value` | Decimal | Sí | Valor registrado por el dispositivo. |
| `unit` | Texto, máximo 16 caracteres | Sí | Unidad correspondiente a la métrica. |
| `metadata` | Objeto JSON | No | Información adicional. Su valor predeterminado es `{}`. |
| `ingested_at` | Fecha y hora con zona horaria | Automático | Momento en que PostgreSQL almacenó el evento. |

## Métricas, unidades y rangos

| Métrica | Unidad | Intervalo inclusivo |
| --- | --- | --- |
| `temperature` | `celsius` | -80 a 200 |
| `humidity` | `percent` | 0 a 100 |
| `battery_voltage` | `volt` | 0 a 1000 |

## Reglas de validación

1. `event_id` es obligatorio, debe ser un UUID válido y no puede repetirse.
2. `device_id` es obligatorio y admite entre 1 y 64 caracteres.
3. `device_id` sólo puede contener letras, números, puntos, guiones y guiones bajos.
4. `recorded_at` debe ser una fecha y hora válida con zona horaria.
5. `metric` debe ser una de las métricas permitidas.
6. `value` debe ser un número dentro del intervalo correspondiente a la métrica.
7. `unit` debe coincidir con la métrica.
8. No se permiten valores vacíos en los campos obligatorios.
9. Se permite que `recorded_at` esté exactamente cinco minutos en el futuro para tolerar pequeños desfases de reloj; un tiempo posterior debe rechazarse.
10. `metadata` debe ser un objeto JSON con un tamaño máximo de 2048 bytes.

## Reproducibilidad

La migración utiliza DDL condicional para poder ejecutarse más de una vez sin producir errores.

El seed utiliza `ON CONFLICT` para impedir que se dupliquen los eventos cuando se ejecuta repetidamente. Todos sus datos son sintéticos.

## Casos verificables

### Caso normal

Una temperatura con valor `23.75`, unidad `celsius` y fecha en UTC debe aceptarse.

### Caso límite 1

Las temperaturas con valores de `-80` y `200` grados Celsius deben aceptarse porque corresponden a los límites inclusivos definidos.

### Caso límite 2

Un evento con una fecha exactamente cinco minutos en el futuro debe aceptarse para tolerar un pequeño desfase en el reloj del dispositivo.

### Fallo declarado

Un evento con `event_id` vacío debe rechazarse porque el campo es obligatorio y debe contener un UUID válido.

## Limitaciones

- No se utilizan datos personales ni sensibles.
- No se utilizan credenciales reales ni cadenas de conexión.
- M01 no incluye una aplicación completa.
- Todavía no se implementa una API completa.
