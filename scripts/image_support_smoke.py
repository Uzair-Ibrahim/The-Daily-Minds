"""Actual RSS/CDN/web/PDF proof; missing and failed images are explicitly simulated."""
import asyncio
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from playwright.async_api import async_playwright
from pypdf import PdfReader

from backend.config import Settings
from backend.news.images import ImageDelivery, extract_image
from backend.news.models import ProfileInput
from backend.news.service import Newspaper
from scripts.daily_generation_smoke import start
from scripts.audit_feed_images import audit_feeds

ART = ROOT / 'artifacts'


async def main():
    ART.mkdir(exist_ok=True)
    before = ART / 'automatic-daily-web.png'
    if before.exists() and not (ART / 'image-before-web.png').exists():
        shutil.copyfile(before, ART / 'image-before-web.png')
    report = {'data': 'Actual RSS metadata and publisher CDN images; no generated photography or paid APIs', 'feeds': []}
    delivery = ImageDelivery()
    audit = await audit_feeds()
    if audit:
        for row in audit:
            sample = (row.get('samples') or [{}])[0]
            metadata = extract_image(sample, sample.get('link', row['url']))
            content = await delivery.get(metadata['image_url']) if metadata['image_url'] else None
            report['feeds'].append({'feed': row['feed'], 'audited_at_utc': row.get('audited_at_utc'), 'entries_audited': row.get('entries'),
                                    'fields': row.get('fields'), 'sample_image_url': metadata['image_url'],
                                    'sample_delivery_verified': bool(content), 'delivered_bytes': len(content or b'')})
    settings = Settings(_env_file=None, database_path=str(ROOT / 'data' / f'image-qa-{uuid4().hex}.sqlite3'),
                        daily_generation_enabled=False, credit_search_confirmed_free=False,
                        exa_api_key='', tavily_api_key='', llm_api_key='')
    paper = Newspaper(settings)
    reader = str(uuid4())
    paper.store.save_profile(reader, ProfileInput(topics={'pakistan': 2, 'world': 1}, edition_length=4))
    edition = await paper.generate(reader)
    assert edition['articles'][0].get('image_url'), 'No actual image metadata on the lead story'
    original = json.dumps(edition, sort_keys=True)
    server, task, base = await start(paper)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport={'width': 1440, 'height': 1050}, accept_downloads=True)
                await context.add_init_script('localStorage.setItem("daily-mind-reader", ' + json.dumps(reader) + ');')
                page = await context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto(base)
                await page.locator('.editorial-image-lead .ready img').wait_for(timeout=20000)
                assert await page.locator('.editorial-image-lead img').evaluate('(img) => img.complete && img.naturalWidth >= 160')
                await page.screenshot(path=str(ART / 'image-after-desktop.png'), full_page=True)
                async with page.expect_download(timeout=60000) as pending:
                    await page.get_by_role('button', name='Download PDF', exact=True).click()
                pdf_path = ART / 'image-supported-paper.pdf'
                await (await pending.value).save_as(str(pdf_path))
                pdf = PdfReader(pdf_path)
                images = sum(len(sheet.images) for sheet in pdf.pages)
                assert images == 1, f'Expected one lead photo, got {images}'
                text = re.sub(r'\s+', ' ', ' '.join(sheet.extract_text() for sheet in pdf.pages))
                for article in edition['articles']:
                    assert re.sub(r'\s+', ' ', article['title']) in text
                assert edition['id'] in text and any(sheet.get('/Annots') for sheet in pdf.pages)
                report['real_web_pdf'] = {'edition_id': edition['id'], 'lead_image_source': edition['articles'][0]['image_url'],
                                          'pdf_pages': len(pdf.pages), 'embedded_images': images,
                                          'all_article_titles_match': True, 'edition_id_matches': True}
                import pypdfium2
                document = pypdfium2.PdfDocument(str(pdf_path))
                for index in range(len(document)):
                    sheet = document[index]
                    bitmap = sheet.render(scale=1)
                    bitmap.to_pil().save(ART / f'image-pdf-page-{index+1}.png')
                    bitmap.close()
                    sheet.close()
                document.close()
                await page.set_viewport_size({'width': 390, 'height': 844})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await page.screenshot(path=str(ART / 'image-after-mobile.png'), full_page=True)
                report['mobile_390px_no_overflow'] = True

                await page.route('**/api/editions/*/articles/*/image', lambda route: route.fulfill(status=204))
                await page.reload()
                await page.locator('.editorial-image-lead .missing').wait_for(timeout=15000)
                assert await page.locator('.editorial-image-lead img').count() == 0
                await page.screenshot(path=str(ART / 'image-unavailable-mobile.png'), full_page=True)
                report['explicit_simulated_image_failure_falls_back'] = True
                await page.unroute('**/api/editions/*/articles/*/image')

                # QA-only legacy snapshot from real retrieved content, with image fields removed.
                legacy_reader = str(uuid4())
                paper.store.save_profile(legacy_reader, ProfileInput())
                legacy = {**edition, 'profile_id': legacy_reader}
                legacy['articles'] = [{key: value for key, value in item.items() if not key.startswith('image_')} for item in edition['articles']]
                legacy = paper.store.save_edition(legacy_reader, edition['local_date'], legacy, False)
                legacy_context = await browser.new_context()
                await legacy_context.add_init_script('localStorage.setItem("daily-mind-reader", ' + json.dumps(legacy_reader) + ');')
                legacy_page = await legacy_context.new_page()
                await legacy_page.goto(base)
                await legacy_page.locator('.editorial-image-lead .missing').wait_for()
                assert await legacy_page.locator('.article-card h3').count() == len(edition['articles'])
                await legacy_page.screenshot(path=str(ART / 'image-legacy-no-photo.png'), full_page=True)
                report['explicit_legacy_snapshot_without_image_fields_readable'] = True
                report['browser_errors'] = errors
                assert not errors
            finally:
                await browser.close()
        assert json.dumps(paper.store.edition(reader, edition['id']), sort_keys=True) == original
        report['original_snapshot_unchanged'] = True
        if '--full-journey' in sys.argv:
            process = await asyncio.create_subprocess_exec(sys.executable, str(ROOT / 'scripts' / 'browser_smoke.py'), cwd=ROOT,
                env={**os.environ, 'DAILY_MIND_BASE_URL': base}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                output, errors = await asyncio.wait_for(process.communicate(), 180)
            except TimeoutError:
                process.terminate()
                await process.wait()
                raise RuntimeError('Existing browser journey timed out')
            assert process.returncode == 0, errors.decode(errors='replace')
            report['existing_full_journey'] = json.loads(output)
    finally:
        server.should_exit = True
        await task
    (ART / 'image-support-smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
