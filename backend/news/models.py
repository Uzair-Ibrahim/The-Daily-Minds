from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

TOPICS = {
    "technology": {"label": "Technology & AI", "terms": ["ai", "artificial intelligence", "technology", "software", "computer", "openai", "chip", "digital", "robot", "tech"]},
    "world": {"label": "World affairs", "terms": ["world", "election", "government", "war", "president", "diplomacy", "united nations", "politics"]},
    "pakistan": {"label": "Pakistan", "terms": ["pakistan", "pakistani", "karachi", "islamabad", "lahore", "sindh", "punjab"]},
    "business": {"label": "Business & economy", "terms": ["business", "economy", "market", "stock", "finance", "bank", "trade", "inflation", "company", "startup"]},
    "science": {"label": "Science & discovery", "terms": ["science", "research", "study", "space", "nasa", "climate", "scientist", "physics", "health", "discovery"]},
    "sports": {"label": "Sport", "terms": ["sport", "football", "cricket", "tennis", "match", "league", "tournament", "olympic", "rugby"]},
    "culture": {"label": "Culture & ideas", "terms": ["culture", "art", "music", "film", "book", "literature", "museum", "design", "artist", "cinema"]},
}


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: dict[str, float] = Field(default_factory=lambda: {"technology": 1, "world": 1, "science": 1}, max_length=7)
    keywords: list[str] = Field(default_factory=list, max_length=8)
    locale: str = Field(default="", max_length=60)
    language: Literal["en"] = "en"
    depth: Literal["brief", "balanced", "deep"] = "balanced"
    edition_length: int = Field(default=8, ge=4, le=16)
    timezone: str = "Asia/Karachi"
    onboarded: bool = True

    @field_validator("topics")
    @classmethod
    def valid_topics(cls, value):
        if not value or any(key not in TOPICS or not 0.1 <= weight <= 3 for key, weight in value.items()):
            raise ValueError("Choose at least one supported topic with weight 0.1–3")
        return value

    @field_validator("keywords")
    @classmethod
    def valid_keywords(cls, value):
        value = list(dict.fromkeys(word.strip() for word in value if word.strip()))
        if any(len(word) > 60 for word in value):
            raise ValueError("Custom interests must be at most 60 characters")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown timezone")
        return value


class Article(BaseModel):
    id: str
    url: HttpUrl
    title: str = Field(max_length=300)
    source: str
    origin: str
    description: str = Field(max_length=450)
    published_at: datetime | None = None
    retrieved_at: datetime
    topics: list[str]
    provenance: Literal["rss_excerpt", "exa_excerpt", "tavily_excerpt"] = "rss_excerpt"
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)
    breakdown: dict[str, float] = Field(default_factory=dict)


class GenerateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regenerate: bool = False
    targeted_search: bool = False


class InteractionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["opened", "skipped", "liked", "saved", "not_interested"]


class NewsSearchResult(BaseModel):
    status: Literal["ok", "no_live_data", "error"]
    articles: list[Article] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    cached: bool = False


def reader_id(value: str) -> str:
    return str(UUID(value))
