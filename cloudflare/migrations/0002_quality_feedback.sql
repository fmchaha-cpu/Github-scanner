-- v0.2.0 quality / review loop.
-- Safe to run more than once.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS listing_quality (
  listing_id INTEGER PRIMARY KEY,
  updated_at TEXT NOT NULL,
  favorite_character_fit REAL,
  identity_verified INTEGER NOT NULL DEFAULT 0,
  strict_live INTEGER NOT NULL DEFAULT 0,
  verification_level TEXT,
  extraction_quality REAL,
  favorite_characters_json TEXT,
  archetypes_json TEXT,
  risk_flags_json TEXT,
  quality_flags_json TEXT,
  detail_verified_at TEXT,
  manufactured_hits INTEGER NOT NULL DEFAULT 0,
  risk_hits INTEGER NOT NULL DEFAULT 0,
  old_alt_hits INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER,
  listing_url TEXT NOT NULL,
  created_at TEXT NOT NULL,
  reviewer TEXT NOT NULL DEFAULT 'manual',
  label TEXT NOT NULL,
  notes TEXT,
  detector_version TEXT,
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_review_feedback_time
  ON review_feedback(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_review_feedback_label
  ON review_feedback(label, created_at DESC);
