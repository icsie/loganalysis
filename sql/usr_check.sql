\set ON_ERROR_STOP on

-- List fail/ok events for usernames seen in both logs.fail and logs.ok.
DROP VIEW IF EXISTS pg_temp.usr_check_events;

-- Combine detailed fail and ok events for usernames present in both tables.
CREATE TEMP VIEW usr_check_events AS
SELECT
    username.name,
    host(sourceip.addr) AS ip,
    'fail' AS event_type,
    fail.tried_at AS datetime
FROM logs.username AS username
JOIN logs.fail AS fail
    ON fail.uid = username.id
LEFT JOIN logs.sourceip AS sourceip
    ON sourceip.id = fail.sid
WHERE username.seen_in = B'00000011'

UNION ALL

SELECT
    username.name,
    host(sourceip.addr) AS ip,
    'ok' AS event_type,
    ok.tried_at AS datetime
FROM logs.username AS username
JOIN logs.ok AS ok
    ON ok.uid = username.id
LEFT JOIN logs.sourceip AS sourceip
    ON sourceip.id = ok.sid
WHERE username.seen_in = B'00000011';

-- Show each matching event with its type and timestamp.
SELECT name, ip, event_type, datetime
FROM usr_check_events
ORDER BY name, datetime, event_type;

-- Count matching events by username, IP, and event type.
SELECT name, ip, event_type, count(*) AS n
FROM usr_check_events
GROUP BY name, ip, event_type
ORDER BY name, ip, event_type;

-- Count ok events by username for IPs that also appear in fail events.
WITH fail_ips AS (
    SELECT DISTINCT sid
    FROM logs.fail
    WHERE sid IS NOT NULL
)
SELECT
    host(sourceip.addr) AS ip,
    username.name,
    count(*) AS n
FROM logs.ok AS ok
JOIN fail_ips
    ON fail_ips.sid = ok.sid
JOIN logs.sourceip AS sourceip
    ON sourceip.id = ok.sid
JOIN logs.username AS username
    ON username.id = ok.uid
GROUP BY sourceip.addr, username.name
ORDER BY sourceip.addr, username.name;

