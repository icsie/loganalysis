"""Enrich logs.sourceip (ORDER BY n DESC) using local City/Country/ASN MMDBs.

Default: preview only. Add --write to upsert public.ip_location.
Run from any directory; config/data paths are relative to this project.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from ipaddress import IPv4Address, ip_network
import json
from pathlib import Path

from dotenv import dotenv_values
import maxminddb
import psycopg

ROOT = Path(__file__).resolve().parents[1]
KINDS = ('GeoLite2-City', 'GeoLite2-Country', 'GeoLite2-ASN')


def connect():
    settings = dotenv_values(ROOT / '.env.local')
    for key in ('DB_NAME', 'DB_USER', 'DB_PASSWORD'):
        if not settings.get(key):
            raise ValueError(f'Missing {key} in .env.local')
    return psycopg.connect(
        host=settings.get('DB_HOST') or 'localhost',
        port=settings.get('DB_PORT') or '5432',
        dbname=settings['DB_NAME'], user=settings['DB_USER'],
        password=settings['DB_PASSWORD'], connect_timeout=10,
    )


def open_readers(stack, directory):
    readers = {}
    for path in sorted(directory.rglob('*.mmdb')):
        reader = stack.enter_context(maxminddb.open_database(str(path)))
        kind = reader.metadata().database_type
        if kind in KINDS:
            if kind not in readers or reader.metadata().build_epoch > readers[kind].metadata().build_epoch:
                readers[kind] = reader
    missing = set(KINDS) - readers.keys()
    if missing:
        raise ValueError('Missing MMDB: ' + ', '.join(sorted(missing)))
    return readers


def label(record):
    names = record.get('names', {})
    return names.get('zh-TW') or names.get('en') or names.get('zh-CN')


def lookup(ip, readers):
    city = readers[KINDS[0]].get(ip) or {}
    country_data = readers[KINDS[1]].get(ip) or {}
    asn, prefix = readers[KINDS[2]].get_with_prefix_len(ip)
    country = country_data.get('country', {}) | city.get('country', {})
    regions = city.get('subdivisions', [])
    loc = city.get('location', {})
    stamps = [datetime.fromtimestamp(readers[k].metadata().build_epoch, timezone.utc) for k in KINDS]
    return dict(
        ip=ip, country_code=country.get('iso_code'), country_name=label(country),
        region_name=label(regions[-1]) if regions else None,
        city_name=label(city.get('city', {})), latitude=loc.get('latitude'),
        longitude=loc.get('longitude'), accuracy_radius_km=loc.get('accuracy_radius'),
        time_zone=loc.get('time_zone'),
        lookup_status='found' if city or country_data else 'not_found',
        source='GeoLite2-City + GeoLite2-Country', source_updated_at=stamps[0],
        asn=asn.get('autonomous_system_number') if asn else None,
        asn_organization=asn.get('autonomous_system_organization') if asn else None,
        asn_network=str(ip_network(f'{ip}/{prefix}', strict=False)) if asn else None,
        asn_lookup_status='found' if asn else 'not_found',
        city_source_updated_at=stamps[0], country_source_updated_at=stamps[1],
        asn_source_updated_at=stamps[2],
    )


def upsert(cursor, row):
    columns = list(row)
    versions = ('city_source_updated_at', 'country_source_updated_at', 'asn_source_updated_at')
    freshness = ' AND '.join(
        f'(ip_location.{c} IS NULL OR ip_location.{c} <= EXCLUDED.{c})' for c in versions
    )
    query = (f'INSERT INTO public.ip_location ({", ".join(columns)}) '
             f'VALUES ({", ".join(["%s"] * len(columns))}) '
             'ON CONFLICT (ip) DO UPDATE SET '
             + ', '.join(f'{c} = EXCLUDED.{c}' for c in columns if c != 'ip')
             + ', updated_at = NOW() WHERE ' + freshness + ' RETURNING ip')
    cursor.execute(query, list(row.values()))
    return cursor.fetchone() is not None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Write results; otherwise preview only')
    parser.add_argument('--limit', type=int, help='Process only the top N IPv4 rows')
    parser.add_argument('--ip', help='Look up one IPv4 instead of reading logs.sourceip')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data' / 'ip_loc')
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error('--limit must be positive')
    if args.ip:
        try:
            args.ip = str(IPv4Address(args.ip))
        except ValueError:
            parser.error('--ip must be one valid IPv4 address without CIDR')
    processed = saved = 0
    try:
        with ExitStack() as stack:
            readers = open_readers(stack, args.data_dir)
            connection = None
            writer = None
            if not args.ip or args.write:
                connection = stack.enter_context(connect())
                writer = stack.enter_context(connection.cursor())
            if args.ip:
                rows = [(args.ip, None)]
            else:
                # Named cursor streams rows rather than loading the whole table.
                rows = stack.enter_context(connection.cursor(name='sourceip_geolocation'))
                rows.itersize = 500
                query = ('SELECT host(addr) AS ip, n FROM logs.sourceip '
                         'WHERE family(addr) = 4 AND masklen(addr) = 32 '
                         'ORDER BY n DESC NULLS LAST, addr')
                params = ()
                if args.limit:
                    query += ' LIMIT %s'
                    params = (args.limit,)
                rows.execute(query, params)
            for ip, n in rows:
                row = lookup(ip, readers)
                if args.write:
                    saved += int(upsert(writer, row))
                print(json.dumps({'n': n, **row}, ensure_ascii=False, default=str))
                processed += 1
        # Connection context commits only after every row succeeded.
        print(f'{"WRITE committed" if args.write else "PREVIEW only"}: processed={processed}, saved={saved}, skipped={processed-saved if args.write else 0}')
    except psycopg.errors.InsufficientPrivilege:
        parser.exit(1, 'Permission denied; changes rolled back. Ask the DBA for SELECT on logs.sourceip and SELECT/INSERT/UPDATE on public.ip_location.\n')
    except psycopg.Error as error:
        parser.exit(1, f'Database operation failed ({type(error).__name__}); changes rolled back. Check .env.local and table schema.\n')
    except (ValueError, OSError, maxminddb.InvalidDatabaseError) as error:
        parser.exit(1, f'Lookup failed ({type(error).__name__}); changes rolled back. Check IPv4 input and the three MMDB files.\n')


if __name__ == '__main__':
    main()
