"""Genuine RSS capture/replay and isolated browser/PDF proof. No production DB writes."""
import argparse
import asyncio
import io
import json
import socket
import sys
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright
from pypdf import PdfReader
from backend.config import Settings
from backend.news.discovery import NewsDiscovery
from backend.news.models import Article, ProfileInput
from backend.news.routes import create_news_router
from backend.news.service import Newspaper
from backend.news.story_graph import match, text
from backend.services.provenance import utc_now

ART = ROOT/'artifacts'


async def run(replay=None):
    ART.mkdir(exist_ok=True)
    capture = ART/'living-story-rss.json'
    with tempfile.TemporaryDirectory() as temp:
        settings = Settings(_env_file=None, database_path=str(Path(temp)/'demo.sqlite3'),
                            daily_generation_enabled=False, credit_search_confirmed_free=False)
        if replay:
            saved = json.loads(Path(replay).read_text(encoding='utf-8'))
            articles = [Article.model_validate(a) for a in saved['articles']]
            warnings = ['Archived genuine RSS replay; not current live news.']
        else:
            result = await NewsDiscovery(settings).retrieve()
            articles, warnings = result['articles'], result['warnings']
            capture.write_text(json.dumps({'captured_at':utc_now().isoformat(), 'warnings':warnings,
                                          'articles':[a.model_dump(mode='json') for a in articles]}, indent=2),encoding='utf-8')
        if not articles:
            raise RuntimeError('No RSS articles available. Replay a prior genuine capture with --replay PATH.')
        class Replay:
            items = articles
            async def retrieve(self, *args):
                return {'articles':self.items, 'warnings':warnings + ['Archived/replayed source observations for this isolated demonstration; no future developments simulated.'], 'cached':True}
        discovery = Replay()
        paper = Newspaper(settings, discovery=discovery)
        reader = str(uuid4())
        paper.store.save_profile(reader, ProfileInput(topics={'world':1,'science':1,'technology':1}))
        values = [a.model_dump(mode='json') for a in articles]
        vectors = await asyncio.to_thread(paper.stories.embeddings.encode, [text(a) for a in values])
        positive, rejected = None, None
        for i,a in enumerate(values):
            for j,b in enumerate(values[i+1:], i+1):
                accepted, signals, score = match(a,b,vectors,settings.story_similarity_threshold)
                if accepted and positive is None:
                    positive = (i,j,signals)
                if not accepted and rejected is None:
                    rejected = (i,j)
        indices = positive[:2] if positive else (0,)
        discovery.items = [articles[indices[0]]]
        first = await paper.generate(reader)
        story_id = first['articles'][0]['story_id']
        app = FastAPI()
        app.include_router(create_news_router(paper))
        app.mount('/', StaticFiles(directory=ROOT/'frontend/dist', html=True))
        sock = socket.socket()
        sock.bind(('127.0.0.1',0))
        base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(app,log_level='warning'))
        thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started: break
                await asyncio.sleep(.1)
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(viewport={'width':1440,'height':1000})
                    await context.add_init_script('localStorage.setItem("daily-mind-reader", '+json.dumps(reader)+');')
                    page = await context.new_page()
                    errors=[]
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    await page.goto(base)
                    await page.get_by_role('button',name='Living story · Explore timeline').first.click()
                    await page.get_by_role('button',name='Follow this story',exact=True).click()
                    await page.get_by_role('button',name='Unfollow this story',exact=True).wait_for()
                    discovery.items = [articles[i] for i in indices]
                    await page.get_by_role('button',name='Make a new edition',exact=True).click()
                    await page.get_by_role('button',name='Make a new edition',exact=True).wait_for(state='visible')
                    await page.wait_for_function('document.querySelectorAll(".story-toggle").length > 0 && !document.querySelector(".loading-paper")')
                    await page.get_by_role('button',name='Living story · Explore timeline').first.click()
                    await page.get_by_role('button',name='Unfollow this story',exact=True).wait_for()
                    await page.screenshot(path=str(ART/'living-story-desktop.png'),full_page=True)
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    await page.set_viewport_size({'width':390,'height':844})
                    await page.screenshot(path=str(ART/'living-story-mobile.png'),full_page=True)
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    headers={'X-Reader-ID':reader}
                    archive = await (await context.request.get(base+'/api/editions',headers=headers)).json()
                    edition = await (await context.request.get(base+'/api/editions/'+archive[0]['id'],headers=headers)).json()
                    response = await context.request.get(base+'/api/editions/'+edition['id']+'/pdf',headers=headers,timeout=60000)
                    assert response.status == 200
                    pdf = await response.body()
                    (ART/'living-story-paper.pdf').write_bytes(pdf)
                    parsed = PdfReader(io.BytesIO(pdf))
                    pdf_text = '\n'.join(p.extract_text() for p in parsed.pages)
                    if positive:
                        assert 'THE CONTINUING STORIES' in pdf_text
                        assert edition['continuing_stories']
                        assert any(a['breakdown'].get('followed_story') for a in edition['articles'])
                    assert not errors, errors
                    # Unfollow works after a saved edition; snapshots remain immutable.
                    frozen = json.dumps(paper.store.edition(reader,edition['id']),sort_keys=True)
                    await page.get_by_role('button',name='Unfollow this story',exact=True).click()
                    await page.get_by_role('button',name='Follow this story',exact=True).wait_for()
                    assert json.dumps(paper.store.edition(reader,edition['id']),sort_keys=True)==frozen
                    report={'rss_articles':len(articles), 'replay':bool(replay), 'model_status':paper.stories.embeddings.status,
                            'possible_connection': {'titles':[articles[i].title for i in indices], 'signals':positive[2]} if positive else None,
                            'rejected_titles':[articles[i].title for i in rejected] if rejected else [],
                            'timeline_observations':len(paper.stories.detail(reader,story_id).timeline),
                            'follow_and_unfollow':True,'immutable_snapshot':True,'desktop_mobile_no_overflow':True,
                            'pdf_pages':len(parsed.pages),'page_errors':errors,
                            'limitation':'Genuine source material replayed in two editions. No future development or observation time fabricated; not proof of multi-day live operation.'}
                    (ART/'living-story-demo.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                    (ART/('living-story-demo-replay.json' if replay else 'living-story-demo-live.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
                    print(json.dumps(report,indent=2),flush=True)
                finally:
                    await browser.close()
        finally:
            server.should_exit=True
            await asyncio.to_thread(thread.join,10)
            sock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--replay',help='Previously saved genuine RSS capture, clearly labeled archived')
    args=parser.parse_args()
    asyncio.run(run(args.replay))
