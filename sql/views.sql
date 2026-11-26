\set ON_ERROR_STOP on

-- Run with: psql -U postgres -d netlogs -f sql/views.sql
CREATE OR REPLACE VIEW logs.attackers AS
WITH fail_only_ip_counts AS (
    SELECT
        fail.sid,
        count(*) AS n
    FROM logs.fail AS fail
    JOIN logs.username AS username
        ON username.id = fail.uid
    WHERE username.seen_in = B'00000001'
      AND fail.sid IS NOT NULL
    GROUP BY fail.sid
    -- Add HAVING count(*) > 5 here to filter low-frequency IPs.
)
SELECT
    sourceip.addr,
    fail_only_ip_counts.n,
    ip_location.latitude,
    ip_location.longitude,
    ip_location.country_name,
    ip_location.city_name,
    ip_location.asn,
    ip_location.asn_organization,
    ip_location.asn_network,
    ip_location.lookup_status
FROM fail_only_ip_counts
JOIN logs.sourceip AS sourceip
    ON sourceip.id = fail_only_ip_counts.sid
JOIN public.ip_location AS ip_location
    ON ip_location.ip = sourceip.addr
WHERE ip_location.lookup_status = 'found';

GRANT SELECT ON logs.attackers TO netla;
