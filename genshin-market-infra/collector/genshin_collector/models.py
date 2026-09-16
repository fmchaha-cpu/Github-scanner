from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


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
    primogems: Optional[int] = None
    intertwined: Optional[int] = None
    limited_pulls: Optional[float] = None
    legacy_hits: int = 0
    history_hits: int = 0
    discovery_hits: int = 0
    resource_hits: int = 0
    archetype: Optional[str] = None
    history_richness: Optional[float] = None
    discovery_headroom: Optional[float] = None
    resource_richness: Optional[float] = None
    organic_account_feel: Optional[float] = None
    legacy_collector_value: Optional[float] = None
    personal_experience_fit: Optional[float] = None
    collector_priority: float = 0.0
    detector_reason: Optional[str] = None
    is_candidate: bool = False
    is_alert_candidate: bool = False
    detector_version: str = "v1"


class CoverageRow(BaseModel):
    platform: str
    query_family: str
    query_text: Optional[str] = None
    page_label: Optional[str] = None
    status: str
    result_count: int = 0
    error: Optional[str] = None
    observed_at: str = Field(default_factory=utcnow_iso)
