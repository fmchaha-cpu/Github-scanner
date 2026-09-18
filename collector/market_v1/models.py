from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WarframeFounderListing(BaseModel):
    platform: str
    url: str
    title: str
    seller: str | None = None
    price_value: float | None = None
    currency: str | None = None
    observed_at: str = Field(default_factory=utcnow_iso)
    evidence_level: Literal["POTENTIAL_LEAD", "CLAIM_EVIDENCE"]
    founder_terms: list[str] = Field(default_factory=list)
    prime_items: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)
    evidence_score: float = 0.0
    detail_verified: bool = False
    alert_eligible: bool = False
    budget_fit: Literal["preferred", "above_preferred", "unknown"] = "unknown"
    safety_note: str = (
        "Listing text evidence only; ownership, transferability and authenticity are not verified."
    )


class ScanOutcome(BaseModel):
    game: str
    scan_id: str
    started_at: str
    finished_at: str
    sources_attempted: int
    listings_found: int
    alert_eligible: int
    errors: list[str] = Field(default_factory=list)
    listings: list[WarframeFounderListing] = Field(default_factory=list)
