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

-- v0.7 source-health and field-provenance tables (also applied by migration 0005).
CREATE TABLE IF NOT EXISTS coverage_diagnostics_v07_extra (
  scan_run_id TEXT NOT NULL,
  path_key TEXT NOT NULL,
  http_probe_http_status INTEGER,
  safe_headers_json TEXT,
  http_probe_safe_headers_json TEXT,
  browser_early_blocked INTEGER NOT NULL DEFAULT 0,
  circuit_breaker_triggered INTEGER NOT NULL DEFAULT 0,
  circuit_breaker_reason TEXT,
  PRIMARY KEY(scan_run_id, path_key),
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cov_diag_v07_breaker ON coverage_diagnostics_v07_extra(circuit_breaker_triggered, scan_run_id);

CREATE TABLE IF NOT EXISTS listing_field_provenance (
  listing_id INTEGER PRIMARY KEY,
  updated_at TEXT NOT NULL,
  field_sources_json TEXT NOT NULL,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verification_provenance_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_run_id TEXT NOT NULL,
  listing_id INTEGER NOT NULL,
  platform TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  verification_reason TEXT,
  field_sources_json TEXT NOT NULL,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_verification_prov_time ON verification_provenance_events(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_verification_prov_platform ON verification_provenance_events(platform, observed_at DESC);

CREATE TABLE IF NOT EXISTS source_health_state (
  platform TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'unknown',
  consecutive_blocked INTEGER NOT NULL DEFAULT 0,
  consecutive_zero_yield INTEGER NOT NULL DEFAULT 0,
  last_success_at TEXT,
  last_blocked_at TEXT,
  last_probe_at TEXT,
  cooldown_until TEXT,
  last_reason TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_health_cooldown ON source_health_state(cooldown_until);

-- v1.0 multi-game extension. Warframe data is kept physically separate from Genshin.
CREATE TABLE IF NOT EXISTS warframe_founder_scans (
  id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
  sources_attempted INTEGER NOT NULL DEFAULT 0, listings_found INTEGER NOT NULL DEFAULT 0,
  alert_eligible INTEGER NOT NULL DEFAULT 0, errors_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS warframe_founder_listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL, seller TEXT, price_value REAL, currency TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, evidence_level TEXT NOT NULL,
  founder_terms_json TEXT NOT NULL DEFAULT '[]', prime_items_json TEXT NOT NULL DEFAULT '[]',
  evidence_snippets_json TEXT NOT NULL DEFAULT '[]', evidence_score REAL NOT NULL DEFAULT 0,
  detail_verified INTEGER NOT NULL DEFAULT 0, alert_eligible INTEGER NOT NULL DEFAULT 0,
  budget_fit TEXT NOT NULL DEFAULT 'unknown', safety_note TEXT NOT NULL, last_scan_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wf_founder_recent ON warframe_founder_listings(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_wf_founder_alert ON warframe_founder_listings(alert_eligible,evidence_score DESC,last_seen DESC);
CREATE TABLE IF NOT EXISTS warframe_founder_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, scan_id TEXT NOT NULL,
  observed_at TEXT NOT NULL, evidence_level TEXT NOT NULL, evidence_score REAL NOT NULL,
  alert_eligible INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(listing_id) REFERENCES warframe_founder_listings(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_wf_founder_events_time ON warframe_founder_events(observed_at DESC);
