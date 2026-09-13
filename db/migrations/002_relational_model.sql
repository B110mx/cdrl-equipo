BEGIN;

CREATE TABLE IF NOT EXISTS devices (
	device_id varchar(64) PRIMARY KEY,
	device_name varchar(100) NOT NULL CHECK (btrim(device_name) <> ''),
	status varchar(16) NOT NULL DEFAULT 'active'
		CHECK (status IN ('active', 'inactive')),
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	CONSTRAINT devices_device_id_format CHECK (
		device_id ~ '^[[:alnum:]_.-]+$'
	)
);

CREATE INDEX IF NOT EXISTS devices_status_idx
	ON devices (status);

-- Conserva las mediciones M01: registra sus dispositivos antes de validar la FK.
-- No reemplaza nombres ni estados de dispositivos que ya estén registrados.
INSERT INTO devices (device_id, device_name)
SELECT DISTINCT device_id, device_id
FROM telemetry_measurements
ON CONFLICT (device_id) DO NOTHING;

DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1
		FROM pg_constraint
		WHERE conname = 'telemetry_measurements_device_fk'
		  AND conrelid = 'telemetry_measurements'::regclass
	) THEN
		ALTER TABLE telemetry_measurements
			ADD CONSTRAINT telemetry_measurements_device_fk
			FOREIGN KEY (device_id)
			REFERENCES devices (device_id)
			ON UPDATE CASCADE
			ON DELETE RESTRICT;
	END IF;
END $$;

COMMIT;
