from backend.schemas import EvidenceRecord


def extractive_answer(records: list[EvidenceRecord]) -> str:
    if not records:
        return "No usable evidence was retrieved; unable to verify an answer."
    excerpts = "\n\n".join(f"[{item.id}] {item.snippet}" for item in records)
    return "Extractive baseline (no LLM synthesis). Unverified source excerpts follow:\n\n" + excerpts
