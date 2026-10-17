import json
import sqlite3
from datetime import timedelta
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from backend.news.models import Article, ProfileInput
from backend.services.provenance import utc_now


class Store:
    def __init__(self, path: str, database_url="", schema="daily_mind"):
        self.database_url, self.schema = database_url, schema
        self._postgres_initialized = False
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS articles(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS interactions(profile_id TEXT NOT NULL, article_id TEXT NOT NULL, action TEXT NOT NULL,
                    topics TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(profile_id,article_id,action));
                CREATE TABLE IF NOT EXISTS editions(id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, local_date TEXT NOT NULL,
                    version INTEGER NOT NULL, snapshot TEXT NOT NULL, UNIQUE(profile_id,local_date,version));
                CREATE INDEX IF NOT EXISTS editions_reader ON editions(profile_id,local_date);
                CREATE TABLE IF NOT EXISTS generation_leases(profile_id TEXT NOT NULL, local_date TEXT NOT NULL,
                    owner TEXT NOT NULL, expires_at REAL NOT NULL, PRIMARY KEY(profile_id,local_date));
                CREATE TABLE IF NOT EXISTS article_image_enrichment(article_id TEXT NOT NULL, article_url TEXT NOT NULL,
                    metadata TEXT NOT NULL, expires_at REAL NOT NULL, PRIMARY KEY(article_id,article_url));
            """)

    @contextmanager
    def connect(self):
        if self.database_url:
            from backend.news.postgres import Connection
            db = Connection(self.database_url, self.schema, initialize=not self._postgres_initialized)
        else:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
            self._postgres_initialized = True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def profile(self, profile_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            return self.save_profile(profile_id, ProfileInput(onboarded=False))
        return {"id": profile_id, **json.loads(row["data"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def save_profile(self, profile_id, profile):
        now = utc_now().isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO profiles VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
                       (profile_id, profile.model_dump_json(), now, now))
        return self.profile(profile_id)

    def articles(self, articles):
        with self.connect() as db:
            db.executemany("INSERT INTO articles VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                           [(article.id, article.model_dump_json()) for article in articles])

    def events(self, profile_id):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM interactions WHERE profile_id=? ORDER BY created_at", (profile_id,)).fetchall()
        return [{**dict(row), "topics": json.loads(row["topics"])} for row in rows]

    def interact(self, profile_id, article_id, action, active=True):
        with self.connect() as db:
            row = db.execute("SELECT value FROM editions JOIN json_each(editions.snapshot,'$.articles') WHERE profile_id=? AND json_extract(value,'$.id')=? ORDER BY local_date DESC,version DESC LIMIT 1",
                             (profile_id, article_id)).fetchone()
            if not row:
                raise KeyError("Article does not belong to this reader's editions")
            article = json.loads(row["value"])
            if not active:
                if action not in {'liked', 'saved'}:
                    raise ValueError('Only likes and saves are reversible')
                cursor = db.execute('DELETE FROM interactions WHERE profile_id=? AND article_id=? AND action=?',
                                    (profile_id, article_id, action))
                return cursor.rowcount > 0
            cursor = db.execute("INSERT OR IGNORE INTO interactions VALUES(?,?,?,?,?)",
                                (profile_id, article_id, action, json.dumps(article["topics"]), utc_now().isoformat()))
            return cursor.rowcount > 0

    def engagement(self, profile_id, article_id):
        with self.connect() as db:
            actions = {row['action'] for row in db.execute('SELECT action FROM interactions WHERE profile_id=? AND article_id=?',
                                                          (profile_id, article_id))}
        return {'article_id': article_id, 'liked': 'liked' in actions, 'saved': 'saved' in actions,
                'like_count': int('liked' in actions), 'like_count_scope': 'your_local_reader'}

    def reading_list(self, profile_id):
        result = []
        for event in self.events(profile_id):
            if event['action'] != 'saved':
                continue
            with self.connect() as db:
                row = db.execute("SELECT editions.id,value FROM editions JOIN json_each(editions.snapshot,'$.articles') "
                    "WHERE profile_id=? AND json_extract(value,'$.id')=? ORDER BY local_date DESC,version DESC LIMIT 1",
                    (profile_id, event['article_id'])).fetchone()
            if row:
                result.append({'edition_id': row['id'], 'article': json.loads(row['value']),
                               **self.engagement(profile_id, event['article_id'])})
        return result

    def image_enrichment(self, article_id, article_url, now):
        with self.connect() as db:
            row = db.execute('SELECT metadata FROM article_image_enrichment WHERE article_id=? AND article_url=? AND expires_at>?',
                             (article_id, article_url, now)).fetchone()
        return json.loads(row['metadata']) if row else None

    def save_image_enrichment(self, article, metadata, expires_at):
        with self.connect() as db:
            db.execute('INSERT INTO article_image_enrichment VALUES(?,?,?,?) ON CONFLICT(article_id,article_url) '
                'DO UPDATE SET metadata=excluded.metadata,expires_at=excluded.expires_at',
                (article['id'], article['url'], json.dumps(metadata), expires_at))

    def reset_feedback(self, profile_id):
        with self.connect() as db:
            db.execute("DELETE FROM interactions WHERE profile_id=?", (profile_id,))

    def onboarded_readers(self):
        with self.connect() as db:
            return [row['id'] for row in db.execute(
                "SELECT id FROM profiles WHERE json_extract(data,'$.onboarded')=1 ORDER BY created_at")]

    def cached_articles(self, now, max_age_days):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM articles ORDER BY json_extract(data,'$.retrieved_at') DESC LIMIT 500").fetchall()
        articles = []
        for row in rows:
            try:
                article = Article.model_validate_json(row['data'])
                if (article.provenance == 'rss_excerpt' and article.retrieved_at.tzinfo is not None
                    and now - timedelta(days=max_age_days) <= article.retrieved_at <= now):
                    articles.append(article)
            except ValueError:
                continue
        return sorted(articles, key=lambda item: item.retrieved_at, reverse=True)[:150]

    def claim_generation(self, profile_id, local_date, owner, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT owner,expires_at FROM generation_leases WHERE profile_id=? AND local_date=?',
                             (profile_id, local_date)).fetchone()
            if row and row['expires_at'] > now:
                return 'busy' if row['owner'] else 'cooldown'
            db.execute('INSERT INTO generation_leases VALUES(?,?,?,?) ON CONFLICT(profile_id,local_date) '
                       'DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at',
                       (profile_id, local_date, owner, now + 120))
        return 'claimed'

    def finish_generation(self, profile_id, local_date, owner, retry_at=None):
        with self.connect() as db:
            if retry_at is None:
                db.execute('DELETE FROM generation_leases WHERE profile_id=? AND local_date=? AND owner=?',
                           (profile_id, local_date, owner))
            else:
                db.execute("UPDATE generation_leases SET owner='',expires_at=? WHERE profile_id=? AND local_date=? AND owner=?",
                           (retry_at, profile_id, local_date, owner))

    def latest(self, profile_id, local_date):
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM editions WHERE profile_id=? AND local_date=? ORDER BY version DESC LIMIT 1", (profile_id, local_date)).fetchone()
        return json.loads(row["snapshot"]) if row else None

    def edition(self, profile_id, edition_id):
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM editions WHERE profile_id=? AND id=?", (profile_id, edition_id)).fetchone()
        if not row:
            raise KeyError("Edition not found for this reader")
        return json.loads(row["snapshot"])

    def archive(self, profile_id):
        with self.connect() as db:
            rows = db.execute("SELECT snapshot FROM editions WHERE profile_id=? ORDER BY local_date DESC,version DESC LIMIT 100", (profile_id,)).fetchall()
        return [{key: item[key] for key in ("id", "title", "local_date", "version", "generated_at", "status", "article_count")} for item in (json.loads(row["snapshot"]) for row in rows)]

    def save_edition(self, profile_id, local_date, snapshot, regenerate):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT version,snapshot FROM editions WHERE profile_id=? AND local_date=? ORDER BY version DESC LIMIT 1", (profile_id, local_date)).fetchone()
            if row and not regenerate:
                return json.loads(row["snapshot"])
            snapshot = {**snapshot, "id": str(uuid4()), "version": row["version"] + 1 if row else 1}
            db.execute("INSERT INTO editions VALUES(?,?,?,?,?)", (snapshot["id"], profile_id, local_date, snapshot["version"], json.dumps(snapshot)))
        return snapshot
