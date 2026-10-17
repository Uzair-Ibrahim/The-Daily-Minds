"""Real local browser journey. Uses public RSS only; no fixture data or credit APIs."""
import asyncio
import json
import os
import re
import unicodedata
from pathlib import Path

from playwright.async_api import async_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
BASE_URL = os.getenv("DAILY_MIND_BASE_URL", "http://127.0.0.1:8000")


def visible_text(value):
    value = unicodedata.normalize('NFKC', value)
    value = re.sub(r'\s+', ' ', ''.join(character for character in value if unicodedata.category(character) != 'Cf'))
    return re.sub(r'(?<=\w)- (?=\w)', '-', value)


async def main():
    ARTIFACTS.mkdir(exist_ok=True)
    report = {"data": "real public RSS, no paid APIs", "base_url": BASE_URL, "checks": []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True,
                                                record_video_dir=str(ARTIFACTS / "browser-recordings"),
                                                record_video_size={"width": 1440, "height": 1000})
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(BASE_URL + "/", wait_until="networkidle")
            await page.get_by_role("button", name="Find my rhythm").wait_for()
            await page.screenshot(path=str(ARTIFACTS / "onboarding-desktop.png"))
            await page.get_by_role("button", name="Find my rhythm").click()
            async with page.expect_response(lambda response: response.url.endswith("/api/editions/generate") and response.request.method == "POST", timeout=90000) as response_info:
                await page.get_by_role("button", name="Make my morning paper").click()
            response = await response_info.value
            assert response.ok, await response.text()
            first = await response.json()
            await page.locator(".newspaper").wait_for(timeout=90000)
            report["checks"].append("onboarding, real RSS edition generation, web reading")
            await page.screenshot(path=str(ARTIFACTS / "edition-desktop.png"), full_page=True)
            await page.locator('button[aria-label^="Like "]').first.click()
            await page.get_by_role("status").filter(has_text="Liked.").wait_for()
            await page.locator('button[aria-label^="Save "]').first.click()
            await page.get_by_role("status").filter(has_text="Saved.").wait_for()
            await page.locator('button[aria-label^="Skip "]').nth(1).click()
            await page.locator(".skipped-card").wait_for()
            await page.get_by_role("button", name="Interest DNA", exact=True).click()
            await page.locator(".dna-panel").wait_for()
            await page.screenshot(path=str(ARTIFACTS / "interest-dna.png"))
            report["checks"].append("like/save/skip events and explainable Interest DNA")
            async with page.expect_response(lambda response: response.url.endswith("/api/editions/generate") and response.request.method == "POST", timeout=90000) as next_response:
                await page.get_by_role("button", name="See it in your next edition").click()
            second = await (await next_response.value).json()
            await page.locator(".newspaper").wait_for(timeout=90000)
            assert second["version"] == 2 and second["id"] != first["id"]
            first_scores = {item["id"]: item["score"] for item in first["articles"]}
            differences = [{"article_id": item["id"], "before": first_scores[item["id"]], "after": item["score"]}
                           for item in second["articles"] if item["id"] in first_scores and item["score"] != first_scores[item["id"]]]
            assert differences, "Real feedback did not change any article priority"
            report["ranking_changes"] = differences
            old_positions = {item["id"]: index for index, item in enumerate(first["articles"], 1)}
            order_changes = [{"article_id": item["id"], "before_position": old_positions[item["id"]], "after_position": index}
                             for index, item in enumerate(second["articles"], 1)
                             if item["id"] in old_positions and old_positions[item["id"]] != index]
            report["ranking_order_changes"] = order_changes
            report["ranking_feedback_verified"] = bool(differences)
            report["visible_order_changed"] = bool(order_changes)
            async with page.expect_download(timeout=60000) as download_info:
                await page.get_by_role("button", name="Download PDF").click()
            await (await download_info.value).save_as(str(ARTIFACTS / "daily-mind-live.pdf"))
            pdf = PdfReader(ARTIFACTS / "daily-mind-live.pdf")
            text = visible_text(" ".join(sheet.extract_text() for sheet in pdf.pages))
            assert "The Daily Mind" in text and second["local_date"] in text and second['id'] in text
            for article in second["articles"]:
                assert visible_text(article["title"]) in text, article["title"]
            report["pdf_pages"] = len(pdf.pages)
            report["checks"].append("same saved edition PDF download, parsing and source text")
            await page.get_by_role("button", name="The archive", exact=True).click()
            await page.locator(".archive-card").first.wait_for()
            assert await page.locator(".archive-card").count() == 2
            await page.screenshot(path=str(ARTIFACTS / "archive-desktop.png"))
            await page.locator(".archive-card").last.click()
            await page.locator(".newspaper").wait_for()
            assert first["articles"][0]["title"] in await page.locator(".newspaper").text_content()
            await page.reload(wait_until="networkidle")
            await page.locator(".newspaper").wait_for()
            report["checks"].append("versioned archive and profile persistence on reload")
            await page.get_by_role("button", name="Interest DNA", exact=True).click()
            await page.get_by_role("button", name="Reset feedback").click()
            await page.get_by_role("status").filter(has_text="Feedback reset").wait_for()
            assert "0 topic signals" in await page.locator(".dna-panel").inner_text()
            await page.get_by_role("button", name="Edit preferences").click()
            await page.get_by_role("button", name="Find my rhythm").wait_for()
            await page.get_by_role("button", name="Cancel", exact=True).click()
            await page.get_by_role("button", name="Your paper", exact=True).click()
            assert await page.locator('button[aria-label^="Like "]').first.is_enabled()
            report["checks"].append("feedback reset clears signals/actions; preferences editor opens and cancels")
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.screenshot(path=str(ARTIFACTS / "edition-mobile.png"), full_page=True)
            assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile layout overflows"
            report["checks"].append("390px mobile layout without horizontal overflow")
            assert not errors, errors
            report["browser_errors"] = errors
            report["edition_ids"] = [first["id"], second["id"]]
            report["article_count"] = second["article_count"]
            report["reader_id"] = await page.evaluate("localStorage.getItem('daily-mind-reader')")
            report["result"] = "PASS"
            await context.close()
            await page.video.save_as(str(ARTIFACTS / "browser-journey.webm"))
        finally:
            await browser.close()
    (ARTIFACTS / "browser-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
