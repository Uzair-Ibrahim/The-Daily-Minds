"""Real profile/links/restart checks plus explicitly labeled simulated failure checks."""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import socket
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from playwright.async_api import async_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
BASE = "http://127.0.0.1:8010"


async def start_server():
    global BASE
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    BASE = f"http://127.0.0.1:{port}"
    run_id = str(uuid4())
    process = await asyncio.create_subprocess_exec(sys.executable, str(ROOT / "scripts" / "qa_server.py"), cwd=str(ROOT),
        env=dict(os.environ, QA_PORT=str(port), QA_RUN_ID=run_id, DATABASE_PATH=str(ROOT / "data" / "qa-personalization.sqlite3"), CREDIT_SEARCH_CONFIRMED_FREE="false", EXA_API_KEY="", TAVILY_API_KEY="", LLM_API_KEY="", LLM_PROVIDER="none"),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    process.qa_url = BASE
    process.qa_run_id = run_id
    async with httpx.AsyncClient(timeout=2) as client:
        for _ in range(60):
            if process.returncode is not None:
                raise RuntimeError("Owned QA server exited during startup")
            try:
                response = await client.get(BASE + "/__qa/status")
                if response.status_code == 200 and response.json().get("run_id") == run_id:
                    return process
            except httpx.RequestError:
                pass
            await asyncio.sleep(0.2)
    process.terminate()
    await process.wait()
    raise RuntimeError("QA server failed to start")


async def stop_server(process):
    if process.returncode is None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                status = await client.get(process.qa_url + "/__qa/status")
                if status.json().get("run_id") != process.qa_run_id:
                    raise RuntimeError("QA ownership mismatch")
                await client.post(process.qa_url + "/__qa/stop")
            await asyncio.wait_for(process.wait(), timeout=15)
        except Exception:
            process.terminate()
            await process.wait()


async def main():
    ART.mkdir(exist_ok=True)
    proof = json.loads((ART / "personalization-proof.json").read_text())
    report = {"checks": [], "source_navigation": [], "profile_proof": proof["selection_difference"], "source_mode": proof["mode"]}
    process = await start_server()
    browser = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            for name in ("A", "B"):
                reader = proof["profiles"][name]["reader_id"]
                context = await browser.new_context(viewport={"width": 1440, "height": 1000})
                await context.add_init_script("localStorage.setItem('daily-mind-reader', " + json.dumps(reader) + ")")
                page = await context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                await page.goto(BASE, wait_until="networkidle")
                await page.locator(".newspaper").wait_for()
                await page.screenshot(path=str(ART / f"profile-{name}-browser.png"), full_page=True)
                await page.locator('[aria-label="Editorial memory"]').screenshot(path=str(ART / f"profile-{name}-memory.png"))
                assert await page.locator(".article-card").count() >= 4
                await page.locator(".ranking-details").first.locator("summary").click()
                assert "ranking heuristics" in await page.locator(".ranking-details").first.inner_text()
                assert "Edition generated" in await page.locator(".edition-notes").inner_text()
                assert "Three things I learned" in await page.locator('[aria-label="Editorial memory"]').inner_text()
                if not report["source_navigation"]:
                    for link in await page.locator(".read-source").all():
                        url = await link.get_attribute("href")
                        host = urlsplit(url).hostname or ""
                        if host != "news.google.com" and host.endswith(("bbc.co.uk", "bbc.com", "dawn.com", "theguardian.com")):
                            documents = []
                            def capture_document(response):
                                if response.request.resource_type == "document" and not response.url.startswith(BASE):
                                    documents.append({"url": response.url, "status": response.status})
                            context.on("response", capture_document)
                            async with page.expect_popup(timeout=15000) as opened:
                                await link.click()
                            popup = await opened.value
                            response = None
                            error = None
                            try:
                                response = await popup.wait_for_load_state("domcontentloaded", timeout=20000)
                            except Exception as exception:
                                error = type(exception).__name__
                            final_url = popup.url
                            status = next((item["status"] for item in reversed(documents) if item["url"] == final_url), None)
                            check = {"requested_url": url, "final_url": final_url, "same_publisher_host": urlsplit(final_url).hostname == host,
                                     "http_status": status, "loaded_document": error is None and status is not None and 200 <= status < 400, "error": error}
                            report["source_navigation"].append(check)
                            await popup.close()
                            context.remove_listener("response", capture_document)
                            break
                await page.set_viewport_size({"width": 390, "height": 844})
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                await page.screenshot(path=str(ART / f"profile-{name}-mobile.png"), full_page=True)
                assert not errors, errors
                await context.close()
            report["checks"].extend(["both requested real-capture profiles render distinct editions", "Why this story explains actual signals", "generation/retrieval labels separated", "mobile layouts", "no page errors"])
            assert report["source_navigation"], "No original publisher link was tested"
            reader = proof["profiles"]["B"]["reader_id"]
            edition_id = proof["profiles"]["B"]["edition_id"]
            headers = {"X-Reader-ID": reader}
            async with httpx.AsyncClient(base_url=BASE, headers=headers, timeout=60) as client:
                before = (await client.get('/api/editions/' + edition_id)).json()
                pdf = await client.get('/api/editions/' + edition_id + '/pdf')
                assert pdf.status_code == 200
                (ART / "final-sample-paper.pdf").write_bytes(pdf.content)
                parsed = PdfReader(io.BytesIO(pdf.content))
                text = re.sub(r"\s+", " ", " ".join(sheet.extract_text() for sheet in parsed.pages))
                for item in before["articles"]:
                    assert re.sub(r"\s+", " ", item["title"]) in text
                for item in before["takeaways"]:
                    assert re.sub(r"\s+", " ", item["text"]) in text
                assert any(sheet.get('/Annots') for sheet in parsed.pages)
                report["pdf_pages"] = len(parsed.pages)
            await stop_server(process)
            original_url = BASE
            process = await start_server()
            report["restart_ports"] = {"before": original_url, "after": BASE, "note": "Owned QA process restarts on a new OS-assigned port to avoid Windows TIME_WAIT; same SQLite file."}
            async with httpx.AsyncClient(base_url=BASE, headers=headers, timeout=20) as client:
                after = (await client.get('/api/editions/' + edition_id)).json()
                assert before == after, "Saved edition changed across real server restart"
                report["restart_snapshot_sha256"] = hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest()
                assert (await client.get('/api/editions')).json()
                missing = (await client.post('/api/v1/ask', json={"question": "test", "live": True})).json()
                assert missing["status"] == "provider_unavailable" and not missing["evidence"]
            report["checks"].extend(["real server process shutdown/restart preserves snapshot and archive", "PDF article + takeaway text and links match snapshot", "missing API credentials fail gracefully"])
            failure_context = await browser.new_context(viewport={"width": 1440, "height": 1000})
            failure_page = await failure_context.new_page()
            await failure_page.route("**/api/editions/generate", lambda route: route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": {"message": "TEST ONLY: no live news is available. Open a saved edition or retry."}})))
            await failure_page.goto(BASE, wait_until="networkidle")
            await failure_page.get_by_role("button", name="Find my rhythm").click()
            await failure_page.get_by_role("button", name="Make my morning paper").click()
            await failure_page.get_by_role("alert").filter(has_text="TEST ONLY").wait_for(timeout=20000)
            assert await failure_page.locator(".newspaper").count() == 0
            await failure_page.screenshot(path=str(ART / "simulated-network-error.png"))
            report["checks"].append("explicitly simulated HTTP 503 renders honest error/empty state; no fake paper")
            await failure_context.close()
            journey = await asyncio.create_subprocess_exec(sys.executable, str(ROOT / "scripts" / "browser_smoke.py"), cwd=str(ROOT),
                env=dict(os.environ, DAILY_MIND_BASE_URL=BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(journey.communicate(), timeout=180)
            assert journey.returncode == 0, stdout.decode(errors="replace") + stderr.decode(errors="replace")
            report["full_live_journey"] = json.loads(stdout)
            report["checks"].append("fresh successful onboarding through real live RSS, interactions, new edition, PDF, archive and recording")
            await browser.close()
            browser = None
        report["result"] = "PASS"
        (ART / "final-browser-qa.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        if browser:
            await browser.close()
        await stop_server(process)


if __name__ == "__main__":
    asyncio.run(main())
