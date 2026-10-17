"""Postgres execution adapter for the application's existing bounded SQL vocabulary."""
from functools import lru_cache
import re
import sqlite3

from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def translate(query):
    query = query.strip().rstrip(';')
    if query.upper().startswith('PRAGMA '):
        return None
    if query.upper() == 'BEGIN IMMEDIATE':
        return 'SELECT pg_advisory_xact_lock(8247801984)'
    query = query.replace('expires_at REAL', 'expires_at DOUBLE PRECISION')
    query = query.replace("json_extract(data,'$.onboarded')=1", "(data::jsonb ->> 'onboarded')='true'")
    query = query.replace("JOIN json_each(editions.snapshot,'$.articles')",
                          "CROSS JOIN LATERAL jsonb_array_elements(editions.snapshot::jsonb -> 'articles') AS article_values(value)")
    query = query.replace('SELECT value FROM', 'SELECT value::text AS value FROM')
    query = query.replace('SELECT editions.id,value FROM', 'SELECT editions.id,value::text AS value FROM')
    query = re.sub(r"json_extract\(([\w.]+),'\$\.([\w]+)'\)", r"(\1::jsonb ->> '\2')", query)
    query = query.replace('MIN(first_observed,excluded.first_observed)', 'LEAST(story_clusters.first_observed,excluded.first_observed)')
    query = query.replace('MAX(last_observed,excluded.last_observed)', 'GREATEST(story_clusters.last_observed,excluded.last_observed)')
    if query.upper().startswith('INSERT OR IGNORE INTO '):
        query = re.sub(r'^INSERT OR IGNORE INTO ', 'INSERT INTO ', query, flags=re.I) + ' ON CONFLICT DO NOTHING'
    return re.sub(r"'(?:''|[^'])*'|\?", lambda m: '%s' if m[0] == '?' else m[0], query)


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return (Row(row) for row in self.cursor)


@lru_cache(maxsize=4)
def pool_for(url):
    if not url.startswith(('postgres://', 'postgresql://')):
        raise sqlite3.OperationalError('Configure a valid PostgreSQL DATABASE_URL.')
    try:
        psycopg.conninfo.conninfo_to_dict(url)
        return ConnectionPool(url, min_size=0, max_size=5, timeout=5, max_idle=60,
                              kwargs={'connect_timeout': 5, 'prepare_threshold': None, 'row_factory': dict_row,
                                      'sslmode': 'verify-full', 'sslrootcert': str(Path(__file__).resolve().parents[1] / 'certs' / 'prod-ca-2021.crt')}, open=True)
    except psycopg.Error:
        raise sqlite3.OperationalError('Cloud database configuration is invalid.') from None


class Connection:
    def __init__(self, url, schema='daily_mind', initialize=False):
        if not re.fullmatch(r'daily_mind(?:_qa_[0-9a-f]{32})?', schema):
            raise ValueError('Invalid application database schema.')
        self.pool = pool_for(url)
        self.connection = None
        try:
            self.connection = self.pool.getconn(timeout=5)
            self.connection.execute("SET LOCAL statement_timeout = '10s'")
            self.connection.execute("SET LOCAL lock_timeout = '5s'")
            self.connection.execute("SET LOCAL idle_in_transaction_session_timeout = '20s'")
            if initialize:
                self.connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            self.connection.execute(f'SET LOCAL search_path TO "{schema}", pg_catalog')
        except psycopg.Error:
            if self.connection:
                try:
                    self.connection.rollback()
                except psycopg.Error:
                    pass
                self.pool.putconn(self.connection)
            raise sqlite3.OperationalError('Cloud database temporarily unavailable.') from None

    def execute(self, query, parameters=()):
        query = translate(query)
        if query is None:
            return None
        try:
            return Cursor(self.connection.execute(query, parameters))
        except psycopg.Error:
            raise sqlite3.OperationalError('Cloud database operation failed. Please retry.') from None

    def executemany(self, query, parameters):
        try:
            cursor = self.connection.cursor()
            cursor.executemany(translate(query), parameters)
            return Cursor(cursor)
        except psycopg.Error:
            raise sqlite3.OperationalError('Cloud database operation failed. Please retry.') from None

    def executescript(self, script):
        for query in script.split(';'):
            if query.strip():
                self.execute(query)

    def commit(self):
        try:
            self.connection.commit()
        except psycopg.Error:
            raise sqlite3.OperationalError('Cloud database commit failed. Please retry.') from None

    def rollback(self):
        try:
            self.connection.rollback()
        except psycopg.Error:
            pass

    def close(self):
        self.pool.putconn(self.connection)
