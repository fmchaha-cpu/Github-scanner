PRAGMA foreign_keys = ON;

-- v0.7: add diagnostics without ALTER TABLE so upgrading existing D1 databases stays safe/idempotent.
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
