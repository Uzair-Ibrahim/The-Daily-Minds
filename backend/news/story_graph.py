"""Reader-scoped evidence memory; possible relationships are never verification."""
import hashlib
import json
import re
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

from backend.news.discovery import canonical_url
from backend.news.embeddings import Embeddings

SCHEMA = """
CREATE TABLE IF NOT EXISTS story_clusters(
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), title TEXT NOT NULL,
 first_observed TEXT NOT NULL, last_observed TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS story_reader ON story_clusters(profile_id,last_observed);
CREATE TABLE IF NOT EXISTS story_articles(
 story_id TEXT NOT NULL REFERENCES story_clusters(id), article_id TEXT NOT NULL,
 url TEXT NOT NULL, PRIMARY KEY(story_id,article_id));
CREATE TABLE IF NOT EXISTS story_timeline_events(
 id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES story_clusters(id),
 article_id TEXT NOT NULL, observed_at TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS story_events ON story_timeline_events(story_id,observed_at);
CREATE TABLE IF NOT EXISTS reader_story_follows(
 profile_id TEXT NOT NULL REFERENCES profiles(id), story_id TEXT NOT NULL REFERENCES story_clusters(id),
 followed_at TEXT NOT NULL, PRIMARY KEY(profile_id,story_id));
CREATE TABLE IF NOT EXISTS story_embeddings(id TEXT PRIMARY KEY, vector TEXT NOT NULL);
"""

STOP = set("the a an to of for in on at and or is are was were has have had with from by as after before says said new news latest update updates report reports this that it its into over will more than amid about could would their not".split())
BROAD = set("ai artificial intelligence technology world science business government company launch launches model models research pakistan city country".split())


class Observation(BaseModel):
    article_id: str
    title: str
    url: str
    source: str
    description: str
    published_at: str | None = None
    observed_at: str
    change: str
    signals: list[str]
    association: str


class StoryDetail(BaseModel):
    id: str
    title: str
    first_observed: str
    last_observed: str
    followed: bool
    timeline: list[Observation]
    limitation: str = "Possible related coverage, not independently verified. Publication time is supplied by the source; observation time is retrieval time."


class FollowInput(BaseModel):
    followed: bool


class StoryUpdates(BaseModel):
    since: str | None
    stories: list[StoryDetail]


def text(article):
    return article["title"] + ". " + article.get("description", "")


def terms(value):
    return set(re.findall(r"[\w-]+", value.casefold())) - STOP


def match(a, b, vectors=None, threshold=0.68):
    if canonical_url(a["url"]) == canonical_url(b["url"]):
        return True, ["Same original article URL"], 1.0
    at, bt = terms(a["title"]), terms(b["title"])
    shared = (at & bt) - BROAD
    # Distinct product numbers, years and explicit dates cannot be ignored.
    nums = lambda value: set(re.findall(r"\b\d+(?:[.-]\d+)*\b", value))
    na, nb = nums(a["title"]), nums(b["title"])
    if na and nb and na != nb:
        return False, [], 0.0
    if a.get("published_at") and b.get("published_at"):
        delta = abs((datetime.fromisoformat(a["published_at"]) - datetime.fromisoformat(b["published_at"])).total_seconds())
        if delta > 14 * 86400:
            return False, [], 0.0
    proper = lambda value: {w.casefold() for w in re.findall(r"\b[A-Z][\w-]{2,}\b", value)} - STOP - BROAD
    pa, pb = proper(a["title"]), proper(b["title"])
    if not shared or (pa and pb and not pa & pb):
        return False, [], 0.0
    va, vb = (vectors or {}).get(text(a)), (vectors or {}).get(text(b))
    similarity = sum(x*y for x, y in zip(va, vb)) if va is not None and vb is not None else None
    overlap = len(shared) / max(1, min(len(at - BROAD), len(bt - BROAD)))
    accepted = (len(shared) >= 2 and overlap >= .35 and similarity is not None and similarity >= threshold
                or len(shared) >= 4 and overlap >= .65)
    signals = ["Shared headline terms: " + ", ".join(sorted(shared))]
    if similarity is not None:
        signals.append("Local text similarity supports this possible connection")
    else:
        signals.append("Conservative headline matching; semantic model unavailable or disabled")
    return accepted, signals, similarity if similarity is not None else overlap


class StoryGraph:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        with store.connect() as db:
            db.executescript(SCHEMA)
        self.embeddings = Embeddings(settings, store)

    def ingest(self, reader, articles):
        values = [a.model_dump(mode="json") for a in articles]
        with self.store.connect() as db:
            rows = db.execute("SELECT e.data FROM story_timeline_events e JOIN story_clusters s ON s.id=e.story_id "
                              "WHERE s.profile_id=? ORDER BY e.observed_at DESC LIMIT 300", (reader,)).fetchall()
        previous = [json.loads(row[0]) for row in rows]
        vectors = self.embeddings.encode([text(a) for a in values + previous])
        assignments = {}
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for article in values:
                candidates = []
                known = db.execute("SELECT a.story_id FROM story_articles a JOIN story_clusters s ON s.id=a.story_id "
                                   "WHERE s.profile_id=? AND a.url=? LIMIT 1", (reader, canonical_url(article['url']))).fetchone()
                for old in previous:
                    accepted, signals, score = match(article, old, vectors, self.settings.story_similarity_threshold)
                    if accepted:
                        candidates.append((score, old["story_id"], signals))
                if known:
                    story_id, signals = known[0], ['Same original article URL']
                elif candidates:
                    _, story_id, signals = max(candidates, key=lambda item: (item[0], item[1]))
                else:
                    story_id = str(uuid5(NAMESPACE_URL, reader + ":" + canonical_url(article["url"])))
                    signals = ["First source observation; no related coverage established"]
                assignments[article["id"]] = story_id
                observed = article["retrieved_at"]
                db.execute("INSERT INTO story_clusters VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                           "first_observed=MIN(first_observed,excluded.first_observed),last_observed=MAX(last_observed,excluded.last_observed)",
                           (story_id, reader, article["title"], observed, observed))
                db.execute("INSERT OR IGNORE INTO story_articles VALUES(?,?,?)", (story_id, article["id"], canonical_url(article["url"])))
                history = [old for old in previous if old["story_id"] == story_id]
                change = "New article observed."
                if history and article["source"] not in {old["source"] for old in history}:
                    change = "New source covering a possibly related event."
                elif any(canonical_url(old["url"]) == canonical_url(article["url"]) and text(old) != text(article) for old in history):
                    change = "Publisher headline or excerpt changed; this alone does not establish a factual correction."
                change += " Not enough source evidence to determine what changed."
                if history and len(article['description']) >= 100 and article['description'] not in {old['description'] for old in history}:
                    change = 'Newly observed source excerpt differs from earlier saved coverage. The quoted text is attributed reporting, not a verified change in facts.'
                event_id = hashlib.sha256((story_id + canonical_url(article["url"]) + text(article)).encode()).hexdigest()
                observation = {"story_id": story_id, "article_id": article["id"], "title": article["title"],
                               "url": article["url"], "source": article["source"], "description": article["description"],
                               "published_at": article["published_at"], "observed_at": observed,
                               "change": change, "signals": signals,
                               "association": "possibly_related" if candidates else "single_observation"}
                inserted = db.execute("INSERT OR IGNORE INTO story_timeline_events VALUES(?,?,?,?,?)",
                                     (event_id, story_id, article["id"], observed, json.dumps(observation))).rowcount
                if inserted:
                    previous.append(observation)
        return assignments

    def detail(self, reader, story_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM story_clusters WHERE id=? AND profile_id=?", (story_id, reader)).fetchone()
            if not row:
                raise KeyError("Story not found for this reader")
            events = db.execute("SELECT data FROM story_timeline_events WHERE story_id=? ORDER BY observed_at DESC,id DESC LIMIT 150", (story_id,)).fetchall()
            followed = bool(db.execute("SELECT 1 FROM reader_story_follows WHERE profile_id=? AND story_id=?", (reader, story_id)).fetchone())
        timeline = sorted([json.loads(e[0]) for e in events], key=lambda e: (datetime.fromisoformat(e['observed_at']), e['article_id']))
        return StoryDetail(**dict(row), followed=followed, timeline=timeline)

    def follow(self, reader, story_id, followed):
        self.detail(reader, story_id)
        from backend.services.provenance import utc_now
        with self.store.connect() as db:
            if followed:
                db.execute("INSERT OR IGNORE INTO reader_story_follows VALUES(?,?,?)", (reader, story_id, utc_now().isoformat()))
            else:
                db.execute("DELETE FROM reader_story_follows WHERE profile_id=? AND story_id=?", (reader, story_id))
        return self.detail(reader, story_id)

    def followed(self, reader):
        with self.store.connect() as db:
            return {row[0] for row in db.execute("SELECT story_id FROM reader_story_follows WHERE profile_id=?", (reader,))}

    def cutoff(self, reader):
        with self.store.connect() as db:
            row = db.execute("SELECT MAX(json_extract(snapshot,'$.generated_at')) FROM editions WHERE profile_id=?", (reader,)).fetchone()
        return row[0] if row else None

    def updates(self, reader, since=None):
        stories = []
        for story_id in sorted(self.followed(reader)):
            detail = self.detail(reader, story_id)
            timeline = [e for e in detail.timeline if since is None or datetime.fromisoformat(e.observed_at) > datetime.fromisoformat(since)]
            if timeline:
                stories.append(detail.model_copy(update={"timeline": timeline}))
        return StoryUpdates(since=since, stories=stories)

    def seen_articles(self, reader):
        with self.store.connect() as db:
            rows = db.execute("SELECT snapshot FROM editions WHERE profile_id=? ORDER BY local_date DESC,version DESC LIMIT 30", (reader,)).fetchall()
        return {a['id'] for row in rows for a in json.loads(row[0]).get('articles', [])}

    def snapshot(self, reader, ids):
        result = []
        for story_id in dict.fromkeys(ids):
            detail = self.detail(reader, story_id)
            if len(detail.timeline) > 1:
                result.append(detail.model_copy(update={"timeline": detail.timeline[-3:]}).model_dump(mode="json"))
            if len(result) == 3:
                break
        return result
