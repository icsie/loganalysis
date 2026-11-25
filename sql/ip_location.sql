-- Run as table owner: psql -U postgres -d netlogs -v ON_ERROR_STOP=1 -f sql/ip_location.sql
BEGIN;
CREATE TABLE IF NOT EXISTS public.ip_location (
    ip INET PRIMARY KEY,
    country_code VARCHAR(2),
    country_name TEXT,
    region_name TEXT,
    city_name TEXT,
    latitude DOUBLE PRECISION CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION CHECK (longitude BETWEEN -180 AND 180),
    accuracy_radius_km INTEGER CHECK (accuracy_radius_km >= 0),
    time_zone TEXT,
    lookup_status TEXT NOT NULL CHECK (lookup_status IN ('found', 'not_found')),
    source TEXT NOT NULL,
    source_updated_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (masklen(ip) = CASE family(ip) WHEN 4 THEN 32 ELSE 128 END)
);
COMMENT ON TABLE public.ip_location IS
    'Per-IP geolocation cache; approximate network location, not attacker identity.';
-- City/Country/ASN cache upgrade; preserves existing records.
ALTER TABLE public.ip_location
    ADD COLUMN IF NOT EXISTS asn BIGINT CHECK (asn BETWEEN 0 AND 4294967295),
    ADD COLUMN IF NOT EXISTS asn_organization TEXT,
    ADD COLUMN IF NOT EXISTS asn_network CIDR,
    ADD COLUMN IF NOT EXISTS asn_lookup_status TEXT
        CHECK (asn_lookup_status IN ('found', 'not_found')),
    ADD COLUMN IF NOT EXISTS city_source_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS country_source_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS asn_source_updated_at TIMESTAMPTZ;

-- Application role configured for this project's netlogs database.
GRANT USAGE ON SCHEMA public TO netla;
GRANT SELECT, INSERT, UPDATE ON public.ip_location TO netla;

COMMIT;
