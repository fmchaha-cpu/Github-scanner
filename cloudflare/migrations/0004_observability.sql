PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS coverage_diagnostics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_run_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  path_key TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  fetch_mode TEXT,
  http_status INTEGER,
  elapsed_ms INTEGER,
  html_bytes INTEGER,
  text_chars INTEGER,
  anchor_count INTEGER,
  detail_link_count INTEGER,
  parsed_count INTEGER,
  page_title TEXT,
  content_hash TEXT,
  blocked_signals_json TEXT,
  sample_detail_urls_json TEXT,
  fallback_reason TEXT,
  parser_strategy TEXT,
  final_url TEXT,
  unmatched_listing_like_count INTEGER,
  sample_unmatched_listing_like_urls_json TEXT,
  http_probe_html_bytes INTEGER,
  http_probe_text_chars INTEGER,
  http_probe_detail_link_count INTEGER,
  http_probe_content_hash TEXT,
  http_probe_blocked_signals_json TEXT,
  http_probe_final_url TEXT,
  http_probe_unmatched_listing_like_count INTEGER,
  http_probe_sample_unmatched_listing_like_urls_json TEXT,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_coverage_diag_time ON coverage_diagnostics(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_coverage_diag_platform_time ON coverage_diagnostics(platform, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_coverage_diag_run_path ON coverage_diagnostics(scan_run_id, path_key);
CREATE INDEX IF NOT EXISTS idx_coverage_diag_hash ON coverage_diagnostics(platform, content_hash);

CREATE TABLE IF NOT EXISTS listing_verification_meta (
  listing_id INTEGER PRIMARY KEY,
  updated_at TEXT NOT NULL,
  verification_reason TEXT,
  parser_strategy TEXT,
  detail_fetch_mode TEXT,
  detail_fetch_fallback_reason TEXT,
  detail_http_status INTEGER,
  detail_html_bytes INTEGER,
  detail_blocked_signals_json TEXT,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_listing_verification_reason ON listing_verification_meta(verification_reason, updated_at DESC);

CREATE TABLE IF NOT EXISTS verification_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_run_id TEXT NOT NULL,
  listing_id INTEGER NOT NULL,
  platform TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  verification_reason TEXT,
  fetch_mode TEXT,
  fallback_reason TEXT,
  http_status INTEGER,
  html_bytes INTEGER,
  blocked_signals_json TEXT,
  identity_verified INTEGER NOT NULL DEFAULT 0,
  strict_live INTEGER NOT NULL DEFAULT 0,
  extraction_quality REAL,
  quality_flags_json TEXT,
  FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verification_events_time ON verification_events(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_verification_events_platform_time ON verification_events(platform, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_verification_events_reason_time ON verification_events(verification_reason, observed_at DESC);
