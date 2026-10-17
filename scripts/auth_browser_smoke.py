"""Actual Chromium + FastAPI + SQLite; synthetic news and mocked Supabase only."""
import asyncio
import io
import json
from pathlib import Path
import socket
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
import uvicorn
from playwright.async_api import async_playwright
from pypdf import PdfReader
from backend.news.models import ProfileInput
from tests.test_auth import AuthFixture


async def main():
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    fixture = AuthFixture(ROOT / 'data' / f'auth-qa-{uuid4().hex}.sqlite3')
    guest, user_a, user_b = (str(uuid4()) for _ in range(3))
    readers = {'guest': guest, 'a': fixture.auth.mapped_reader(user_a), 'b': fixture.auth.mapped_reader(user_b)}
    editions = {}
    for key, reader in readers.items():
        fixture.paper.store.save_profile(reader, ProfileInput(locale=key, topics={'science': 1, 'technology': 1}))
        editions[key] = await fixture.paper.generate(reader)
    # MOCK DATA: publisher image retrieval is out of scope for authentication QA.
    async def no_image(article):
        return {'image_url': None, 'image_status': 'unavailable'}
    fixture.paper.image_resolver.resolve = no_image
    server_socket = socket.socket()
    server_socket.bind(('127.0.0.1', 0))
    server_socket.listen()
    server = uvicorn.Server(uvicorn.Config(fixture.app, log_level='warning'))
    task = asyncio.create_task(server.serve(sockets=[server_socket]))
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(.05)
    base = f'http://127.0.0.1:{server_socket.getsockname()[1]}'
    report = {'data': 'TEST ONLY synthetic news; mocked Supabase HTTP; real asymmetric JWT verification, SQLite, Chromium and PDF', 'checks': []}
    selected = user_a
    offline = False
    refresh_requests = []

    def session(subject):
        token = fixture.token(subject)
        return {'access_token': token, 'token_type': 'bearer', 'expires_in': 3600,
                'refresh_token': 'TEST_ONLY_REFRESH_' + subject,
                'user': {'id': subject, 'aud': 'authenticated', 'role': 'authenticated', 'email': 'reader@example.test',
                         'app_metadata': {'provider': 'email', 'providers': ['email']}, 'user_metadata': {},
                         'created_at': '2026-10-17T00:00:00Z'}}

    async def provider(route):
        if 'grant_type=refresh_token' in route.request.url:
            refresh_requests.append(route.request.url)
        if offline:
            await route.abort('failed')
        elif '/signup' in route.request.url:
            await route.fulfill(json={'user': session(selected)['user'], 'session': None})
        elif '/logout' in route.request.url:
            await route.fulfill(status=204)
        elif '/user' in route.request.url:
            await route.fulfill(json=session(selected)['user'])
        else:
            await route.fulfill(json=session(selected))

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
                await context.add_init_script('if (!localStorage.getItem("daily-mind-reader")) localStorage.setItem("daily-mind-reader",' + json.dumps(guest) + ');')
                await context.route('https://test-project.supabase.co/auth/v1/**', provider)
                page = await context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto(base)
                await page.locator('.newspaper').wait_for()
                assert await page.locator('.account-strip').inner_text() == 'GUEST READING ROOM\nSign in\nCreate account'
                report['checks'].append('Guest Mode opens pre-existing archive without signup')
                await page.get_by_role('button', name='Create account', exact=True).click()
                dialog = page.get_by_role('dialog')
                await dialog.get_by_label('Email', exact=True).fill('reader@example.test')
                await dialog.get_by_label('Password', exact=True).fill('TEST_ONLY_password_123')
                await dialog.get_by_role('button', name='Create account', exact=True).click()
                await dialog.get_by_text('Check your email to confirm your account, then sign in.', exact=True).wait_for()
                report['checks'].append('Email-confirmation signup feedback; no automatic guest merge')
                await dialog.get_by_label('Password', exact=True).fill('TEST_ONLY_password_123')
                await dialog.get_by_role('button', name='Sign in', exact=True).click()
                await page.get_by_text('YOUR ACCOUNT EDITION', exact=True).wait_for()
                await page.locator('.newspaper').wait_for()
                await page.reload()
                await page.get_by_text('YOUR ACCOUNT EDITION', exact=True).wait_for()
                await page.locator('.newspaper').wait_for()
                assert await page.evaluate("async () => (await (await fetch('/api/profile', {headers:{Authorization:'Bearer '+JSON.parse(localStorage.getItem('daily-mind-auth-session')).access_token}})).json()).locale") == 'a'
                report['checks'].append('Sign-in and persistent session survive page reload; backend maps account A')
                story = page.locator('.story-memory').first
                await story.locator('button').first.click()
                await story.locator('.story-timeline li').first.wait_for()
                await story.get_by_role('button', name='Follow this story', exact=True).click()
                await story.get_by_role('button', name='Unfollow this story', exact=True).wait_for()
                report['checks'].append('Authenticated Living Story timeline and follow use the scoped account API')
                await page.locator('button[aria-label^="Like "]').first.click()
                await page.get_by_role('status').filter(has_text='Liked.').wait_for()
                await page.locator('button[aria-label^="Save "]').first.click()
                await page.get_by_role('status').filter(has_text='Saved.').wait_for()
                await page.get_by_role('button', name='Reading list', exact=True).click()
                await page.get_by_text('Your reading list', exact=False).first.wait_for()
                await page.get_by_role('button', name='Interest DNA', exact=True).click()
                await page.locator('.dna-panel').wait_for()
                await page.get_by_role('button', name='The archive', exact=True).click()
                await page.locator('.archive-card').first.click()
                await page.locator('.newspaper').wait_for()
                async with page.expect_download(timeout=60000) as pending:
                    await page.get_by_role('button', name='Download PDF', exact=True).click()
                path = artifacts / 'auth-account-a.pdf'
                await (await pending.value).save_as(str(path))
                pdf_text = ' '.join(p.extract_text() for p in PdfReader(path).pages)
                assert editions['a']['id'] in pdf_text
                report['checks'].append('Authenticated likes, saves, reading list, Interest DNA, archives and matching PDF')
                await page.screenshot(path=str(artifacts / 'auth-account-desktop.png'), full_page=True)
                await page.get_by_role('button', name='Sign out', exact=True).click()
                await page.locator('.newspaper').wait_for()
                await page.get_by_text('GUEST READING ROOM', exact=True).wait_for()
                assert await page.evaluate("localStorage.getItem('daily-mind-reader')") == guest
                assert fixture.paper.store.events(guest) == []
                report['checks'].append('Sign-out restores original guest profile without leaking account feedback')
                selected = user_b
                await page.get_by_role('button', name='Sign in', exact=True).click()
                dialog = page.get_by_role('dialog')
                await dialog.get_by_label('Email', exact=True).fill('other@example.test')
                await dialog.get_by_label('Password', exact=True).fill('TEST_ONLY_password_123')
                await dialog.get_by_role('button', name='Sign in', exact=True).click()
                await page.get_by_text('YOUR ACCOUNT EDITION', exact=True).wait_for()
                await page.locator('.newspaper').wait_for()
                assert fixture.paper.store.events(readers['b']) == []
                assert fixture.paper.store.events(readers['a'])
                expired = fixture.token(user_b, exp=1)
                await page.evaluate("token => { const value=JSON.parse(localStorage.getItem('daily-mind-auth-session')); value.access_token=token; value.expires_at=1; localStorage.setItem('daily-mind-auth-session', JSON.stringify(value)); }", expired)
                await page.reload()
                await page.get_by_text('YOUR ACCOUNT EDITION', exact=True).wait_for()
                await page.locator('.newspaper').wait_for()
                assert refresh_requests
                report['checks'].append('Expired persisted access token refreshed through official SDK before account reading resumes')
                await page.route('**/api/profile/interests', lambda route: route.fulfill(status=401, json={'detail': 'TEST ONLY expired session'}))
                await page.reload()
                await page.get_by_text('SESSION NEEDS ATTENTION', exact=True).wait_for()
                report['checks'].append('Account B isolated from A; expired API session locks account instead of silently falling back')
                await page.unroute('**/api/profile/interests')
                offline = True
                await page.get_by_role('button', name='Continue as guest', exact=True).click()
                await page.locator('.newspaper').wait_for()
                await page.get_by_text('Signed out on this device. Server revocation could not be confirmed.', exact=True).wait_for()
                assert await page.evaluate("localStorage.getItem('daily-mind-auth-session')") is None
                report['checks'].append('Offline sign-out clears persistent session even when provider revocation fails')
                await page.get_by_role('button', name='Sign in', exact=True).click()
                dialog = page.get_by_role('dialog')
                await dialog.get_by_label('Email', exact=True).fill('offline@example.test')
                await dialog.get_by_label('Password', exact=True).fill('TEST_ONLY_password_123')
                await dialog.get_by_role('button', name='Sign in', exact=True).click()
                await dialog.get_by_role('status').wait_for(timeout=20000)
                await dialog.get_by_role('button', name='Continue as guest', exact=True).click()
                await page.locator('.newspaper').wait_for()
                report['checks'].append('Provider network failure shows error; explicit Guest Mode still opens saved newspaper')
                await page.set_viewport_size({'width': 390, 'height': 844})
                await page.get_by_role('button', name='Sign in', exact=True).click()
                await page.screenshot(path=str(artifacts / 'auth-mobile-signin.png'), full_page=True)
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors, errors
                report['checks'].append('Editorial login dialog responsive at 390px; zero uncaught browser errors')
                report['browser_errors'] = errors
                report['jwks_requests'] = fixture.calls
            finally:
                await browser.close()
    finally:
        server.should_exit = True
        await task
    (artifacts / 'auth-browser-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
