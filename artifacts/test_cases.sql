-- Casos SQL adicionales. make verify los ejecuta en un esquema temporal M02.
-- Requiere las dos migraciones y semillas; el harness elimina sólo ese esquema.
DO $$
DECLARE
    constraint_seen text;
BEGIN
    -- Normal: dos lecturas sintéticas para el primer dispositivo.
    IF (SELECT count(*) FROM telemetry_measurements WHERE device_id='sensor-lab-01') <> 2 THEN
        RAISE EXCEPTION 'Caso normal incorrecto';
    END IF;
    -- Vacío: el dispositivo de reserva no tiene lecturas.
    IF EXISTS (SELECT 1 FROM telemetry_measurements WHERE device_id='sensor-lab-03') THEN
        RAISE EXCEPTION 'Caso vacio incorrecto';
    END IF;
    -- Límites inclusivos del contrato heredado de M01.
    INSERT INTO telemetry_measurements(event_id,device_id,recorded_at,metric,value,unit)
    VALUES
      ('00000000-0000-4000-8000-000000000080','sensor-lab-01','2026-09-03T00:00:00Z','temperature',-80,'celsius'),
      ('00000000-0000-4000-8000-000000000200','sensor-lab-01','2026-09-03T00:00:00Z','temperature',200,'celsius');
    -- Fallo declarado: debe rechazarse por la FK, no por otro error.
    BEGIN
        INSERT INTO telemetry_measurements(event_id,device_id,recorded_at,metric,value,unit)
        VALUES ('00000000-0000-4000-8000-000000000999','nonexistent-device',
                '2026-09-03T00:00:00Z','temperature',23.75,'celsius');
        RAISE EXCEPTION 'La FK acepto un dispositivo inexistente';
    EXCEPTION WHEN foreign_key_violation THEN
        GET STACKED DIAGNOSTICS constraint_seen = CONSTRAINT_NAME;
        IF constraint_seen <> 'telemetry_measurements_device_fk' THEN
            RAISE EXCEPTION 'Se rechazo por una FK diferente';
        END IF;
    END;
END $$;
