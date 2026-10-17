import asyncio
import base64
from html import escape
from urllib.parse import urlsplit


def edition_html(edition, lead_image=None):
    offline_notice = ''
    if edition['status'] == 'offline_fallback':
        offline_notice = ('<p class="disclosure"><strong>Offline edition: previously retrieved content, not fresh news.</strong> '
                          + 'Sources retrieved ' + escape(edition['source_retrieved_from']) + ' to '
                          + escape(edition['source_retrieved_to']) + '. Edition date is assembly date.</p>')
    articles = []
    for index, article in enumerate(edition["articles"]):
        visual = ''
        if index == 0:
            if lead_image:
                encoded = base64.b64encode(lead_image).decode('ascii')
                credit = article.get('image_credit') or 'Image via ' + article['source']
                visual = f'<figure class="lead-picture"><img src="data:image/jpeg;base64,{encoded}" alt="Publisher-supplied story image"><figcaption>{escape(credit)} · Publisher/source rights retained.</figcaption></figure>'
            else:
                section = ' / '.join(article['topics'])
                visual = f'<div class="image-placeholder">{escape(section)}<br><span>In focus · Publisher image unavailable</span></div>'
        date = article["published_at"] or "Publication date unknown"
        link_label = "Open via Google News" if urlsplit(article["url"]).hostname == "news.google.com" else "Read original"
        articles.append(f'''<article class="{'lead' if index == 0 else ''}"><div class="eyebrow">{escape(' / '.join(article['topics']))}</div>
            <h2>{escape(article['title'])}</h2><p class="source">{escape(article['source'])} · {escape(date)}</p>
            {visual}<p>{escape(article['description']) or 'Read the original for the full story.'}</p>
            <p class="note">Attributed excerpt · Retrieved {escape(article['retrieved_at'])}</p>
            <a href="{escape(article['url'], quote=True)}">{link_label} ↗</a></article>''')
    warnings = " ".join(edition["warnings"])
    takeaways = "".join(f'<li>{escape(item["text"])} <a href="{escape(item["url"], quote=True)}">({escape(item["source"])})</a></li>' for item in edition["takeaways"])
    return f'''<!doctype html><html lang="en"><head><meta charset="UTF-8"><title>The Daily Mind — {escape(edition['local_date'])}</title>
    <style>
    *{{box-sizing:border-box}} body{{background:#f6f3ec;color:#25251f;font-family:Georgia,serif;margin:0;padding:28px;line-height:1.55}}
    header{{text-align:center;border-top:4px solid #24271f;border-bottom:2px solid #24271f;padding:22px 0;margin-bottom:26px}}
    h1{{font-size:54px;line-height:1;margin:0 0 12px;letter-spacing:-2px}} .tagline{{font-style:italic}} .dateline{{display:flex;justify-content:space-between;font:11px Arial,sans-serif;margin-top:20px}}
    main{{columns:2;column-gap:28px}} article{{break-inside:avoid;border-bottom:1px solid #c5c1b5;padding-bottom:20px;margin-bottom:20px}}
    h2{{font-size:24px;line-height:1.18;margin:8px 0 12px}} article.lead h2{{font-size:30px}} p{{font-size:13px}} .eyebrow{{font:10px Arial;text-transform:uppercase;letter-spacing:2px;color:#34624d}}
    .source,.note{{font:10px Arial;line-height:1.5;color:#57594f}} a{{color:#315b46;font:11px Arial;overflow-wrap:anywhere}} footer{{break-inside:avoid;border-top:2px solid #24271f;margin-top:24px;padding-top:15px}} footer h2{{font-size:22px}} li{{font-size:12px;margin:9px 0;break-inside:avoid}} .disclosure{{font:10px Arial;line-height:1.6}}
    .lead-picture{{margin:12px 0;break-inside:avoid}} .lead-picture img{{width:100%;max-height:175px;object-fit:contain;display:block;background:#f1f0ea}} figcaption{{font:8px Arial;line-height:1.5;color:#57594f;margin-top:5px}} .image-placeholder{{border-top:1px solid #c5c1b5;border-bottom:1px solid #c5c1b5;padding:16px 0;margin:12px 0;color:#34624d;font:11px Arial;text-transform:uppercase;letter-spacing:1px}} .image-placeholder span{{font:9px Arial;text-transform:none;letter-spacing:0;color:#57594f}}
    @page{{size:A4;margin:14mm 12mm 17mm}} @media print{{body{{padding:0;background:white}} header{{padding-top:10px}} h1{{font-size:48px}}}}
    </style></head><body><header><h1>The Daily Mind<span style="color:#34624d">.</span></h1><div class="tagline">Your newspaper. Your curiosity. Your evolving intelligence.</div>
    <div class="dateline"><span>{escape(edition['local_date'])} · {escape(edition['timezone'])}</span><span>Edition {edition['version']} · {edition['article_count']} stories · {edition['source_count']} sources</span></div></header>
    {offline_notice}<main>{''.join(articles)}</main><footer><h2>{'Three things I learned' if edition.get('takeaway_method') and len(edition['takeaways']) == 3 else 'From this edition' if edition.get('takeaway_method') else 'Three things to explore'}</h2><p class="note">{'Extractive editorial memory: attributed source excerpts, not independently verified facts. Sparse descriptions use headline-only evidence.' if edition.get('takeaway_method') else 'Source headlines from this saved edition; not generated factual conclusions.'}</p><ol>{takeaways}</ol>
    <p class="disclosure">{escape(warnings)}</p><p class="note">Immutable edition {escape(edition['id'])} · Generated {escape(edition['generated_at'])} · Original reporting belongs to the linked publishers.</p></footer></body></html>'''


async def render_pdf(edition, image_loader=None):
    from playwright.async_api import async_playwright
    async with asyncio.timeout(45):
        lead_image = None
        if image_loader and edition['articles'] and edition['articles'][0].get('image_url'):
            try:
                async with asyncio.timeout(7):
                    lead_image = await image_loader.get(edition['articles'][0]['image_url'])
            except Exception:
                pass
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.route("**/*", lambda route: route.abort())
                await page.set_content(edition_html(edition, lead_image), wait_until="load")
                return await page.pdf(format="A4", print_background=True, display_header_footer=True,
                    header_template="<span></span>", footer_template='<div style="width:100%;text-align:center;font-size:8px;color:#666">THE DAILY MIND · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
            finally:
                await browser.close()
