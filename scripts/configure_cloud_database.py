"""Run in your own terminal: the database password is never echoed or printed."""
import argparse
import getpass
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values, set_key
import psycopg


def connection_url(password, host, project):
    if not re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', host):
        raise ValueError('Copy the exact Session pooler host from Supabase Connect.')
    if not re.fullmatch(r'[a-z0-9]+', project) or not password:
        raise ValueError('Project reference and a real database password are required.')
    return f'postgresql://postgres.{project}:{quote(password, safe="")}@{host}:5432/postgres?sslmode=verify-full'


def main():
    parser = argparse.ArgumentParser(description='Privately configure and verify Supabase Postgres.')
    parser.add_argument('--host', required=True, help='Session pooler host copied from Supabase Connect')
    args = parser.parse_args()
    if not sys.stdin.isatty():
        print('Run this command in your own interactive terminal. Do not send the password in chat.')
        return 2
    values = dotenv_values(ROOT / '.env')
    hostname = urlsplit(values.get('SUPABASE_URL', '')).hostname or ''
    if not hostname.endswith('.supabase.co'):
        print('Configure SUPABASE_URL in your local .env first.')
        return 2
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Supabase DATABASE password (hidden; not your account password or API key): ')
        url = connection_url(password, args.host, hostname.removesuffix('.supabase.co'))
        with psycopg.connect(url, connect_timeout=8, prepare_threshold=None, sslmode='verify-full',
                             sslrootcert=str(ROOT / 'backend/certs/prod-ca-2021.crt')) as connection:
            connection.execute('SELECT 1').fetchone()
        set_key(ROOT / '.env', 'DATABASE_URL', url, quote_mode='always')
        print('Database verified with TLS. DATABASE_URL saved privately. Local SQLite mode is unchanged.')
        return 0
    except (psycopg.Error, ValueError, getpass.GetPassWarning):
        print('Verification failed. Check the database password and Session pooler host in Supabase. No credentials were printed or saved.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
