-- 0001_foundation.sql
-- Cluster role for the application, request-context helpers, and the business time zone.

-- Roles are cluster-global, so creation is idempotent (many databases may be migrated on one cluster).
-- The login password is set separately (scripts/db.py bootstrap); this role owns nothing and is no superuser.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ze_app') THEN
    CREATE ROLE ze_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO ze_app;
-- Alembic creates its bookkeeping table before this file runs, so default privileges miss it;
-- /health reads it to report the applied schema version.
GRANT SELECT ON alembic_version TO ze_app;

-- Objects created later by the migration owner are usable by ze_app without per-migration GRANTs.
-- Evidence tables are tightened again in the final hardening migration.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ze_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO ze_app;

-- ---------------------------------------------------------------------------------------------
-- Request context. The API sets these with set_config(..., is_local => true) at the start of every
-- request transaction, so they cannot leak to another request on a pooled connection.
-- An unset context yields NULL, which every policy and check treats as "no access".
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION app_user_id() RETURNS bigint LANGUAGE sql STABLE
AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::bigint $$;

CREATE FUNCTION app_role() RETURNS text LANGUAGE sql STABLE
AS $$ SELECT NULLIF(current_setting('app.role', true), '') $$;

CREATE FUNCTION app_contractor_id() RETURNS bigint LANGUAGE sql STABLE
AS $$ SELECT NULLIF(current_setting('app.contractor_id', true), '')::bigint $$;

CREATE FUNCTION app_worker_id() RETURNS bigint LANGUAGE sql STABLE
AS $$ SELECT NULLIF(current_setting('app.worker_id', true), '')::bigint $$;

-- ---------------------------------------------------------------------------------------------
-- Business time. Statutory time rules (daylight, calibration dates, fitness dates) are evaluated
-- in India Standard Time against the record's own timestamp, never the session time zone.
--
-- IST is a fixed UTC+05:30 offset (India has had no DST since 1945), so an INTERVAL offset is exact
-- AND needs no IANA tz database: some PostgreSQL builds (including the embedded Windows build used
-- for development) ship without one and reject names like 'Asia/Kolkata'.
-- Trap: AT TIME ZONE '+05:30' (text) is POSIX-style and means UTC-05:30; the INTERVAL form is
-- east-positive and is the one used here. Both overloads below are IMMUTABLE (index-safe).
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION local_ts(ts timestamptz) RETURNS timestamp LANGUAGE sql IMMUTABLE
AS $$ SELECT ts AT TIME ZONE INTERVAL '5 hours 30 minutes' $$;

CREATE FUNCTION local_date(ts timestamptz) RETURNS date LANGUAGE sql IMMUTABLE
AS $$ SELECT (ts AT TIME ZONE INTERVAL '5 hours 30 minutes')::date $$;

-- Inverse: wall-clock time in India -> absolute instant (used by seeds, demos and tests).
CREATE FUNCTION from_local(local timestamp) RETURNS timestamptz LANGUAGE sql IMMUTABLE
AS $$ SELECT local AT TIME ZONE INTERVAL '5 hours 30 minutes' $$;
