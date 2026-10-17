"""Controlled two-profile proof from one real RSS capture; replay is explicitly archived."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings
from backend.news.discovery import NewsDiscovery
from backend.news.models import Article, ProfileInput
from backend.news.service import Newspaper
from backend.services.provenance import utc_now

ARTIFACTS = ROOT / "artifacts"
PROFILES = {
    "A": {"topics": {"technology": 2.5, "business": 1.5}, "keywords": ["AI", "software engineering", "startups"]},
    "B": {"topics": {"science": 2.5, "world": 1.8}, "keywords": ["climate", "health", "world news"]},
}


class CapturedDiscovery:
    def __init__(self, capture):
        self.capture = capture

    async def retrieve(self, query="", targeted=False):
        return {"articles": [Article.model_validate(item) for item in self.capture["articles"]], "cached": True,
                "warnings": ["Controlled comparison reuses a real RSS capture. Original retrieval timestamps retained."], "status": "ok"}


async def main(replay=False):
    ARTIFACTS.mkdir(exist_ok=True)
    capture_path = ARTIFACTS / "personalization-candidates.json"
    settings = Settings(credit_search_confirmed_free=False, database_path=str(ROOT / "data" / "qa-personalization.sqlite3"))
    if replay:
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        mode = "archived_real_rss_replay"
    else:
        result = await NewsDiscovery(settings).retrieve("AI OR software OR startups OR climate OR health")
        if not result["articles"]:
            print(json.dumps({"result": "FAIL", "reason": "No live RSS evidence available", "warnings": result["warnings"]}))
            return 1
        capture = {"captured_at": utc_now().isoformat(), "origin": "real public RSS", "warnings": result["warnings"],
                   "articles": [article.model_dump(mode="json") for article in result["articles"]]}
        capture_path.write_text(json.dumps(capture, indent=2, ensure_ascii=True), encoding="utf-8")
        mode = "live_rss_capture"
    paper = Newspaper(settings, discovery=CapturedDiscovery(capture))
    report = {"mode": mode, "capture_time": capture["captured_at"], "candidate_count": len(capture["articles"]),
              "comparison": "Both readers use the identical real candidate batch and ranking time; no fixtures or model calls.", "profiles": {}}
    fixed_time = utc_now()
    editions = {}
    for name, values in PROFILES.items():
        profile_id = str(uuid4())
        paper.store.save_profile(profile_id, ProfileInput(**values, edition_length=8))
        edition = await paper.generate(profile_id, now=fixed_time)
        editions[name] = edition
        report["profiles"][name] = {"reader_id": profile_id, "preferences": values, "edition_id": edition["id"],
            "stories": [{key: item[key] for key in ("id", "title", "source", "url", "topics", "score", "reasons", "breakdown")} for item in edition["articles"]]}
        (ARTIFACTS / f"profile-{name}-edition.json").write_text(json.dumps(edition, indent=2, ensure_ascii=True), encoding="utf-8")
    a, b = editions["A"]["articles"], editions["B"]["articles"]
    only_a = {item["id"] for item in a} - {item["id"] for item in b}
    only_b = {item["id"] for item in b} - {item["id"] for item in a}
    assert len(only_a) >= 2 and len(only_b) >= 2, "Insufficient profile separation; do not claim the demo passed"
    assert a[0]["id"] != b[0]["id"], "Both profiles have the same lead; inspect ranking before claiming differentiation"
    report["selection_difference"] = {"only_A": len(only_a), "only_B": len(only_b), "different_leads": True}
    target = min(range(1, len(a)), key=lambda i: a[i - 1]["score"] - a[i]["score"])
    chosen = a[target]
    profile_id = report["profiles"]["A"]["reader_id"]
    assert paper.store.interact(profile_id, chosen["id"], "liked")
    next_edition = await paper.generate(profile_id, regenerate=True, now=fixed_time)
    updated = next(item for item in next_edition["articles"] if item["id"] == chosen["id"])
    assert updated["breakdown"]["feedback"] > chosen["breakdown"]["feedback"]
    old_positions = {item["id"]: index for index, item in enumerate(a, 1)}
    order_changes = [{"id": item["id"], "before_position": old_positions[item["id"]], "after_position": index}
                     for index, item in enumerate(next_edition["articles"], 1)
                     if item["id"] in old_positions and old_positions[item["id"]] != index]
    report["feedback"] = {"action": "liked", "article_id": chosen["id"], "before_score": chosen["score"],
                          "after_score": updated["score"], "order_changes": order_changes,
                          "new_edition_id": next_edition["id"], "event_origin": "automated QA action, not organic reader engagement"}
    skip_target = next(item for item in a[1:] if item["id"] != chosen["id"])
    assert paper.store.interact(profile_id, skip_target["id"], "skipped")
    final_edition = await paper.generate(profile_id, regenerate=True, now=fixed_time)
    final_positions = {item["id"]: index for index, item in enumerate(final_edition["articles"], 1)}
    changed = [{"id": item["id"], "before_position": index, "after_position": final_positions.get(item["id"], "not selected")}
               for index, item in enumerate(a, 1) if final_positions.get(item["id"]) != index]
    assert changed, "No observable ranking-order change after feedback"
    report["skip_feedback"] = {"action": "skipped", "article_id": skip_target["id"], "order_changes": changed,
                              "new_edition_id": final_edition["id"], "event_origin": "automated QA action"}
    report["result"] = "PASS"
    (ARTIFACTS / "personalization-proof.json").write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps({"result": "PASS", "mode": mode, "candidate_count": report["candidate_count"],
                      "selection_difference": report["selection_difference"], "feedback": report["feedback"],
                      "skip_feedback": report["skip_feedback"]}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", action="store_true", help="Use the saved real capture; explicitly archived, no live claim")
    raise SystemExit(asyncio.run(main(parser.parse_args().replay)))
