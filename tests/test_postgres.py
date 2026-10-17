"""Cloud tests use a disposable private schema; never the application's schema."""
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from backend.config import Settings
from backend.news.models import ProfileInput
from backend.news.postgres import Connection, Row, pool_for, translate
from backend.news.service import Newspaper
from backend.news.store import Store
from tests.test_newspaper import FixtureDiscovery


def test_parameter_translation_preserves_quoted_literals():
    assert translate("SELECT '?' AS marker WHERE id=?") == "SELECT '?' AS marker WHERE id=%s"
    assert translate("SELECT 'reader''s ?' WHERE id=?") == "SELECT 'reader''s ?' WHERE id=%s"


def test_sqlite_specific_queries_have_postgres_equivalents():
    sql = translate("SELECT value FROM editions JOIN json_each(editions.snapshot,'$.articles') WHERE json_extract(value,'$.id')=?")
    assert 'CROSS JOIN LATERAL jsonb_array_elements' in sql
    assert 'value::text AS value' in sql
    assert "value::jsonb ->> 'id'" in sql
    assert translate('INSERT OR IGNORE INTO articles VALUES(?,?)').endswith('ON CONFLICT DO NOTHING')
    assert translate('PRAGMA journal_mode=WAL') is None
    assert 'pg_advisory_xact_lock' in translate('BEGIN IMMEDIATE')
    assert 'DOUBLE PRECISION' in translate('CREATE TABLE leases(expires_at REAL NOT NULL)')
    assert "='true'" in translate("SELECT id FROM profiles WHERE json_extract(data,'$.onboarded')=1")


def test_row_supports_existing_mapping_and_position_access():
    row = Row({'id': 'a', 'value': 'b'})
    assert row[0] == row['id'] == 'a'
    assert row[1] == row['value'] == 'b'
    assert dict(row) == {'id': 'a', 'value': 'b'}


def test_cloud_backend_never_falls_back_to_temporary_sqlite(tmp_path):
    settings = Settings(_env_file=None, database_backend='postgres', database_url='', database_path=str(tmp_path/'must-not-create.sqlite3'))
    with pytest.raises(ValueError, match='refusing temporary SQLite fallback'):
        Newspaper(settings)
    assert not (tmp_path/'must-not-create.sqlite3').exists()


def test_invalid_schema_and_dsn_rejected_without_connection():
    with pytest.raises(ValueError):
        Connection('postgresql://invalid', schema='public; DROP SCHEMA public')
    with pytest.raises(sqlite3.OperationalError):
        pool_for('https://invalid')


def test_connection_failure_returns_generic_storage_error(monkeypatch):
    class OfflinePool:
        def getconn(self, **kwargs):
            import psycopg
            raise psycopg.OperationalError('TEST_ONLY_PRIVATE_PASSWORD must not appear in API errors')
    monkeypatch.setattr('backend.news.postgres.pool_for', lambda url: OfflinePool())
    with pytest.raises(sqlite3.OperationalError) as error:
        Connection('postgresql://test')
    assert str(error.value) == 'Cloud database temporarily unavailable.'


def test_configuration_helper_encodes_password_and_rejects_wrong_hosts():
    from scripts.configure_cloud_database import connection_url
    from urllib.parse import urlsplit, unquote
    password = 'TEST_ONLY p@ss:%/?#\'unicode'
    url = connection_url(password, 'aws-0-ap-southeast-1.pooler.supabase.com', 'testproject')
    parsed = urlsplit(url)
    assert unquote(parsed.password) == password
    assert parsed.hostname == 'aws-0-ap-southeast-1.pooler.supabase.com'
    assert parsed.username == 'postgres.testproject'
    assert password not in url
    with pytest.raises(ValueError):
        connection_url(password, 'aws-0-test.pooler.supabase.com.attacker.test', 'testproject')


@pytest.fixture
def pg_store(tmp_path):
    if os.getenv('RUN_POSTGRES_TESTS') != '1':
        pytest.skip('Opt-in real PostgreSQL integration; requires DATABASE_URL privately in .env')
    url = Settings().database_url.get_secret_value()
    if not url:
        pytest.fail('Configure DATABASE_URL privately before running cloud tests')
    schema = 'daily_mind_qa_' + uuid4().hex
    store = Store(str(tmp_path/'cache.sqlite3'), database_url=url, schema=schema)
    try:
        yield store
    finally:
        connection = pool_for(url).getconn()
        try:
            assert schema.startswith('daily_mind_qa_') and len(schema) == 46
            connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
            connection.commit()
        finally:
            pool_for(url).putconn(connection)


@pytest.mark.live
def test_postgres_durable_profiles_feedback_and_rollback(pg_store):
    reader = str(uuid4())
    pg_store.save_profile(reader, ProfileInput(topics={'science': 1}))
    restored = Store(pg_store.path, database_url=pg_store.database_url, schema=pg_store.schema)
    assert restored.profile(reader)['topics'] == {'science': 1}
    with pytest.raises(RuntimeError):
        with pg_store.connect() as db:
            db.execute('INSERT INTO profiles VALUES(?,?,?,?)', ('rollback-test', '{}', 'now', 'now'))
            raise RuntimeError('TEST rollback')
    with pg_store.connect() as db:
        assert db.execute('SELECT id FROM profiles WHERE id=?', ('rollback-test',)).fetchone() is None


@pytest.mark.live
def test_postgres_generation_lease_serializes_competing_workers(pg_store):
    reader = str(uuid4())
    now = 1792240000.123
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(pg_store.claim_generation, reader, '2026-10-17', str(uuid4()), now) for _ in range(2)]
        states = [f.result() for f in futures]
    assert sorted(states) == ['busy', 'claimed']


@pytest.mark.live
async def test_postgres_edition_story_feedback_and_account_persistence(pg_store):
    from backend.auth import ReaderAuth
    settings = Settings(_env_file=None, database_path=pg_store.path, story_semantic_enabled=False, daily_generation_enabled=False)
    paper = Newspaper(settings, store=pg_store, discovery=FixtureDiscovery())
    subject = str(uuid4())
    auth = ReaderAuth(settings, pg_store)
    reader = auth.mapped_reader(subject)
    pg_store.save_profile(reader, ProfileInput(topics={'science': 1, 'technology': 1}))
    edition = await paper.generate(reader)
    article = edition['articles'][0]
    assert pg_store.interact(reader, article['id'], 'liked')
    assert not pg_store.interact(reader, article['id'], 'liked')
    assert pg_store.interact(reader, article['id'], 'saved')
    assert pg_store.reading_list(reader)[0]['article']['id'] == article['id']
    assert pg_store.interact(reader, article['id'], 'liked', False)
    paper.stories.follow(reader, article['story_id'], True)
    assert paper.stories.detail(reader, article['story_id']).followed
    restored = Store(pg_store.path, database_url=pg_store.database_url, schema=pg_store.schema)
    assert ReaderAuth(settings, restored).mapped_reader(subject) == reader
    assert restored.edition(reader, edition['id']) == edition
    assert restored.onboarded_readers() == [reader]
    assert restored.cached_articles(__import__('backend.services.provenance', fromlist=['utc_now']).utc_now(), 7)
    second = await paper.generate(reader)
    assert second['id'] == edition['id'] and paper.discovery.calls == 1
    with pytest.raises(KeyError):
        restored.edition(str(uuid4()), edition['id'])
