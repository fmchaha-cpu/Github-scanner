-- Genshin Market Tracker v0.5: historical comparables, disappearance evidence,
-- relisting suggestions and persistent quality snapshots.
-- Safe to run more than once because it only creates new tables/indexes.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS listing_market_meta (
  listing_id INTEGER PRIMARY KEY,
  market_status TEXT NOT NULL DEFAULT 'ACTIVE_UNCONFIRMED',
  status_confidence REAL NOT NULL DEFAULT 0,
  status_evidence TEXT,
  status_updated_at TEXT NOT NULL,
  first_removed_at TEXT,
  relisting_fingerprint TEXT,
  limited_c6_characters_json TEXT,
  c6r1_characters_json TEXT,
  character_tags_json TEXT,
  discovery_paths_json TEXT,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_market_meta_status
  ON listing_market_meta(market_status, status_updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_meta_fingerprint
  ON listing_market_meta(relisting_fingerprint);

CREATE TABLE IF NOT EXISTS coverage_paths (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_run_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  query_family TEXT NOT NULL,
  query_text TEXT,
  page_label TEXT,
  path_key TEXT NOT NULL,
  status TEXT NOT NULL,
  result_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  observed_at TEXT NOT NULL,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_coverage_paths_run
  ON coverage_paths(scan_run_id, path_key);
CREATE INDEX IF NOT EXISTS idx_coverage_paths_time
  ON coverage_paths(observed_at DESC);

CREATE TABLE IF NOT EXISTS listing_seen_paths (
  listing_id INTEGER NOT NULL,
  scan_run_id TEXT NOT NULL,
  path_key TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  PRIMARY KEY(listing_id, scan_run_id, path_key),
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_seen_paths_run_path
  ON listing_seen_paths(scan_run_id, path_key);

CREATE TABLE IF NOT EXISTS listing_path_state (
  listing_id INTEGER NOT NULL,
  path_key TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  last_checked TEXT NOT NULL,
  miss_count INTEGER NOT NULL DEFAULT 0,
  last_result TEXT NOT NULL DEFAULT 'seen',
  PRIMARY KEY(listing_id, path_key),
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_path_state_misses
  ON listing_path_state(miss_count, last_checked DESC);

CREATE TABLE IF NOT EXISTS listing_status_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  old_status TEXT,
  new_status TEXT NOT NULL,
  confidence REAL,
  evidence TEXT,
  scan_run_id TEXT,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_status_events_listing
  ON listing_status_events(listing_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_status_events_time
  ON listing_status_events(created_at DESC);

CREATE TABLE IF NOT EXISTS historical_annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER,
  listing_url TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL,
  evidence TEXT,
  notes TEXT,
  reviewer TEXT NOT NULL DEFAULT 'manual',
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_historical_annotations_time
  ON historical_annotations(created_at DESC);


CREATE TABLE IF NOT EXISTS historical_offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_key TEXT NOT NULL UNIQUE,
  provenance TEXT NOT NULL,
  platform TEXT,
  external_id TEXT,
  url TEXT,
  title TEXT NOT NULL,
  seller TEXT,
  server TEXT,
  ar INTEGER,
  price_value REAL NOT NULL,
  currency TEXT NOT NULL,
  market_status TEXT NOT NULL,
  status_confidence REAL NOT NULL DEFAULT 0,
  status_evidence TEXT,
  observed_at TEXT NOT NULL,
  limited_c6_count INTEGER NOT NULL DEFAULT 0,
  c6r1_count INTEGER NOT NULL DEFAULT 0,
  limited_pulls REAL,
  history_richness REAL,
  discovery_headroom REAL,
  resource_richness REAL,
  legacy_collector_value REAL,
  archetypes_json TEXT,
  limited_c6_characters_json TEXT,
  c6r1_characters_json TEXT,
  character_tags_json TEXT,
  risk_hits INTEGER NOT NULL DEFAULT 0,
  relisting_fingerprint TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_historical_offers_status
  ON historical_offers(market_status, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_historical_offers_market
  ON historical_offers(server, currency, price_value);
CREATE INDEX IF NOT EXISTS idx_historical_offers_fingerprint
  ON historical_offers(relisting_fingerprint);

CREATE TABLE IF NOT EXISTS quality_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_run_id TEXT,
  created_at TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  suggestions_json TEXT NOT NULL,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_quality_snapshots_time
  ON quality_snapshots(created_at DESC);
