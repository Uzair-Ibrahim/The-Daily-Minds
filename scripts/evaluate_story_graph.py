"""Small synthetic development fixture, not research-grade accuracy or real news."""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import Settings
from backend.news.story_graph import StoryGraph, match, text, terms
from backend.news.store import Store


def run():
    pairs = json.loads((ROOT/'tests/fixtures/story_pairs.json').read_text())
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    records = []
    for pair in pairs:
        a = {'title': pair['a'], 'description': '', 'url': 'https://example.org/a', 'published_at': now.isoformat()}
        b = {'title': pair['b'], 'description': '', 'url': 'https://example.org/a' if pair.get('same_url') else 'https://example.org/b',
             'published_at': None if pair.get('missing_date') else (now+timedelta(days=pair.get('days', 1))).isoformat()}
        records.append((a,b,pair['same']))
    with tempfile.TemporaryDirectory() as temp:
        settings = Settings(_env_file=None, database_path=str(Path(temp)/'eval.sqlite3'))
        graph = StoryGraph(Store(settings.database_path), settings)
        start = perf_counter()
        vectors = graph.embeddings.encode([text(a) for a,b,_ in records]+[text(b) for a,b,_ in records])
        elapsed = perf_counter()-start
        results = {mode: {'tp':0,'fp':0,'tn':0,'fn':0} for mode in ['keyword_overlap_baseline','semantic_alone','hybrid']}
        errors = []
        for a,b,label in records:
            ta,tb = terms(a['title']),terms(b['title'])
            predictions = {'keyword_overlap_baseline': len(ta & tb)/max(1,len(ta | tb)) >= .35,
                           'semantic_alone': sum(x*y for x,y in zip(vectors.get(text(a),[]),vectors.get(text(b),[]))) >= settings.story_similarity_threshold,
                           'hybrid': match(a,b,vectors,settings.story_similarity_threshold)[0]}
            for mode,pred in predictions.items():
                results[mode]['tp' if pred and label else 'fp' if pred else 'fn' if label else 'tn'] += 1
                if bool(pred) != label:
                    errors.append({'mode':mode,'a':a['title'],'b':b['title'],'expected':label})
        for mode,counts in results.items():
            counts['precision'] = counts['tp']/max(1,counts['tp']+counts['fp'])
            counts['recall'] = counts['tp']/max(1,counts['tp']+counts['fn'])
        output = {'fixture':'Synthetic development set, not independent validation. Keyword overlap is a comparison baseline; no previous event matcher existed.',
                  'pairs':len(pairs), 'positive_support':sum(p['same'] for p in pairs), 'negative_support':sum(not p['same'] for p in pairs),
                  'model_status':graph.embeddings.status, 'embedding_seconds':round(elapsed,3), 'results':results, 'errors':errors}
    (ROOT/'artifacts').mkdir(exist_ok=True)
    (ROOT/'artifacts/story-evaluation.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2))


if __name__ == '__main__':
    run()
