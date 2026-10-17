"""Optional CPU embeddings. Runtime is offline; model setup is an explicit action."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from threading import RLock

_lock = RLock()


@lru_cache(maxsize=2)
def load_model(name, cache):
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(4)
    return SentenceTransformer(name, device="cpu", cache_folder=cache,
                               local_files_only=True, trust_remote_code=False)


class Embeddings:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.status = "disabled" if not settings.story_semantic_enabled else "not_loaded"

    def encode(self, texts):
        if not self.settings.story_semantic_enabled or not texts:
            return {}
        # Avoid importing torch at all on installations without a downloaded model.
        cache = Path(self.settings.story_model_cache)
        if not cache.exists():
            self.status = "model_unavailable"
            return {}
        try:
            with _lock:
                keys = {text: hashlib.sha256((self.settings.story_embedding_model + "\0" + text).encode()).hexdigest()
                        for text in dict.fromkeys(texts)}
                result = {}
                with self.store.connect() as db:
                    for text, key in keys.items():
                        row = db.execute("SELECT vector FROM story_embeddings WHERE id=?", (key,)).fetchone()
                        if row:
                            result[text] = json.loads(row[0])
                missing = [text for text in keys if text not in result]
                if missing:
                    model = load_model(self.settings.story_embedding_model, str(cache))
                    vectors = model.encode(missing, batch_size=24, normalize_embeddings=True,
                                           show_progress_bar=False).tolist()
                    with self.store.connect() as db:
                        for text, vector in zip(missing, vectors):
                            result[text] = vector
                            db.execute("INSERT OR IGNORE INTO story_embeddings VALUES(?,?)",
                                       (keys[text], json.dumps(vector)))
                self.status = "local_semantic"
                return result
        except Exception:
            self.status = "model_unavailable"
            return {}
