import re
from backend.news.models import TOPICS


def primary_topic(article):
    title = article.get('title', '')
    scores = {topic: sum(bool(re.search(r'\b' + re.escape(term) + r'(?:s|es)?\b', title, re.I))
                         for term in info['terms']) for topic, info in TOPICS.items()}
    topic = max(scores, key=scores.get)
    return topic if scores[topic] else next(iter(article.get('topics') or ['world']))
