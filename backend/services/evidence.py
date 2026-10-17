from backend.schemas import EvidenceRecord


def evidence_limitations(records: list[EvidenceRecord]) -> list[str]:
    warnings = ["Search snippets are untrusted source excerpts; citations establish traceability, not verified truth.",
                "Source authority and conflicts have not been automatically verified; excerpts may disagree."]
    if any(item.published_at_utc is None for item in records):
        warnings.append("Publication dates are unknown for some sources. Retrieval time does not establish recency.")
    return warnings
