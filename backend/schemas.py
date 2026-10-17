from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, AwareDatetime, StringConstraints, model_validator

Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Status = Literal["ok", "partial", "no_evidence", "provider_unavailable", "error"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AskRequest(StrictModel):
    question: Query
    live: bool = True
    use_cache: bool = False
    max_sources: int = Field(default=5, ge=1, le=8, strict=True)


class SearchRequest(StrictModel):
    query: Query
    max_results: int = Field(default=5, ge=1, le=8, strict=True)


class EvidenceRecord(StrictModel):
    id: str
    title: str = Field(max_length=300)
    url: HttpUrl
    snippet: str = Field(min_length=1, max_length=3000)
    source_type: Literal["web_search"] = "web_search"
    retrieved_at_utc: AwareDatetime
    published_at_utc: AwareDatetime | None = None
    is_official_source: bool | None = None
    relevance_score: float | None = Field(default=None, ge=0, le=1)


class SearchResult(StrictModel):
    status: Status
    evidence: list[EvidenceRecord] = Field(default_factory=list, max_length=8)
    queried_at_utc: AwareDatetime
    retrieved_at_utc: AwareDatetime | None = None
    error_code: str | None = None
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_status(self):
        if self.status in {"ok", "partial"} and not self.evidence:
            raise ValueError("Successful search requires evidence")
        if self.evidence and self.retrieved_at_utc is None:
            raise ValueError("Evidence requires an actual retrieval timestamp")
        if self.status in {"no_evidence", "provider_unavailable", "error"} and self.evidence:
            raise ValueError("Failure status must not contain usable evidence")
        return self


class AskResponse(StrictModel):
    answer: str
    mode: Literal["extractive"] = "extractive"
    status: Status
    citations: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    queried_at_utc: AwareDatetime
    retrieved_at_utc: AwareDatetime | None = None
    freshness: Literal["retrieved_now_publication_date_unknown", "retrieved_now", "not_retrieved", "cached_within_ttl"]
    limitations: list[str] = Field(default_factory=list)
    elapsed_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_citations(self):
        ids = [item.id for item in self.evidence]
        if len(ids) != len(set(ids)) or not set(self.citations).issubset(ids):
            raise ValueError("Citations must reference unique supplied evidence IDs")
        return self
