from backend.news.models import ProfileInput
from backend.news.ranking import rank_articles
from scripts.personalization_proof import PROFILES
from tests.test_newspaper import make_article


def test_requested_profiles_use_actual_specific_signals():
    candidates = [make_article(topic, index) for index, topic in enumerate(["technology", "business", "science", "world", "sports"])]
    candidates[0].title = "TEST AI software engineering and startups report"
    candidates[2].title = "TEST climate health research report"
    results = {key: rank_articles(candidates, ProfileInput(**values).model_dump(), []) for key, values in PROFILES.items()}
    assert results["A"][0]["id"] == candidates[0].id
    assert results["B"][0]["id"] == candidates[2].id
    assert results["A"][0]["breakdown"]["custom_interests"] == 6
    assert results["B"][0]["breakdown"]["custom_interests"] == 4
