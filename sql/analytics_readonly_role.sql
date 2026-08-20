\set ON_ERROR_STOP on

SELECT format(
    'CREATE ROLE analyst_ro LOGIN PASSWORD %L',
    :'ro_password'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles
    WHERE rolname = 'analyst_ro'
)
\gexec

ALTER ROLE analyst_ro WITH
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS
    PASSWORD :'ro_password';

REVOKE ALL PRIVILEGES ON DATABASE pubg_analytics FROM analyst_ro;
GRANT CONNECT ON DATABASE pubg_analytics TO analyst_ro;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM analyst_ro;
REVOKE ALL ON SCHEMA analytics_ops FROM analyst_ro;
GRANT USAGE ON SCHEMA analytics_ops TO analyst_ro;

REVOKE ALL PRIVILEGES
ON ALL TABLES IN SCHEMA analytics_ops
FROM analyst_ro;

REVOKE ALL PRIVILEGES
ON ALL SEQUENCES IN SCHEMA analytics_ops
FROM analyst_ro;

REVOKE ALL PRIVILEGES
ON ALL FUNCTIONS IN SCHEMA analytics_ops
FROM analyst_ro;

GRANT SELECT ON analytics_ops.latest_environmental_hotspots TO analyst_ro;
GRANT SELECT ON analytics_ops.latest_pipeline_runs TO analyst_ro;
GRANT SELECT ON analytics_ops.quality_run_summary TO analyst_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE pubg_analytics IN SCHEMA analytics_ops
    REVOKE ALL PRIVILEGES ON TABLES FROM analyst_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE pubg_analytics IN SCHEMA analytics_ops
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM analyst_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE pubg_analytics IN SCHEMA analytics_ops
    REVOKE ALL PRIVILEGES ON FUNCTIONS FROM analyst_ro;
