-- Local learning setup only.
-- Do not use local credentials in a shared or production environment.
--
-- Run from PowerShell in the repository root:
--   .\run_db_setup.ps1
--
-- The executing PostgreSQL role must be allowed to create roles and databases.
-- The application login is read from DB_USER and DB_PASSWORD in the environment.
-- This file uses psql commands (\getenv, \connect, and \gexec), so run it with psql.

\set ON_ERROR_STOP on
\getenv app_user DB_USER
\getenv app_password DB_PASSWORD
\connect postgres

-- Create or update the local application login; keep it non-admin.
SELECT format(
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM pg_catalog.pg_roles
            WHERE rolname = :'app_user'
        ) THEN
            'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
        ELSE
            'CREATE ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
    END,
    :'app_user',
    :'app_password'
)
\gexec

-- CREATE DATABASE has no IF NOT EXISTS form and cannot run in a transaction.
SELECT 'CREATE DATABASE netlogs'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_database
    WHERE datname = 'netlogs'
)
\gexec

-- The application can connect only when explicitly granted below.
-- This does not revoke PUBLIC connection rights on other databases in the cluster.
-- Avoid changing those shared database grants from this project bootstrap script.
REVOKE ALL PRIVILEGES ON DATABASE netlogs FROM PUBLIC, :"app_user";
GRANT CONNECT ON DATABASE netlogs TO :"app_user";

\connect netlogs

-- Match the SPEC's preferred schema lookup order.
ALTER DATABASE netlogs SET search_path TO logs, public;

CREATE SCHEMA IF NOT EXISTS logs;
GRANT USAGE, CREATE ON SCHEMA logs TO :"app_user";

-- Keep dataset tables out of public. Remove the default PUBLIC create grant,
-- then allow the application to use public for the import-history table only.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app_user";

CREATE TABLE IF NOT EXISTS public.import_history (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    table_name TEXT NOT NULL UNIQUE,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    import_status TEXT NOT NULL
);

REVOKE ALL PRIVILEGES ON TABLE public.import_history FROM PUBLIC, :"app_user";
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.import_history
    TO :"app_user";
GRANT USAGE, SELECT
    ON SEQUENCE public.import_history_id_seq
    TO :"app_user";
