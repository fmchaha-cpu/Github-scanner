from pathlib import Path
import sqlite3


def test_v05_migrations_apply_on_fresh_schema():
    root = Path(__file__).resolve().parents[2] / "cloudflare"
    db = sqlite3.connect(":memory:")
    for rel in ["schema.sql", "migrations/0002_quality_feedback.sql", "migrations/0003_historical_comparables.sql"]:
        db.executescript((root / rel).read_text(encoding="utf-8"))

    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {
        "listing_market_meta", "listing_path_state", "listing_seen_paths", "coverage_paths",
        "listing_status_events", "historical_offers", "historical_annotations", "quality_snapshots",
    }
    assert required <= tables

    market_cols = {r[1] for r in db.execute("PRAGMA table_info(listing_market_meta)")}
    assert {"market_status", "relisting_fingerprint", "character_tags_json", "discovery_paths_json"} <= market_cols


def test_historical_offer_source_key_is_unique():
    root = Path(__file__).resolve().parents[2] / "cloudflare"
    db = sqlite3.connect(":memory:")
    for rel in ["schema.sql", "migrations/0002_quality_feedback.sql", "migrations/0003_historical_comparables.sql"]:
        db.executescript((root / rel).read_text(encoding="utf-8"))
    cols = "source_key,provenance,title,price_value,currency,market_status,status_confidence,observed_at"
    vals = ("hist-1", "test", "x", 100, "EUR", "SOLD_CONFIRMED", .9, "2026-01-01T00:00:00Z")
    db.execute(f"INSERT INTO historical_offers({cols}) VALUES (?,?,?,?,?,?,?,?)", vals)
    try:
        db.execute(f"INSERT INTO historical_offers({cols}) VALUES (?,?,?,?,?,?,?,?)", vals)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("source_key should prevent duplicate historical imports")
