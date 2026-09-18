-- v1.0: Warframe Founder evidence is intentionally separate from Genshin scoring/history.
CREATE TABLE IF NOT EXISTS warframe_founder_scans (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  sources_attempted INTEGER NOT NULL DEFAULT 0,
  listings_found INTEGER NOT NULL DEFAULT 0,
  alert_eligible INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS warframe_founder_listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  seller TEXT,
  price_value REAL,
  currency TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  evidence_level TEXT NOT NULL CHECK(evidence_level IN ('POTENTIAL_LEAD','CLAIM_EVIDENCE')),
  founder_terms_json TEXT NOT NULL DEFAULT '[]',
  prime_items_json TEXT NOT NULL DEFAULT '[]',
  evidence_snippets_json TEXT NOT NULL DEFAULT '[]',
  evidence_score REAL NOT NULL DEFAULT 0,
  detail_verified INTEGER NOT NULL DEFAULT 0,
  alert_eligible INTEGER NOT NULL DEFAULT 0,
  budget_fit TEXT NOT NULL DEFAULT 'unknown',
  safety_note TEXT NOT NULL,
  last_scan_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wf_founder_recent ON warframe_founder_listings(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_wf_founder_alert ON warframe_founder_listings(alert_eligible,evidence_score DESC,last_seen DESC);

CREATE TABLE IF NOT EXISTS warframe_founder_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL,
  scan_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  evidence_level TEXT NOT NULL,
  evidence_score REAL NOT NULL,
  alert_eligible INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(listing_id) REFERENCES warframe_founder_listings(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_wf_founder_events_time ON warframe_founder_events(observed_at DESC);
