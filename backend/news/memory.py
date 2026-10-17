import re

UNTRUSTED_INSTRUCTIONS = re.compile(r"ignore (?:all|previous) (?:rules|instructions)|system prompt|api[_ -]?key|reveal (?:secrets|credentials)|execute (?:shell|code)", re.I)
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "u.s", "u.k"}


def first_source_sentence(text):
    text = text.strip()
    for match in re.finditer(r"[.!?](?=\s|$)", text):
        token = text[:match.start()].rsplit(" ", 1)[-1].lower()
        if token in ABBREVIATIONS or len(text[:match.end()]) < 35:
            continue
        return text[:match.end()]
    return text


def build_takeaways(articles):
    candidates = []
    for article in articles:
        description = article["description"].strip()
        if UNTRUSTED_INSTRUCTIONS.search(description + " " + article["title"]):
            continue
        normalize = lambda value: re.sub(r"\W+", " ", value.casefold()).strip()
        source_suffix = normalize(article["source"])
        description_body = normalize(description).removesuffix(source_suffix).strip()
        headline_body = normalize(article["title"]).removesuffix(source_suffix).strip()
        headline_only = len(description) < 35 or description_body == headline_body
        text = article["title"] if headline_only else first_source_sentence(description)
        candidates.append({"text": text, "article_id": article["id"], "source": article["source"],
                           "url": article["url"], "kind": "headline_only" if headline_only else "source_excerpt",
                           "limitation": "Headline-level evidence only." if headline_only else "Attributed source excerpt; not independently verified."})
    candidates.sort(key=lambda item: item["kind"] == "headline_only")
    selected, sources = [], set()
    for item in candidates:
        if item["source"] not in sources:
            selected.append(item)
            sources.add(item["source"])
        if len(selected) == 3:
            return selected
    return (selected + [item for item in candidates if item not in selected])[:3]
