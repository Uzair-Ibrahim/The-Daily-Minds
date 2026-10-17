"""Real Dawn legacy-image regression plus actual browser feedback/share/PDF checks."""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from playwright.async_api import async_playwright
from pypdf import PdfReader

from backend.config import Settings
from backend.news.discovery import NewsDiscovery
from backend.news.models import ProfileInput
from backend.news.ranking import rank_articles
from backend.news.service import Newspaper
from scripts.daily_generation_smoke import start

ART = ROOT / 'artifacts'
STORY = '/2037770/'


async def main():
    ART.mkdir(exist_ok=True)
    settings = Settings(_env_file=None, database_path=str(ROOT/'data'/f'engagement-{uuid4().hex}.sqlite3'),
        daily_generation_enabled=False, exa_api_key='', tavily_api_key='', llm_api_key='', credit_search_confirmed_free=False)
    paper = Newspaper(settings)
    reader = str(uuid4())
    profile = paper.store.save_profile(reader, ProfileInput(topics={'science':2,'world':1},edition_length=4))
    began = perf_counter()
    result = await paper.discovery.retrieve('climate')
    paper.store.articles(result['articles'])
    ranked = rank_articles(result['articles'], profile, [])
    dawn = next((item for item in ranked if STORY in item['url']), None)
    if dawn is None:
        # The global 150-candidate cap can omit a real item still present in its fetched feed.
        feed_items = [item for saved in paper.discovery.feed_cache.values() for item in saved[1] if STORY in str(item.url)]
        if not feed_items:
            raise RuntimeError('Specific Dawn story is no longer present in retrieved feeds; no invented replacement')
        dawn = rank_articles(feed_items[:1],profile,[])[0]
    secondary = next(item for item in ranked if item['id'] != dawn['id'] and item.get('image_url'))
    missing = next(item for item in ranked if not item.get('image_url') and 'news.google.com' in item['url'])
    fourth = next(item for item in ranked if item['id'] not in {dawn['id'],secondary['id'],missing['id']})
    # Reproduce the actual legacy bug: metadata absent in a snapshot of real retrieved news.
    dawn = {key:value for key,value in dawn.items() if not key.startswith('image_')}
    edition = {'title':'The Daily Mind','profile_id':reader,'local_date':profile['updated_at'][:10],
        'timezone':profile['timezone'],'generated_at':profile['updated_at'],'status':'retrieved_live',
        'articles':[dawn,secondary,missing,fourth],'article_count':4,'source_count':len({item['source'] for item in [dawn,secondary,missing,fourth]}),
        'profile_snapshot':profile,'interest_dna':paper.dna(reader),'warnings':['QA selection from actual retrieved RSS; lead reproduces absent historical image fields.'],
        'takeaways':[], 'mode':'attributed_excerpts'}
    edition = paper.store.save_edition(reader,edition['local_date'],edition,False)
    original = copy.deepcopy(edition)
    report={'data':'Actual RSS and publisher image; QA clicks and explicit simulated network/API failures',
            'candidate_count':len(ranked),'retrieval_seconds':round(perf_counter()-began,3),
            'legacy_dawn_image_url_before':dawn.get('image_url'),'original_topics':dawn['topics']}
    server, task, base = await start(paper)
    try:
        async with httpx.AsyncClient(base_url=base,headers={'X-Reader-ID':reader},timeout=60) as client:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(viewport={'width':1440,'height':1050},accept_downloads=True)
                    await context.add_init_script('localStorage.setItem("daily-mind-reader",'+json.dumps(reader)+');')
                    page = await context.new_page()
                    errors=[]; external=[]; requests=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.on('request',lambda req:requests.append(req.url))
                    page.on('request',lambda req:external.append(req.url) if not req.url.startswith(base) and req.url.startswith('http') else None)
                    await page.goto(base)
                    await page.locator('.article-0 .editorial-image-frame.ready img').wait_for(timeout=30000)
                    await page.locator('.article-1 .editorial-image-frame.ready img').wait_for(timeout=30000)
                    await page.locator('.article-2').scroll_into_view_if_needed()
                    await page.locator('.article-2 .editorial-image-frame.missing').wait_for(timeout=30000)
                    assert 'SCIENCE' in (await page.locator('.article-0 .article-kicker').inner_text()).upper()
                    assert await page.locator('.article-0 img').evaluate('(img)=>img.complete && img.naturalWidth>=160')
                    assert await page.locator('.article-2 .editorial-image-frame').evaluate('(el)=>el.getBoundingClientRect().height')<80
                    await page.locator('.article-0').scroll_into_view_if_needed()
                    await page.screenshot(path=str(ART/'engagement-dawn-hero.png'),full_page=True)
                    report['dawn_browser_photo_visible']=True
                    report['section_label']=await page.locator('.article-0 .article-kicker').inner_text()
                    assert not external, 'Third-party request before choosing a share option'
                    lead = page.locator('.article-0')
                    async def click_state(label, expected_label, screenshot):
                        await lead.get_by_role('button',name=label+' '+dawn['title'],exact=True).click()
                        await lead.get_by_role('button',name=expected_label+' '+dawn['title'],exact=True).wait_for()
                        await page.screenshot(path=str(ART/screenshot),full_page=False)
                    assert await lead.locator('.local-like-count').inner_text()=='0'
                    await click_state('Like','Unlike','engagement-liked.png')
                    assert await lead.locator('.local-like-count').inner_text()=='1'
                    await click_state('Unlike','Like','engagement-unliked.png')
                    assert await lead.locator('.local-like-count').inner_text()=='0'
                    await click_state('Like','Unlike','engagement-liked-again.png')
                    await click_state('Save','Unsave','engagement-saved.png')
                    await click_state('Unsave','Save','engagement-unsaved.png')
                    await click_state('Save','Unsave','engagement-saved-again.png')
                    report['like_unlike_like_and_save_unsave_save']=True
                    await page.reload()
                    lead=page.locator('.article-0')
                    await lead.get_by_role('button',name='Unlike '+dawn['title'],exact=True).wait_for()
                    await lead.get_by_role('button',name='Unsave '+dawn['title'],exact=True).wait_for()
                    report['states_persist_after_reload']=True
                    await page.get_by_role('button',name='Reading list',exact=True).click()
                    await page.locator('.reading-list article').wait_for()
                    assert await page.locator('.reading-list article').count()==1
                    await page.get_by_role('button',name='Open saved edition',exact=True).click()
                    await page.locator('.newspaper').wait_for()
                    lead=page.locator('.article-0')
                    await lead.get_by_role('button',name='Share '+dawn['title'],exact=True).click()
                    menu=lead.get_by_role('group',name='Share original news source')
                    await menu.wait_for()
                    for name in ['WhatsApp','X','LinkedIn']:
                        href=await menu.get_by_role('link',name=name,exact=True).get_attribute('href')
                        assert 'localhost' not in href and reader not in href
                    assert not external
                    await page.screenshot(path=str(ART/'engagement-share-menu.png'),full_page=False)
                    await page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__copied=text}}})")
                    await menu.get_by_role('button',name='Copy link',exact=True).click()
                    assert await page.evaluate('window.__copied')==dawn['url']
                    await lead.get_by_role('button',name='Share '+dawn['title'],exact=True).click()
                    await page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});Object.defineProperty(navigator,'share',{configurable:true,value:undefined})")
                    await menu.get_by_role('button',name='Copy link',exact=True).click()
                    assert await menu.get_by_role('textbox',name='Original source link').input_value()==dawn['url']
                    await menu.get_by_role('button',name='Share from this device',exact=True).click()
                    await menu.get_by_role('textbox',name='Original source link').wait_for()
                    await page.evaluate("Object.defineProperty(navigator,'share',{configurable:true,value:async payload=>{window.__shared=payload}})")
                    await menu.get_by_role('button',name='Share from this device',exact=True).click()
                    assert (await page.evaluate('window.__shared'))['url']==dawn['url']
                    report['share_links_clipboard_native_and_fallbacks']=True
                    await lead.get_by_role('button',name='Share '+dawn['title'],exact=True).click()
                    await menu.get_by_role('button',name='Copy link',exact=True).focus()
                    await page.keyboard.press('Escape')
                    assert await lead.get_by_role('button',name='Share '+dawn['title'],exact=True).get_attribute('aria-expanded')=='false'
                    # Explicit failure must leave persisted like state intact.
                    await page.route('**/api/articles/*/interactions',lambda route:route.fulfill(status=503,json={'detail':'QA simulated unavailable'}))
                    await lead.get_by_role('button',name='Unlike '+dawn['title'],exact=True).click()
                    await page.get_by_role('alert').wait_for()
                    assert await lead.get_by_role('button',name='Unlike '+dawn['title'],exact=True).count()==1
                    await page.unroute('**/api/articles/*/interactions')
                    report['failed_action_does_not_desynchronize']=True
                    async with page.expect_download(timeout=60000) as pending:
                        await page.get_by_role('button',name='Download PDF',exact=True).click()
                    path=ART/'engagement-dawn-paper.pdf'
                    await (await pending.value).save_as(str(path))
                    pdf=PdfReader(path)
                    assert sum(len(sheet.images) for sheet in pdf.pages)==1
                    text=' '.join(sheet.extract_text() for sheet in pdf.pages)
                    assert dawn['title'] in re.sub(r'\s+',' ',text) and edition['id'] in text
                    report['pdf']={'pages':len(pdf.pages),'embedded_photos':1,'saved_title_and_id_match':True}
                    import pypdfium2
                    doc=pypdfium2.PdfDocument(str(path))
                    for index in range(len(doc)):
                        sheet=doc[index];bitmap=sheet.render(scale=1);bitmap.to_pil().save(ART/f'engagement-pdf-{index+1}.png');bitmap.close();sheet.close()
                    doc.close()
                    await page.set_viewport_size({'width':390,'height':844})
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    await page.screenshot(path=str(ART/'engagement-mobile.png'),full_page=True)
                    report['mobile_no_overflow']=True
                    report['browser_errors']=errors
                    assert not errors
                    report['browser_image_requests']=len([url for url in requests if '/image' in url])
                finally:
                    await browser.close()
            enriched=(await client.get(f"/api/editions/{edition['id']}/articles/{dawn['id']}/image/metadata")).json()
            report['resolved_dawn_metadata']=enriched
            assert enriched['image_status']=='ready'
            assert paper.store.edition(reader,edition['id'])==original
            report['snapshot_immutable']=True
            image_path=f"/api/editions/{edition['id']}/articles/{dawn['id']}/image"
            first=(await client.get(image_path)).content
            report['image_sha256']=hashlib.sha256(first).hexdigest()
            report['image_download_bytes']=len(first)
            # Persisting a second edition with the same article must share active feedback.
            second=paper.store.save_edition(reader,edition['local_date'],original,True)
            loaded=(await client.get('/api/editions/'+second['id'])).json()
            assert loaded['article_engagement'][dawn['id']]['like_count']==1
            assert loaded['article_engagement'][dawn['id']]['saved']
            report['cross_edition_identity_and_counts']=True
            report['metadata_http_requests']=paper.image_resolver.requests
            report['image_http_requests']=paper.image_delivery.requests
            if '--full-journey' in sys.argv:
                process=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'scripts'/'browser_smoke.py'),cwd=ROOT,
                    env={**os.environ,'DAILY_MIND_BASE_URL':base},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                try:
                    output,errors=await asyncio.wait_for(process.communicate(),180)
                except TimeoutError:
                    process.terminate();await process.wait()
                    raise RuntimeError('Existing full browser regression timed out')
                assert process.returncode==0,errors.decode(errors='replace')
                report['existing_full_journey']=json.loads(output)
    finally:
        server.should_exit=True
        await task
    # New server/process-local loader must reuse persistent metadata and bitmap.
    restored=Newspaper(settings)
    from backend.news.image_resolver import ArticleImageResolver
    from backend.news.images import ImageDelivery
    delivery=ImageDelivery(cache_dir=Path(settings.database_path).parent/'publisher-images')
    resolver=ArticleImageResolver(restored.store,delivery)
    metadata=await resolver.resolve(dawn)
    content=await delivery.get(metadata['image_url'])
    assert content and delivery.requests==0 and resolver.requests==0
    report['cache_survives_loader_restart_without_network']=True
    (ART/'image-engagement-smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    asyncio.run(main())
