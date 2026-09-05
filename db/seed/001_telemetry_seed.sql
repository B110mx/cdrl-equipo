INSERT INTO telemetry_measurements
    (event_id, device_id, recorded_at, metric, value, unit, metadata)
VALUES
    ('018f47a0-79f2-7c19-bc7f-1a26d47e9123', 'sensor-lab-01', '2026-09-03T17:59:30Z', 'temperature', 23.75, 'celsius', '{"source":"synthetic"}'),
    ('018f47a0-79f2-7c19-bc7f-1a26d47e9124', 'sensor-lab-01', '2026-09-03T18:00:00Z', 'humidity', 45.20, 'percent', '{"source":"synthetic"}'),
    ('018f47a0-79f2-7c19-bc7f-1a26d47e9125', 'sensor-lab-02', '2026-09-03T18:00:30Z', 'battery_voltage', 12.60, 'volt', '{"source":"synthetic"}')
ON CONFLICT (event_id) DO UPDATE SET
    device_id = EXCLUDED.device_id,
    recorded_at = EXCLUDED.recorded_at,
    metric = EXCLUDED.metric,
    value = EXCLUDED.value,
    unit = EXCLUDED.unit,
    metadata = EXCLUDED.metadata;
