import asyncio
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import Header, HTTPException


class ReaderAuth:
    def __init__(self, settings, store, transport=None):
        self.settings, self.store, self.transport = settings, store, transport
        self.url = settings.supabase_url.rstrip('/')
        try:
            parts = urlsplit(self.url)
            valid_url = (parts.scheme == 'https' and parts.hostname and parts.port in {None, 443}
                         and not parts.username and not parts.password and not parts.path
                         and not parts.query and not parts.fragment)
        except ValueError:
            valid_url = False
        self.configured = bool(settings.supabase_auth_enabled and valid_url
                               and settings.supabase_publishable_key.startswith('sb_publishable_'))
        self.keys, self.expires, self.next_fetch = {}, 0, 0
        self.lock = asyncio.Lock()
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS auth_readers(subject TEXT PRIMARY KEY, reader_id TEXT UNIQUE NOT NULL)')

    def mapped_reader(self, subject):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT reader_id FROM auth_readers WHERE subject=?', (subject,)).fetchone()
            if row:
                return row['reader_id']
            reader = str(uuid4())
            db.execute('INSERT INTO auth_readers VALUES(?,?)', (subject, reader))
            return reader

    async def key(self, kid, algorithm):
        async with self.lock:
            now = time.monotonic()
            if now >= self.expires or kid not in self.keys:
                if now < self.next_fetch:
                    if now >= self.expires:
                        raise HTTPException(503, 'Authentication temporarily unavailable. Retry or explicitly continue as guest.')
                else:
                    self.next_fetch = now + 10
                    try:
                        async with asyncio.timeout(4), httpx.AsyncClient(timeout=4, transport=self.transport, follow_redirects=False) as client:
                            response = await client.get(self.url + '/auth/v1/.well-known/jwks.json')
                            response.raise_for_status()
                            if len(response.content) > 65536:
                                raise ValueError('JWKS too large')
                            keys = response.json()['keys']
                            if not isinstance(keys, list) or len(keys) > 20:
                                raise ValueError('Invalid JWKS')
                            self.keys = {k['kid']: k for k in keys if isinstance(k, dict) and isinstance(k.get('kid'), str)
                                         and k.get('kty') in {'RSA', 'EC'} and k.get('use', 'sig') == 'sig'}
                            self.expires = now + 300
                    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
                        raise HTTPException(503, 'Authentication temporarily unavailable. Retry or explicitly continue as guest.') from None
            value = self.keys.get(kid)
            if not value or value.get('alg', algorithm) != algorithm or value['kty'] != {'RS256': 'RSA', 'ES256': 'EC'}[algorithm]:
                raise jwt.InvalidTokenError('Unknown signing key')
            return jwt.PyJWK.from_dict(value, algorithm=algorithm).key

    async def verify(self, authorization):
        if not self.configured:
            raise HTTPException(503, 'Account authentication is not configured. Guest Mode remains available.')
        try:
            scheme, token = authorization.split(' ', 1)
            if scheme.lower() != 'bearer' or not token or len(token) > 16384:
                raise jwt.InvalidTokenError()
            header = jwt.get_unverified_header(token)
            algorithm, kid = header.get('alg'), header.get('kid')
            if algorithm not in {'ES256', 'RS256'} or not isinstance(kid, str) or len(kid) > 200:
                raise jwt.InvalidTokenError()
            key = await self.key(kid, algorithm)
            claims = jwt.decode(token, key, algorithms=[algorithm], issuer=self.url + '/auth/v1',
                                audience='authenticated', options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']})
            subject = str(UUID(claims['sub']))
            if claims.get('role') != 'authenticated' or claims.get('is_anonymous', False):
                raise jwt.InvalidTokenError()
            return subject
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise HTTPException(401, 'Session expired or invalid. Sign in again, or explicitly continue as guest.',
                                headers={'WWW-Authenticate': 'Bearer'}) from None

    async def reader(self, x_reader_id: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        if authorization is not None:
            return self.mapped_reader(await self.verify(authorization))
        try:
            reader = str(UUID(x_reader_id or ''))
        except ValueError:
            raise HTTPException(400, 'Provide your anonymous reader ID in X-Reader-ID.') from None
        with self.store.connect() as db:
            protected = db.execute('SELECT 1 FROM auth_readers WHERE reader_id=?', (reader,)).fetchone()
        if protected:
            raise HTTPException(401, 'Sign in to open this account profile.', headers={'WWW-Authenticate': 'Bearer'})
        return reader
