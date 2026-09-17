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


def test_v06_observability_migration_applies_and_has_diagnostics_columns():
    root = Path(__file__).resolve().parents[2] / "cloudflare"
    db = sqlite3.connect(":memory:")
    for rel in [
        "schema.sql", "migrations/0002_quality_feedback.sql", "migrations/0003_historical_comparables.sql",
        "migrations/0004_observability.sql",
    ]:
        db.executescript((root / rel).read_text(encoding="utf-8"))
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"coverage_diagnostics", "listing_verification_meta", "verification_events"} <= tables
    cols = {r[1] for r in db.execute("PRAGMA table_info(coverage_diagnostics)")}
    assert {
        "detail_link_count", "parsed_count", "content_hash", "blocked_signals_json", "fallback_reason",
        "http_probe_detail_link_count", "http_probe_content_hash", "http_probe_blocked_signals_json",
        "final_url", "unmatched_listing_like_count", "sample_unmatched_listing_like_urls_json",
        "http_probe_final_url", "http_probe_unmatched_listing_like_count",
    } <= cols
    verification_cols = {r[1] for r in db.execute("PRAGMA table_info(listing_verification_meta)")}
    assert {
        "verification_reason", "parser_strategy", "detail_fetch_mode", "detail_fetch_fallback_reason",
        "detail_http_status", "detail_html_bytes", "detail_blocked_signals_json",
    } <= verification_cols
    event_cols = {r[1] for r in db.execute("PRAGMA table_info(verification_events)")}
    assert {
        "scan_run_id", "listing_id", "platform", "verification_reason", "fetch_mode", "fallback_reason",
        "identity_verified", "strict_live", "extraction_quality", "quality_flags_json",
    } <= event_cols
