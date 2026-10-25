BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cdrl_migrator') THEN
        CREATE ROLE cdrl_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cdrl_writer') THEN
        CREATE ROLE cdrl_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cdrl_reader') THEN
        CREATE ROLE cdrl_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cdrl_operator') THEN
        CREATE ROLE cdrl_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$;

CREATE OR REPLACE VIEW cdrl_operational_summary AS
SELECT
    count(*)::bigint AS measurement_count,
    min(recorded_at) AS earliest_recorded_at,
    max(recorded_at) AS latest_recorded_at,
    max(ingested_at) AS latest_ingested_at
FROM telemetry_measurements;

-- El esquema se toma del search_path, también cuando se usan esquemas de prueba.
DO $$
DECLARE
    app_schema name := current_schema();
    migration_owner name := current_user;
BEGIN
    -- PUBLIC no recibe acceso implícito al esquema ni a objetos actuales.
    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM PUBLIC', app_schema);
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM PUBLIC', app_schema);
    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM PUBLIC', app_schema);
    EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA %I FROM PUBLIC', app_schema);

    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM cdrl_migrator, cdrl_writer, cdrl_reader, cdrl_operator', app_schema);
    EXECUTE format('REVOKE ALL ON devices, telemetry_measurements, cdrl_operational_summary FROM cdrl_writer, cdrl_reader, cdrl_operator');
    EXECUTE format('GRANT USAGE, CREATE ON SCHEMA %I TO cdrl_migrator', app_schema);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO cdrl_writer, cdrl_reader, cdrl_operator', app_schema);
    EXECUTE format('GRANT INSERT ON telemetry_measurements TO cdrl_writer');
    EXECUTE format('GRANT SELECT ON devices, telemetry_measurements TO cdrl_reader');
    EXECUTE format('GRANT SELECT ON cdrl_operational_summary TO cdrl_operator');

    -- Los objetos futuros creados por el usuario de migración o por el rol migrador
    -- tampoco se exponen a PUBLIC. Esto cubre tanto la ejecución automatizada como
    -- una migración manual con SET ROLE.
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I REVOKE ALL ON TABLES FROM PUBLIC', migration_owner, app_schema);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM PUBLIC', migration_owner, app_schema);
    -- EXECUTE para funciones es un privilegio global predeterminado de PUBLIC;
    -- debe revocarse sin IN SCHEMA para que la regla sea efectiva.
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC', migration_owner);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE cdrl_migrator IN SCHEMA %I REVOKE ALL ON TABLES FROM PUBLIC', app_schema);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE cdrl_migrator IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM PUBLIC', app_schema);
    EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE cdrl_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC';
END $$;

COMMIT;
