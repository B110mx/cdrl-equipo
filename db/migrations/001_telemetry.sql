BEGIN;

CREATE TABLE IF NOT EXISTS telemetry_measurements (
    event_id uuid PRIMARY KEY,
    device_id varchar(64) NOT NULL CHECK (device_id ~ '^[[:alnum:]_.-]+$'),
    recorded_at timestamptz NOT NULL,
    metric varchar(32) NOT NULL CHECK (metric IN ('temperature', 'humidity', 'battery_voltage')),
    value numeric NOT NULL,
    unit varchar(16) NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (
        jsonb_typeof(metadata) = 'object'
        AND octet_length(metadata::text) <= 2048
    ),
    ingested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT telemetry_metric_value_unit CHECK (
        (metric = 'temperature' AND unit = 'celsius' AND value BETWEEN -80 AND 200)
        OR (metric = 'humidity' AND unit = 'percent' AND value BETWEEN 0 AND 100)
        OR (metric = 'battery_voltage' AND unit = 'volt' AND value BETWEEN 0 AND 1000)
    )
);

CREATE INDEX IF NOT EXISTS telemetry_device_time_idx
    ON telemetry_measurements (device_id, recorded_at DESC);

COMMIT;
