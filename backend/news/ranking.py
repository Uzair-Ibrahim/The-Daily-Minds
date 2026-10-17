import re
from datetime import timezone

from backend.news.models import TOPICS
from backend.services.provenance import utc_now

SIGNALS = {"opened": 0.05, "liked": 0.35, "saved": 0.25, "skipped": -0.2, "not_interested": -0.5}


def phrase_matches(phrase, text):
    return bool(re.search(r"(?<!\w)" + re.escape(phrase.strip()) + r"(?!\w)", text, flags=re.IGNORECASE))


def interest_dna(profile, events):
    changes = {key: 0.0 for key in TOPICS}
    counts = {key: 0 for key in TOPICS}
    for event in events:
        for topic in event["topics"]:
            if topic in changes:
                changes[topic] += SIGNALS[event["action"]] / max(len(event["topics"]), 1)
                counts[topic] += 1
    return [{"topic": key, "label": info["label"], "base": profile["topics"].get(key, 0.1),
             "feedback": round(max(-1, min(1, changes[key])), 3),
             "weight": round(max(0.1, min(3, profile["topics"].get(key, 0.1) + max(-1, min(1, changes[key])))), 3),
             "events": counts[key]} for key, info in TOPICS.items()]


def rank_articles(articles, profile, events, now=None, story_ids=None, followed_stories=None, seen_article_ids=None):
    now = now or utc_now()
    dna = {item["topic"]: item for item in interest_dna(profile, events)}
    seen = {event["article_id"] for event in events if event["action"] in {"opened", "skipped", "not_interested"}}
    seen.update(seen_article_ids or [])
    candidates = []
    for article in articles:
        matches = [key for key in article.topics if key in dna]
        explicit = sum(profile["topics"].get(key, 0.1) for key in matches) * 3
        feedback = sum(dna[key]["weight"] - dna[key]["base"] for key in matches) * 3
        keywords = [word for word in profile["keywords"] if phrase_matches(word, article.title + " " + article.description)]
        keyword_score = min(len(keywords), 3) * 2
        region = 1 if profile.get("locale") and phrase_matches(profile["locale"], article.title + " " + article.description) else 0
        age = (now - article.published_at.astimezone(timezone.utc)).total_seconds() / 3600 if article.published_at else None
        future = age is not None and age < -0.1
        if future:
            age = None
        elif age is not None:
            age = max(0, age)
        recency = max(0, 2 * (1 - age / 72)) if age is not None else 0
        repetition = -2 if article.id in seen else 0
        breakdown = {"interests": round(explicit, 3), "feedback": round(feedback, 3),
                     "custom_interests": keyword_score, "region": region, "recency": round(recency, 3), "previously_seen": repetition}
        reasons = ["Matches " + ", ".join(TOPICS[key]["label"] for key in matches)]
        story_id = (story_ids or {}).get(article.id)
        if story_id in (followed_stories or set()) and article.id not in seen:
            breakdown["followed_story"] = 1.5
            reasons.append("Prioritized because you follow this continuing story")
        if keywords:
            reasons.append("Custom interest: " + ", ".join(keywords))
        if region:
            reasons.append("Matches your optional local region")
        if feedback:
            reasons.append("Your feedback adjusted this story's priority")
        if age is None:
            reasons.append("Publication date is in the future; no recency bonus" if future else "Publication date unknown; no recency bonus")
        elif age > 72:
            reasons.append("Older coverage; no recency bonus")
        if repetition:
            reasons.append("Previously included, opened or skipped; reduced repetition")
        candidates.append({**article.model_dump(mode="json"), "breakdown": breakdown, "reasons": reasons,
                           "score": round(sum(breakdown.values()), 3)})
        if story_id:
            candidates[-1]["story_id"] = story_id
    ranked, source_counts = [], {}
    boosted = 0
    while candidates:
        if boosted >= max(1, profile.get('edition_length', 8) // 2):
            for item in candidates:
                bonus = item['breakdown'].pop('followed_story', 0)
                if bonus:
                    item['score'] = round(item['score'] - bonus, 3)
                    item['reasons'].remove('Prioritized because you follow this continuing story')
        selected = max(candidates, key=lambda item: (item["score"] - source_counts.get(item["source"], 0), item["id"]))
        candidates.remove(selected)
        boosted += bool(selected['breakdown'].get('followed_story'))
        penalty = -source_counts.get(selected["source"], 0)
        selected["breakdown"]["source_diversity"] = penalty
        selected["score"] = round(selected["score"] + penalty, 3)
        if penalty:
            selected["reasons"].append("Publisher diversity adjustment")
        source_counts[selected["source"]] = source_counts.get(selected["source"], 0) + 1
        ranked.append(selected)
    return ranked
