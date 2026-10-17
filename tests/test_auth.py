"""Auth fixtures are synthetic; no Supabase project, credentials or email are used."""
import asyncio
import json
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from fastapi import HTTPException

from backend.auth import ReaderAuth
from backend.config import Settings
from backend.main import create_app
from backend.news.models import ProfileInput
from backend.news.service import Newspaper
from tests.test_newspaper import FixtureDiscovery


class AuthFixture:
    def __init__(self, path, algorithm='RS256'):
        self.algorithm = algorithm
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048) if algorithm == 'RS256' else ec.generate_private_key(ec.SECP256R1())
        encoder = jwt.algorithms.RSAAlgorithm if algorithm == 'RS256' else jwt.algorithms.ECAlgorithm
        self.jwk = {**json.loads(encoder.to_jwk(self.private.public_key())), 'kid': 'test-key', 'alg': algorithm, 'use': 'sig'}
        self.settings = Settings(_env_file=None, database_path=str(path), daily_generation_enabled=False,
                                 story_semantic_enabled=False, supabase_auth_enabled=True,
                                 supabase_url='https://test-project.supabase.co', supabase_publishable_key='sb_publishable_TEST_ONLY')
        self.paper = Newspaper(self.settings, discovery=FixtureDiscovery())
        self.calls = 0
        self.failure = False
        self.auth = ReaderAuth(self.settings, self.paper.store, httpx.MockTransport(self.jwks))
        self.app = create_app(self.settings, newspaper=self.paper, auth_service=self.auth)

    def jwks(self, request):
        self.calls += 1
        assert str(request.url) == self.settings.supabase_url + '/auth/v1/.well-known/jwks.json'
        if self.failure:
            raise httpx.ConnectError('TEST ONLY offline')
        return httpx.Response(200, json={'keys': [self.jwk]})

    def token(self, subject=None, **changes):
        now = int(time.time())
        claims = {'sub': subject or str(uuid4()), 'iat': now, 'exp': now + 3600, 'iss': self.settings.supabase_url + '/auth/v1',
                  'aud': 'authenticated', 'role': 'authenticated', **changes}
        return jwt.encode(claims, self.private, algorithm=self.algorithm, headers={'kid': 'test-key'})

    def client(self):
        return httpx.AsyncClient(transport=httpx.ASGITransport(self.app), base_url='http://test')


@pytest.fixture
def auth_fixture(tmp_path):
    return AuthFixture(tmp_path / 'auth.sqlite3')


@pytest.mark.parametrize('algorithm', ['RS256', 'ES256'])
async def test_valid_signatures_and_persistent_mapping(tmp_path, algorithm):
    fixture = AuthFixture(tmp_path / 'auth.sqlite3', algorithm)
    subject = str(uuid4())
    headers = {'Authorization': 'Bearer ' + fixture.token(subject)}
    async with fixture.client() as client:
        one, two = await asyncio.gather(client.get('/api/profile', headers=headers), client.get('/api/profile', headers=headers))
        assert one.status_code == two.status_code == 200
        reader = one.json()['id']
        assert reader == two.json()['id'] and reader != subject
        assert fixture.calls == 1
        fixture.failure = True
        assert (await client.get('/api/auth/me', headers=headers)).json()['reader_id'] == reader
        assert fixture.calls == 1
    restarted = ReaderAuth(fixture.settings, fixture.paper.store)
    assert restarted.mapped_reader(subject) == reader


@pytest.mark.parametrize('changes', [
    {'aud': 'other'}, {'iss': 'https://attacker.invalid/auth/v1'}, {'exp': 1}, {'iat': 9999999999},
    {'nbf': 9999999999}, {'sub': 'invalid'}, {'role': 'service_role'}, {'role': 'anon'}, {'is_anonymous': True},
    {'exp': None}, {'aud': None},
])
async def test_reject_invalid_claims_without_guest_fallback(auth_fixture, changes):
    async with auth_fixture.client() as client:
        response = await client.get('/api/profile', headers={'Authorization': 'Bearer ' + auth_fixture.token(**changes), 'X-Reader-ID': str(uuid4())})
        assert response.status_code == 401


async def test_forged_missing_algorithm_and_unknown_key(auth_fixture):
    fixture = auth_fixture
    bad_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(fixture.token(), options={'verify_signature': False})
    tokens = ['invalid', jwt.encode(claims, '', algorithm='none'), jwt.encode(claims, 'TEST_ONLY_' * 6, algorithm='HS256', headers={'kid': 'test-key'}),
              jwt.encode(claims, bad_key, algorithm='RS256', headers={'kid': 'test-key'}),
              jwt.encode(claims, fixture.private, algorithm='RS256', headers={'kid': 'unknown'})]
    async with fixture.client() as client:
        for token in tokens:
            response = await client.get('/api/profile', headers={'Authorization': 'Bearer ' + token})
            assert response.status_code == 401
        assert fixture.calls == 1
        assert (await client.get('/api/profile', headers={'Authorization': 'Basic invalid'})).status_code == 401


async def test_network_failure_no_guest_downgrade_and_bounded_retry(auth_fixture):
    fixture = auth_fixture
    fixture.failure = True
    async with fixture.client() as client:
        for _ in range(3):
            response = await client.get('/api/profile', headers={'Authorization': 'Bearer ' + fixture.token(), 'X-Reader-ID': str(uuid4())})
            assert response.status_code == 503
        assert fixture.calls == 1
        assert (await client.get('/api/profile', headers={'X-Reader-ID': str(uuid4())})).status_code == 200


async def test_key_rotation_and_expired_key_cache(auth_fixture):
    fixture = auth_fixture
    token = fixture.token()
    await fixture.auth.verify('Bearer ' + token)
    fixture.auth.expires = 0
    fixture.auth.next_fetch = 0
    fixture.failure = True
    with pytest.raises(HTTPException) as error:
        await fixture.auth.verify('Bearer ' + token)
    assert error.value.status_code == 503
    fixture.failure = False
    fixture.jwk['kid'] = 'rotated'
    fixture.auth.next_fetch = 0
    claims = jwt.decode(token, options={'verify_signature': False})
    rotated = jwt.encode(claims, fixture.private, algorithm='RS256', headers={'kid': 'rotated'})
    assert await fixture.auth.verify('Bearer ' + rotated) == claims['sub']


async def test_account_isolation_all_private_routes_and_guest_preservation(auth_fixture):
    fixture = auth_fixture
    a = {'Authorization': 'Bearer ' + fixture.token()}
    b = {'Authorization': 'Bearer ' + fixture.token()}
    guest = str(uuid4())
    fixture.paper.store.save_profile(guest, ProfileInput(locale='Guest preserved', topics={'science': 1}))
    async with fixture.client() as client:
        reader_a = (await client.get('/api/profile', headers=a)).json()['id']
        reader_b = (await client.get('/api/profile', headers=b)).json()['id']
        await client.put('/api/profile', headers=a, json={'locale': 'Private A', 'topics': {'science': 1}})
        edition = (await client.post('/api/editions/generate', headers=a, json={})).json()
        eid, aid = edition['id'], edition['articles'][0]['id']
        story_id = fixture.paper.stories.ingest(reader_a, fixture.paper.discovery.items)[aid]
        routes = [('GET', '/profile', None), ('PUT', '/profile', {'locale': 'Tamper', 'topics': {'sports': 1}}),
                  ('GET', '/profile/interests', None), ('POST', '/profile/reset-feedback', {}),
                  ('GET', '/editions', None), ('POST', '/editions/generate', {}), ('GET', '/reading-list', None),
                  ('GET', '/stories/updates', None), ('GET', f'/stories/{story_id}', None),
                  ('PUT', f'/stories/{story_id}/follow', {'followed': True}),
                  ('GET', f'/editions/{eid}', None), ('GET', f'/editions/{eid}/print', None),
                  ('GET', f'/editions/{eid}/pdf', None), ('GET', f'/editions/{eid}/articles/{aid}/image', None),
                  ('GET', f'/editions/{eid}/articles/{aid}/image/metadata', None),
                  ('POST', f'/articles/{aid}/interactions', {'action': 'liked'})]
        for method, path, body in routes:
            response = await client.request(method, '/api' + path, headers={'X-Reader-ID': reader_a}, json=body)
            assert response.status_code == 401, (path, response.text)
        tamper = {**b, 'X-Reader-ID': reader_a}
        assert (await client.get('/api/profile', headers=tamper)).json()['id'] == reader_b
        for path in [f'/editions/{eid}', f'/editions/{eid}/print', f'/editions/{eid}/pdf',
                     f'/editions/{eid}/articles/{aid}/image', f'/editions/{eid}/articles/{aid}/image/metadata', f'/stories/{story_id}']:
            assert (await client.get('/api' + path, headers=tamper)).status_code == 404
        assert (await client.post(f'/api/articles/{aid}/interactions', headers=tamper, json={'action': 'liked'})).status_code == 404
        assert (await client.get('/api/profile', headers=a)).json()['locale'] == 'Private A'
        assert fixture.paper.store.profile(guest)['locale'] == 'Guest preserved'
        response = await client.get('/api/editions', headers=a)
        assert response.headers['cache-control'] == 'no-store'
        assert 'Authorization' in response.headers['vary']
        fixture.settings.supabase_auth_enabled = False
        disabled = ReaderAuth(fixture.settings, fixture.paper.store)
        with pytest.raises(HTTPException) as error:
            await disabled.reader(reader_a, None)
        assert error.value.status_code == 401


async def test_missing_configuration_and_secret_key_never_exposed(auth_fixture):
    fixture = auth_fixture
    fixture.settings.supabase_publishable_key = 'sb_secret_TEST_ONLY_NEVER_PUBLIC'
    auth = ReaderAuth(fixture.settings, fixture.paper.store)
    app = create_app(fixture.settings, newspaper=fixture.paper, auth_service=auth)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        response = await client.get('/api/auth/config')
        assert response.json() == {'enabled': False, 'url': '', 'publishable_key': ''}
        assert (await client.get('/api/profile', headers={'X-Reader-ID': str(uuid4())})).status_code == 200
        assert (await client.get('/api/profile', headers={'Authorization': 'Bearer invalid'})).status_code == 503


@pytest.mark.parametrize('missing', ['exp', 'iat', 'iss', 'aud', 'sub', 'role'])
async def test_required_claims(auth_fixture, missing):
    fixture = auth_fixture
    claims = jwt.decode(fixture.token(), options={'verify_signature': False})
    del claims[missing]
    token = jwt.encode(claims, fixture.private, algorithm='RS256', headers={'kid': 'test-key'})
    async with fixture.client() as client:
        assert (await client.get('/api/profile', headers={'Authorization': 'Bearer ' + token})).status_code == 401


async def test_jwks_total_deadline(auth_fixture):
    async def stalled(request):
        await asyncio.sleep(60)
    fixture = auth_fixture
    fixture.auth.transport = httpx.MockTransport(stalled)
    started = time.monotonic()
    async with fixture.client() as client:
        response = await client.get('/api/profile', headers={'Authorization': 'Bearer ' + fixture.token()})
        assert response.status_code == 503
    assert time.monotonic() - started < 6


async def test_query_parameters_cannot_select_other_account(auth_fixture):
    fixture = auth_fixture
    a, b = fixture.token(), fixture.token()
    async with fixture.client() as client:
        reader_a = (await client.get('/api/profile', headers={'Authorization': 'Bearer ' + a})).json()['id']
        reader_b = (await client.get('/api/profile', headers={'Authorization': 'Bearer ' + b})).json()['id']
        response = await client.get(f'/api/profile?reader_id={reader_a}&profile_id={reader_a}',
                                    headers={'Authorization': 'Bearer ' + b, 'X-Reader-ID': reader_a})
        assert response.json()['id'] == reader_b


@pytest.mark.parametrize('url', ['http://test.supabase.co', 'https://[invalid', 'https://test.supabase.co:invalid',
                                'https://user:password@test.supabase.co', 'https://test.supabase.co/other',
                                'https://test.supabase.co?key=invalid'])
async def test_bad_provider_configuration_preserves_guest(auth_fixture, url):
    fixture = auth_fixture
    fixture.settings.supabase_url = url
    auth = ReaderAuth(fixture.settings, fixture.paper.store)
    assert not auth.configured
    guest = str(uuid4())
    assert await auth.reader(guest, None) == guest
