PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS scan_runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  collector_version TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  source_count INTEGER NOT NULL DEFAULT 0,
  listing_count INTEGER NOT NULL DEFAULT 0,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS coverage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_run_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  query_family TEXT NOT NULL,
  query_text TEXT,
  page_label TEXT,
  status TEXT NOT NULL,
  result_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  observed_at TEXT NOT NULL,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_coverage_run ON coverage(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_coverage_platform_time ON coverage(platform, observed_at DESC);

CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  external_id TEXT,
  url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  seller TEXT,
  server TEXT,
  ar INTEGER,
  price_value REAL,
  currency TEXT,
  availability TEXT,
  instant_delivery INTEGER,
  after_sale_protection TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  last_changed TEXT NOT NULL,
  raw_text TEXT,
  raw_hash TEXT,
  data_confidence REAL,
  security_hint REAL,
  limited_c6_count INTEGER NOT NULL DEFAULT 0,
  c6r1_count INTEGER NOT NULL DEFAULT 0,
  multi_c6 INTEGER NOT NULL DEFAULT 0,
  primogems INTEGER,
  intertwined INTEGER,
  limited_pulls REAL,
  legacy_hits INTEGER NOT NULL DEFAULT 0,
  history_hits INTEGER NOT NULL DEFAULT 0,
  discovery_hits INTEGER NOT NULL DEFAULT 0,
  resource_hits INTEGER NOT NULL DEFAULT 0,
  archetype TEXT,
  history_richness REAL,
  discovery_headroom REAL,
  resource_richness REAL,
  organic_account_feel REAL,
  legacy_collector_value REAL,
  personal_experience_fit REAL,
  collector_priority REAL,
  detector_reason TEXT,
  is_candidate INTEGER NOT NULL DEFAULT 0,
  is_alert_candidate INTEGER NOT NULL DEFAULT 0,
  last_scan_run_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_listings_platform_external ON listings(platform, external_id);
CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_listings_candidate ON listings(is_candidate, collector_priority DESC, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_listings_eu_price ON listings(server, price_value);

CREATE TABLE IF NOT EXISTS listing_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL,
  observed_at TEXT NOT NULL,
  price_value REAL,
  currency TEXT,
  availability TEXT,
  seller TEXT,
  raw_hash TEXT,
  raw_text TEXT,
  changed INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_snapshots_listing_time ON listing_snapshots(listing_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS candidate_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL,
  scan_run_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  priority REAL NOT NULL,
  reason TEXT NOT NULL,
  event_type TEXT NOT NULL DEFAULT 'detected',
  detector_version TEXT,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_candidate_events_time ON candidate_events(created_at DESC);

CREATE TABLE IF NOT EXISTS system_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  component TEXT NOT NULL,
  severity TEXT NOT NULL,
  code TEXT,
  message TEXT NOT NULL,
  details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_system_events_time ON system_events(created_at DESC);
