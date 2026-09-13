-- Primero se insertan los padres de las mediciones de 001_telemetry_seed.sql.
-- Todos los identificadores y nombres son sintéticos.
INSERT INTO devices (device_id, device_name, status)
VALUES
    ('sensor-lab-01', 'Sensor sintético de ambiente', 'active'),
    ('sensor-lab-02', 'Sensor sintético de batería', 'active'),
    ('sensor-lab-03', 'Sensor sintético de reserva sin mediciones', 'inactive')
ON CONFLICT (device_id) DO NOTHING;
