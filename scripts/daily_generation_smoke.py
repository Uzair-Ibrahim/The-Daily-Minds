"""Verify actual automatic RSS generation, browser and matching PDF on an isolated server."""
import asyncio
import io
import json
import os
from pathlib import Path
import re
import socket
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
import uvicorn
from playwright.async_api import async_playwright
from pypdf import PdfReader

from backend.config import Settings
from backend.main import create_app
from backend.news.models import ProfileInput
from backend.news.service import Newspaper

ART = ROOT / 'artifacts'


async def start(paper):
    app = create_app(paper.settings, newspaper=paper)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    for _ in range(100):
        if server.started:
            return server, task, f'http://127.0.0.1:{sock.getsockname()[1]}'
        if task.done():
            await task
            raise RuntimeError('QA server exited')
        await asyncio.sleep(0.05)
    server.should_exit = True
    await task
    raise RuntimeError('QA server startup timed out')


async def verify_browser(base, reader, edition, prefix):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            await context.add_init_script('localStorage.setItem("daily-mind-reader", ' + json.dumps(reader) + ');')
            page = await context.new_page()
            errors, generation_requests = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda req: generation_requests.append(req.url) if '/editions/generate' in req.url else None)
            await page.goto(base)
            await page.locator('.newspaper').wait_for(timeout=15000)
            assert await page.locator('.article-card h3').all_text_contents() == [item['title'] for item in edition['articles']]
            if edition['status'] == 'offline_fallback':
                await page.get_by_text('Offline edition — previously retrieved content, not fresh news.', exact=True).wait_for()
            await page.screenshot(path=str(ART / f'{prefix}-web.png'), full_page=True)
            async with page.expect_download(timeout=60000) as pending:
                await page.get_by_role('button', name='Download PDF', exact=True).click()
            path = ART / f'{prefix}.pdf'
            await (await pending.value).save_as(str(path))
            pdf = PdfReader(path)
            text = re.sub(r'\s+', ' ', ' '.join(sheet.extract_text() for sheet in pdf.pages))
            assert edition['id'] in text and edition['local_date'] in text
            for article in edition['articles']:
                assert re.sub(r'\s+', ' ', article['title']) in text
            for takeaway in edition['takeaways']:
                assert re.sub(r'\s+', ' ', takeaway['text']) in text
            if edition['status'] == 'offline_fallback':
                assert 'previously retrieved content, not fresh news' in text
            assert any(sheet.get('/Annots') for sheet in pdf.pages)
            await page.get_by_role('button', name='The archive', exact=True).click()
            await page.locator('.archive-card').first.click()
            await page.locator('.newspaper').wait_for()
            assert not generation_requests, 'Opening the automatic snapshot unexpectedly generated another edition'
            assert not errors, errors
            import pypdfium2
            rendered = pypdfium2.PdfDocument(str(path))
            for index in range(len(rendered)):
                sheet = rendered[index]
                bitmap = sheet.render(scale=1)
                bitmap.to_pil().save(ART / f'{prefix}-page-{index+1}.png')
                bitmap.close()
                sheet.close()
            rendered.close()
            return {'pages': len(pdf.pages), 'article_titles_and_takeaways_match': True,
                    'edition_id_matches_pdf': True, 'archive_opened': True, 'browser_errors': errors,
                    'browser_generation_calls': len(generation_requests)}
        finally:
            await browser.close()


async def main():
    ART.mkdir(exist_ok=True)
    run_id = uuid4().hex
    settings = Settings(_env_file=None, database_path=str(ROOT / 'data' / f'daily-qa-{run_id}.sqlite3'),
                        daily_generation_interval_seconds=1, credit_search_confirmed_free=False,
                        exa_api_key='', tavily_api_key='', llm_api_key='', llm_provider='none')
    paper = Newspaper(settings)
    reader = str(uuid4())
    paper.store.save_profile(reader, ProfileInput(topics={'technology': 2, 'science': 1}, keywords=['AI'], edition_length=4))
    server, task, base = await start(paper)
    report = {'data': 'Actual public RSS; no credit search or model calls', 'database': 'Isolated local QA database'}
    try:
        async with httpx.AsyncClient(base_url=base, headers={'X-Reader-ID': reader}, timeout=70) as client:
            for _ in range(350):
                archive = (await client.get('/api/editions')).json()
                if archive:
                    break
                await asyncio.sleep(0.2)
            assert archive, 'Automatic real RSS generation failed; no invented replacement'
            edition = (await client.get('/api/editions/' + archive[0]['id'])).json()
            assert edition['generation_trigger'] == 'automatic' and edition['status'] != 'offline_fallback'
            saved = paper.store.edition(reader, edition['id'])
            report['automatic_live'] = await verify_browser(base, reader, edition, 'automatic-daily')
            stable = (await client.post('/api/editions/generate', json={})).json()
            assert stable == saved
            report['same_day_on_demand_keeps_automatic_snapshot'] = True
            report['live_edition_id'] = edition['id']
            report['live_source_urls'] = [item['url'] for item in edition['articles']]
            if '--full-journey' in sys.argv:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, str(ROOT / 'scripts' / 'browser_smoke.py'), cwd=ROOT,
                    env={**os.environ, 'DAILY_MIND_BASE_URL': base},
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                try:
                    output, errors = await asyncio.wait_for(process.communicate(), 180)
                except TimeoutError:
                    process.terminate()
                    await process.wait()
                    raise RuntimeError('Existing full browser journey timed out')
                if process.returncode:
                    raise RuntimeError('Existing browser journey failed: ' + errors.decode(errors='replace'))
                report['existing_full_browser_journey'] = json.loads(output)
    finally:
        server.should_exit = True
        await task

    class ExplicitOutage:
        async def retrieve(self, *args):
            return {'articles': [], 'cached': False, 'warnings': ['QA: explicitly simulated RSS outage; stored content is real earlier RSS.']}

    offline = Newspaper(settings, discovery=ExplicitOutage())
    offline_reader = str(uuid4())
    offline.store.save_profile(offline_reader, ProfileInput(edition_length=4))
    server, task, base = await start(offline)
    try:
        for _ in range(100):
            archive = offline.store.archive(offline_reader)
            if archive:
                break
            await asyncio.sleep(0.05)
        assert archive
        fallback = offline.store.edition(offline_reader, archive[0]['id'])
        assert fallback['status'] == 'offline_fallback' and fallback['generation_trigger'] == 'automatic'
        report['explicit_simulated_outage_using_real_stored_rss'] = await verify_browser(base, offline_reader, fallback, 'offline-daily')
        assert offline.store.edition(reader, saved['id']) == saved
        report['historical_snapshot_unchanged_across_restart'] = True
        report['offline_labels_verified_in_browser_and_pdf'] = True
    finally:
        server.should_exit = True
        await task
    (ART / 'daily-generation-smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
