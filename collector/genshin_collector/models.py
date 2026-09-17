from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ListingObservation(BaseModel):
    platform: str
    external_id: Optional[str] = None
    url: str
    title: str
    seller: Optional[str] = None
    server: Optional[str] = None
    ar: Optional[int] = None
    price_value: Optional[float] = None
    currency: Optional[str] = None
    availability: Optional[str] = None
    instant_delivery: bool = False
    after_sale_protection: Optional[str] = None
    observed_at: str = Field(default_factory=utcnow_iso)
    raw_text: Optional[str] = None
    raw_hash: Optional[str] = None
    data_confidence: Optional[float] = None
    security_hint: Optional[float] = None

    limited_c6_count: int = 0
    c6r1_count: int = 0
    multi_c6: bool = False
    limited_c6_characters: list[str] = Field(default_factory=list)
    c6r1_characters: list[str] = Field(default_factory=list)
    character_tags: list[str] = Field(default_factory=list)

    primogems: Optional[int] = None
    intertwined: Optional[int] = None
    limited_pulls: Optional[float] = None

    legacy_hits: int = 0
    history_hits: int = 0
    discovery_hits: int = 0
    resource_hits: int = 0
    manufactured_hits: int = 0
    risk_hits: int = 0
    old_alt_hits: int = 0

    favorite_character_names: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)

    archetype: Optional[str] = None
    archetypes: list[str] = Field(default_factory=list)
    history_richness: Optional[float] = None
    discovery_headroom: Optional[float] = None
    resource_richness: Optional[float] = None
    organic_account_feel: Optional[float] = None
    legacy_collector_value: Optional[float] = None
    favorite_character_fit: Optional[float] = None
    personal_experience_fit: Optional[float] = None

    identity_verified: bool = False
    strict_live: bool = False
    verification_level: str = "card"
    extraction_quality: Optional[float] = None
    detail_verified_at: Optional[str] = None

    # v0.5 market-history / comparable metadata. These are evidence labels,
    # never guarantees that a transaction actually settled at the listed price.
    market_status: str = "ACTIVE_UNCONFIRMED"
    status_confidence: float = 0.0
    status_evidence: Optional[str] = None
    discovery_paths: list[str] = Field(default_factory=list)
    relisting_fingerprint: Optional[str] = None

    collector_priority: float = 0.0
    detector_reason: Optional[str] = None
    is_candidate: bool = False
    # Means "eligible for human/ChatGPT deep review", never an autonomous buy alert.
    is_alert_candidate: bool = False
    detector_version: str = "v1"


class CoverageRow(BaseModel):
    platform: str
    query_family: str
    query_text: Optional[str] = None
    page_label: Optional[str] = None
    path_key: Optional[str] = None
    status: str
    result_count: int = 0
    error: Optional[str] = None
    observed_at: str = Field(default_factory=utcnow_iso)
