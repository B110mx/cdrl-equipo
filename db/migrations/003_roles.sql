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

-- El esquema se toma del search_path, también cuando se usan esquemas de prueba.
DO $$
DECLARE
    app_schema name := current_schema();
BEGIN
    EXECUTE format('GRANT USAGE, CREATE ON SCHEMA %I TO cdrl_migrator', app_schema);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO cdrl_writer, cdrl_reader, cdrl_operator', app_schema);
    EXECUTE format('GRANT INSERT ON telemetry_measurements TO cdrl_writer');
    EXECUTE format('GRANT SELECT ON devices TO cdrl_reader');
    EXECUTE format('GRANT SELECT ON devices, telemetry_measurements TO cdrl_operator');
END $$;

-- El usuario de Compose ejecuta las pruebas SET ROLE; no se guardan contraseñas.
GRANT cdrl_migrator, cdrl_writer, cdrl_reader, cdrl_operator TO CURRENT_USER;

COMMIT;