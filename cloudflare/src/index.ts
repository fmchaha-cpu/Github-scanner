export interface Env {
  DB: D1Database;
  INGEST_TOKEN: string;
}

type AnyRow = Record<string, any>;

const HISTORICAL_WEIGHTS: Record<string, number> = {
  SOLD_CONFIRMED: 1.00,
  SOLD_CLAIMED: 0.65,
  EXPIRED_REMOVED: 0.25,
  OUTCOME_UNKNOWN: 0.15,
  RISK_CONTAMINATED: 0.05,
};

const ALLOWED_HISTORICAL_STATUSES = new Set([
  "SOLD_CONFIRMED", "SOLD_CLAIMED", "EXPIRED_REMOVED", "OUTCOME_UNKNOWN", "RISK_CONTAMINATED",
]);

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
    },
  });
}

function unauthorized(): Response {
  return json({ error: "unauthorized" }, 401);
}

function isAuthorized(request: Request, env: Env): boolean {
  const auth = request.headers.get("authorization") || "";
  return auth === `Bearer ${env.INGEST_TOKEN}`;
}

async function readJson<T>(request: Request): Promise<T> {
  return (await request.json()) as T;
}

function nowIso(): string {
  return new Date().toISOString();
}

function clamp(x: number, lo = 0, hi = 1): number {
  return Math.max(lo, Math.min(hi, x));
}

function parseArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (!value) return [];
  try {
    const parsed = JSON.parse(String(value));
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function jaccard(a: string[], b: string[]): number {
  const sa = new Set(a.map((x) => x.toLowerCase()));
  const sb = new Set(b.map((x) => x.toLowerCase()));
  if (sa.size === 0 && sb.size === 0) return 1;
  if (sa.size === 0 || sb.size === 0) return 0;
  let intersection = 0;
  for (const x of sa) if (sb.has(x)) intersection++;
  return intersection / (sa.size + sb.size - intersection);
}

function numSimilarity(a: unknown, b: unknown, scale: number): number {
  if (a == null && b == null) return 0.65;
  if (a == null || b == null) return 0.35;
  const na = Number(a), nb = Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return 0.35;
  return clamp(1 - Math.abs(na - nb) / scale);
}

function comparableSimilarity(a: AnyRow, b: AnyRow): number {
  if (a.server && b.server && a.server !== b.server) return 0;
  if (a.currency && b.currency && a.currency !== b.currency) return 0;

  const parts: Array<[number, number]> = [
    [numSimilarity(a.ar, b.ar, 20), 0.08],
    [numSimilarity(a.limited_c6_count ?? 0, b.limited_c6_count ?? 0, 3), 0.18],
    [numSimilarity(a.c6r1_count ?? 0, b.c6r1_count ?? 0, 2), 0.10],
    [jaccard(parseArray(a.limited_c6_characters_json), parseArray(b.limited_c6_characters_json)), 0.18],
    [jaccard(parseArray(a.c6r1_characters_json), parseArray(b.c6r1_characters_json)), 0.07],
    [jaccard(parseArray(a.character_tags_json), parseArray(b.character_tags_json)), 0.11],
    [numSimilarity(a.limited_pulls, b.limited_pulls, 800), 0.08],
    [numSimilarity(a.history_richness, b.history_richness, 100), 0.07],
    [numSimilarity(a.discovery_headroom, b.discovery_headroom, 100), 0.07],
    [numSimilarity(a.resource_richness, b.resource_richness, 100), 0.06],
    [numSimilarity(a.legacy_collector_value, b.legacy_collector_value, 100), 0.04],
    [jaccard(parseArray(a.archetypes_json), parseArray(b.archetypes_json)), 0.04],
  ];
  const totalWeight = parts.reduce((s, [, w]) => s + w, 0);
  return clamp(parts.reduce((s, [v, w]) => s + v * w, 0) / totalWeight);
}

function recencyWeight(row: AnyRow): number {
  // Imported tracker rows may have no trustworthy original listing date. Do not treat the import timestamp as market recency.
  if (String(row.provenance || "").startsWith("tracker_historical_view") && String(row.notes || "").includes("date unavailable")) return 0.55;
  const raw = row.status_updated_at || row.observed_at || row.last_seen;
  if (!raw) return 0.65;
  const t = Date.parse(String(raw));
  if (!Number.isFinite(t)) return 0.65;
  const days = Math.max(0, (Date.now() - t) / 86400_000);
  // ~270-day half-life with a floor so rare old legacy comps still contribute weakly.
  return Math.max(0.25, Math.pow(0.5, days / 270));
}

function evidenceWeight(row: AnyRow, similarity: number): number {
  let base = HISTORICAL_WEIGHTS[String(row.market_status)] ?? 0;
  if (Number(row.risk_hits || 0) > 0) base *= 0.15;
  return base * Math.pow(clamp(similarity), 2) * recencyWeight(row);
}

function weightedMedian(rows: Array<{ value: number; weight: number }>): number | null {
  const clean = rows.filter((x) => Number.isFinite(x.value) && x.weight > 0).sort((a, b) => a.value - b.value);
  if (!clean.length) return null;
  const total = clean.reduce((s, x) => s + x.weight, 0);
  let acc = 0;
  for (const row of clean) {
    acc += row.weight;
    if (acc >= total / 2) return row.value;
  }
  return clean[clean.length - 1].value;
}

function weightedSummary(rows: Array<{ value: number; weight: number }>) {
  const clean = rows.filter((x) => Number.isFinite(x.value) && x.weight > 0);
  const med = weightedMedian(clean);
  if (med == null) return { count: 0, effective_weight: 0, weighted_median: null, mad: null };
  const mad = weightedMedian(clean.map((x) => ({ value: Math.abs(x.value - med), weight: x.weight })));
  return {
    count: clean.length,
    effective_weight: Number(clean.reduce((s, x) => s + x.weight, 0).toFixed(3)),
    weighted_median: Number(med.toFixed(2)),
    mad: mad == null ? null : Number(mad.toFixed(2)),
  };
}

async function ensureQualityTables(env: Env) {
  await env.DB.prepare(`
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
    )
  `).run();

  await env.DB.prepare(`
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
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_review_feedback_time ON review_feedback(created_at DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_review_feedback_label ON review_feedback(label, created_at DESC)`).run();
}

async function ensureV05Tables(env: Env) {
  await ensureQualityTables(env);
  await env.DB.prepare(`
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
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_market_meta_status ON listing_market_meta(market_status, status_updated_at DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_market_meta_fingerprint ON listing_market_meta(relisting_fingerprint)`).run();

  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS coverage_paths (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scan_run_id TEXT NOT NULL, platform TEXT NOT NULL, query_family TEXT NOT NULL,
      query_text TEXT, page_label TEXT, path_key TEXT NOT NULL, status TEXT NOT NULL,
      result_count INTEGER NOT NULL DEFAULT 0, error TEXT, observed_at TEXT NOT NULL,
      FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_coverage_paths_run ON coverage_paths(scan_run_id, path_key)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_coverage_paths_time ON coverage_paths(observed_at DESC)`).run();

  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS listing_seen_paths (
      listing_id INTEGER NOT NULL, scan_run_id TEXT NOT NULL, path_key TEXT NOT NULL,
      observed_at TEXT NOT NULL, PRIMARY KEY(listing_id, scan_run_id, path_key),
      FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE,
      FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_seen_paths_run_path ON listing_seen_paths(scan_run_id, path_key)`).run();

  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS listing_path_state (
      listing_id INTEGER NOT NULL, path_key TEXT NOT NULL, first_seen TEXT NOT NULL,
      last_seen TEXT NOT NULL, last_checked TEXT NOT NULL, miss_count INTEGER NOT NULL DEFAULT 0,
      last_result TEXT NOT NULL DEFAULT 'seen', PRIMARY KEY(listing_id, path_key),
      FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_path_state_misses ON listing_path_state(miss_count, last_checked DESC)`).run();

  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS listing_status_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, created_at TEXT NOT NULL,
      old_status TEXT, new_status TEXT NOT NULL, confidence REAL, evidence TEXT, scan_run_id TEXT,
      FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE,
      FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE SET NULL
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_status_events_listing ON listing_status_events(listing_id, created_at DESC)`).run();

  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS historical_annotations (
      id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER, listing_url TEXT NOT NULL,
      created_at TEXT NOT NULL, status TEXT NOT NULL, confidence REAL, evidence TEXT,
      notes TEXT, reviewer TEXT NOT NULL DEFAULT 'manual',
      FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE SET NULL
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_historical_annotations_time ON historical_annotations(created_at DESC)`).run();

  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS historical_offers (
      id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT NOT NULL UNIQUE, provenance TEXT NOT NULL,
      platform TEXT, external_id TEXT, url TEXT, title TEXT NOT NULL, seller TEXT, server TEXT, ar INTEGER,
      price_value REAL NOT NULL, currency TEXT NOT NULL, market_status TEXT NOT NULL,
      status_confidence REAL NOT NULL DEFAULT 0, status_evidence TEXT, observed_at TEXT NOT NULL,
      limited_c6_count INTEGER NOT NULL DEFAULT 0, c6r1_count INTEGER NOT NULL DEFAULT 0, limited_pulls REAL,
      history_richness REAL, discovery_headroom REAL, resource_richness REAL, legacy_collector_value REAL,
      archetypes_json TEXT, limited_c6_characters_json TEXT, c6r1_characters_json TEXT, character_tags_json TEXT,
      risk_hits INTEGER NOT NULL DEFAULT 0, relisting_fingerprint TEXT, notes TEXT
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_historical_offers_status ON historical_offers(market_status, observed_at DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_historical_offers_market ON historical_offers(server, currency, price_value)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_historical_offers_fingerprint ON historical_offers(relisting_fingerprint)`).run();

  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS quality_snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT, scan_run_id TEXT, created_at TEXT NOT NULL,
      metrics_json TEXT NOT NULL, suggestions_json TEXT NOT NULL,
      FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE SET NULL
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_quality_snapshots_time ON quality_snapshots(created_at DESC)`).run();
}


async function ensureV06Tables(env: Env) {
  await ensureV05Tables(env);
  await env.DB.prepare(`
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
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_coverage_diag_time ON coverage_diagnostics(observed_at DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_coverage_diag_platform_time ON coverage_diagnostics(platform, observed_at DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_coverage_diag_run_path ON coverage_diagnostics(scan_run_id, path_key)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_coverage_diag_hash ON coverage_diagnostics(platform, content_hash)`).run();

  await env.DB.prepare(`
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
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_listing_verification_reason ON listing_verification_meta(verification_reason, updated_at DESC)`).run();

  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS verification_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, scan_run_id TEXT NOT NULL, listing_id INTEGER NOT NULL,
      platform TEXT NOT NULL, observed_at TEXT NOT NULL, verification_reason TEXT, fetch_mode TEXT,
      fallback_reason TEXT, http_status INTEGER, html_bytes INTEGER, blocked_signals_json TEXT,
      identity_verified INTEGER NOT NULL DEFAULT 0, strict_live INTEGER NOT NULL DEFAULT 0,
      extraction_quality REAL, quality_flags_json TEXT,
      FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE,
      FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_verification_events_time ON verification_events(observed_at DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_verification_events_platform_time ON verification_events(platform, observed_at DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_verification_events_reason_time ON verification_events(verification_reason, observed_at DESC)`).run();
}


async function ensureV07Tables(env: Env) {
  await ensureV06Tables(env);
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS coverage_diagnostics_v07_extra (
      scan_run_id TEXT NOT NULL, path_key TEXT NOT NULL, http_probe_http_status INTEGER,
      safe_headers_json TEXT, http_probe_safe_headers_json TEXT,
      browser_early_blocked INTEGER NOT NULL DEFAULT 0,
      circuit_breaker_triggered INTEGER NOT NULL DEFAULT 0, circuit_breaker_reason TEXT,
      PRIMARY KEY(scan_run_id, path_key),
      FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_cov_diag_v07_breaker ON coverage_diagnostics_v07_extra(circuit_breaker_triggered, scan_run_id)`).run();
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS listing_field_provenance (
      listing_id INTEGER PRIMARY KEY, updated_at TEXT NOT NULL, field_sources_json TEXT NOT NULL,
      FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
    )
  `).run();
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS verification_provenance_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, scan_run_id TEXT NOT NULL, listing_id INTEGER NOT NULL,
      platform TEXT NOT NULL, observed_at TEXT NOT NULL, verification_reason TEXT, field_sources_json TEXT NOT NULL,
      FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE,
      FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_verification_prov_time ON verification_provenance_events(observed_at DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_verification_prov_platform ON verification_provenance_events(platform, observed_at DESC)`).run();
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS source_health_state (
      platform TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'unknown',
      consecutive_blocked INTEGER NOT NULL DEFAULT 0, consecutive_zero_yield INTEGER NOT NULL DEFAULT 0,
      last_success_at TEXT, last_blocked_at TEXT, last_probe_at TEXT, cooldown_until TEXT, last_reason TEXT,
      updated_at TEXT NOT NULL
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_source_health_cooldown ON source_health_state(cooldown_until)`).run();
}

async function ensureV10Tables(env: Env) {
  await ensureV07Tables(env);
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS warframe_founder_scans (
      id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
      sources_attempted INTEGER NOT NULL DEFAULT 0, listings_found INTEGER NOT NULL DEFAULT 0,
      alert_eligible INTEGER NOT NULL DEFAULT 0, errors_json TEXT NOT NULL DEFAULT '[]'
    )
  `).run();
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS warframe_founder_listings (
      id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
      title TEXT NOT NULL, seller TEXT, price_value REAL, currency TEXT,
      first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
      evidence_level TEXT NOT NULL, founder_terms_json TEXT NOT NULL DEFAULT '[]',
      prime_items_json TEXT NOT NULL DEFAULT '[]', evidence_snippets_json TEXT NOT NULL DEFAULT '[]',
      evidence_score REAL NOT NULL DEFAULT 0, detail_verified INTEGER NOT NULL DEFAULT 0,
      alert_eligible INTEGER NOT NULL DEFAULT 0, budget_fit TEXT NOT NULL DEFAULT 'unknown',
      safety_note TEXT NOT NULL, last_scan_id TEXT NOT NULL
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_wf_founder_recent ON warframe_founder_listings(last_seen DESC)`).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_wf_founder_alert ON warframe_founder_listings(alert_eligible,evidence_score DESC,last_seen DESC)`).run();
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS warframe_founder_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, scan_id TEXT NOT NULL,
      observed_at TEXT NOT NULL, evidence_level TEXT NOT NULL, evidence_score REAL NOT NULL,
      alert_eligible INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY(listing_id) REFERENCES warframe_founder_listings(id) ON DELETE CASCADE
    )
  `).run();
  await env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_wf_founder_events_time ON warframe_founder_events(observed_at DESC)`).run();
}

function synthPathKey(r: AnyRow): string {
  return String(r.path_key || `${r.platform}|${r.query_family}|${r.page_label || "seed"}`);
}

async function recordStatusEvent(env: Env, listingId: any, oldStatus: any, newStatus: string, confidence: number, evidence: string | null, scanRunId: string | null) {
  if (String(oldStatus || "") === newStatus) return;
  await env.DB.prepare(`
    INSERT INTO listing_status_events(listing_id, created_at, old_status, new_status, confidence, evidence, scan_run_id)
    VALUES (?,?,?,?,?,?,?)
  `).bind(listingId, nowIso(), oldStatus ?? null, newStatus, confidence, evidence, scanRunId).run();
}

async function upsertListing(env: Env, o: AnyRow, scanRunId: string, observationPolicy: "full" | "changes_only" = "full") {
  const existing = await env.DB.prepare(
    "SELECT id, title, raw_hash, price_value, currency, availability, seller FROM listings WHERE url = ?"
  ).bind(o.url).first();

  const rawChanged = !existing || existing.raw_hash !== o.raw_hash || existing.price_value !== o.price_value || existing.availability !== o.availability || existing.seller !== o.seller;
  const materialChanged = !existing || String(existing.title || "") !== String(o.title || "") ||
    (existing.price_value ?? null) !== (o.price_value ?? null) ||
    (existing.currency ?? null) !== (o.currency ?? null) ||
    (existing.availability ?? null) !== (o.availability ?? null) ||
    (existing.seller ?? null) !== (o.seller ?? null);
  const changed = observationPolicy === "changes_only" ? materialChanged : rawChanged;
  const firstSeen = existing ? undefined : (o.observed_at || nowIso());
  const lastChanged = changed ? (o.observed_at || nowIso()) : undefined;

  await env.DB.prepare(`
    INSERT INTO listings (
      platform, external_id, url, title, seller, server, ar, price_value, currency,
      availability, instant_delivery, after_sale_protection, first_seen, last_seen,
      last_changed, raw_text, raw_hash, data_confidence, security_hint,
      limited_c6_count, c6r1_count, multi_c6, primogems, intertwined, limited_pulls,
      legacy_hits, history_hits, discovery_hits, resource_hits, archetype,
      history_richness, discovery_headroom, resource_richness, organic_account_feel,
      legacy_collector_value, personal_experience_fit, collector_priority,
      detector_reason, is_candidate, is_alert_candidate, last_scan_run_id
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(url) DO UPDATE SET
      external_id=excluded.external_id, title=excluded.title,
      seller=COALESCE(excluded.seller, listings.seller), server=COALESCE(excluded.server, listings.server),
      ar=COALESCE(excluded.ar, listings.ar), price_value=COALESCE(excluded.price_value, listings.price_value),
      currency=COALESCE(excluded.currency, listings.currency), availability=COALESCE(excluded.availability, listings.availability),
      instant_delivery=excluded.instant_delivery,
      after_sale_protection=COALESCE(excluded.after_sale_protection, listings.after_sale_protection),
      last_seen=excluded.last_seen, last_changed=CASE WHEN ? THEN excluded.last_seen ELSE listings.last_changed END,
      raw_text=excluded.raw_text, raw_hash=excluded.raw_hash, data_confidence=excluded.data_confidence,
      security_hint=excluded.security_hint, limited_c6_count=excluded.limited_c6_count,
      c6r1_count=excluded.c6r1_count, multi_c6=excluded.multi_c6, primogems=excluded.primogems,
      intertwined=excluded.intertwined, limited_pulls=excluded.limited_pulls, legacy_hits=excluded.legacy_hits,
      history_hits=excluded.history_hits, discovery_hits=excluded.discovery_hits, resource_hits=excluded.resource_hits,
      archetype=excluded.archetype, history_richness=excluded.history_richness,
      discovery_headroom=excluded.discovery_headroom, resource_richness=excluded.resource_richness,
      organic_account_feel=excluded.organic_account_feel, legacy_collector_value=excluded.legacy_collector_value,
      personal_experience_fit=excluded.personal_experience_fit, collector_priority=excluded.collector_priority,
      detector_reason=excluded.detector_reason, is_candidate=excluded.is_candidate,
      is_alert_candidate=excluded.is_alert_candidate, last_scan_run_id=excluded.last_scan_run_id
  `).bind(
    o.platform, o.external_id ?? null, o.url, o.title, o.seller ?? null, o.server ?? null,
    o.ar ?? null, o.price_value ?? null, o.currency ?? null, o.availability ?? null,
    o.instant_delivery ? 1 : 0, o.after_sale_protection ?? null,
    firstSeen ?? o.observed_at ?? nowIso(), o.observed_at ?? nowIso(),
    lastChanged ?? o.observed_at ?? nowIso(), o.raw_text ?? null, o.raw_hash ?? null,
    o.data_confidence ?? null, o.security_hint ?? null, o.limited_c6_count ?? 0,
    o.c6r1_count ?? 0, o.multi_c6 ? 1 : 0, o.primogems ?? null, o.intertwined ?? null,
    o.limited_pulls ?? null, o.legacy_hits ?? 0, o.history_hits ?? 0, o.discovery_hits ?? 0,
    o.resource_hits ?? 0, o.archetype ?? null, o.history_richness ?? null,
    o.discovery_headroom ?? null, o.resource_richness ?? null, o.organic_account_feel ?? null,
    o.legacy_collector_value ?? null, o.personal_experience_fit ?? null,
    o.collector_priority ?? 0, o.detector_reason ?? null, o.is_candidate ? 1 : 0,
    o.is_alert_candidate ? 1 : 0, scanRunId, changed ? 1 : 0
  ).run();

  const row = await env.DB.prepare("SELECT id FROM listings WHERE url = ?").bind(o.url).first();
  if (!row) throw new Error("listing upsert did not return an id");
  const listingId = row.id;

  if (observationPolicy === "full" || changed) {
    await env.DB.prepare(`
      INSERT INTO listing_snapshots(listing_id, observed_at, price_value, currency, availability, seller, raw_hash, raw_text, changed)
      VALUES (?,?,?,?,?,?,?,?,?)
    `).bind(listingId, o.observed_at ?? nowIso(), o.price_value ?? null, o.currency ?? null,
      o.availability ?? null, o.seller ?? null, o.raw_hash ?? null, o.raw_text ?? null, changed ? 1 : 0).run();
  }

  await env.DB.prepare(`
    INSERT INTO listing_quality(
      listing_id, updated_at, favorite_character_fit, identity_verified, strict_live,
      verification_level, extraction_quality, favorite_characters_json, archetypes_json,
      risk_flags_json, quality_flags_json, detail_verified_at, manufactured_hits, risk_hits, old_alt_hits
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(listing_id) DO UPDATE SET
      updated_at=excluded.updated_at, favorite_character_fit=excluded.favorite_character_fit,
      identity_verified=excluded.identity_verified, strict_live=excluded.strict_live,
      verification_level=excluded.verification_level, extraction_quality=excluded.extraction_quality,
      favorite_characters_json=excluded.favorite_characters_json, archetypes_json=excluded.archetypes_json,
      risk_flags_json=excluded.risk_flags_json, quality_flags_json=excluded.quality_flags_json,
      detail_verified_at=excluded.detail_verified_at, manufactured_hits=excluded.manufactured_hits,
      risk_hits=excluded.risk_hits, old_alt_hits=excluded.old_alt_hits
  `).bind(
    listingId, o.observed_at ?? nowIso(), o.favorite_character_fit ?? null,
    o.identity_verified ? 1 : 0, o.strict_live ? 1 : 0, o.verification_level ?? "card",
    o.extraction_quality ?? null, JSON.stringify(o.favorite_character_names ?? []),
    JSON.stringify(o.archetypes ?? []), JSON.stringify(o.risk_flags ?? []),
    JSON.stringify(o.quality_flags ?? []), o.detail_verified_at ?? null,
    o.manufactured_hits ?? 0, o.risk_hits ?? 0, o.old_alt_hits ?? 0
  ).run();

  await env.DB.prepare(`
    INSERT INTO listing_verification_meta(
      listing_id,updated_at,verification_reason,parser_strategy,detail_fetch_mode,detail_fetch_fallback_reason,
      detail_http_status,detail_html_bytes,detail_blocked_signals_json
    ) VALUES (?,?,?,?,?,?,?,?,?)
    ON CONFLICT(listing_id) DO UPDATE SET
      updated_at=excluded.updated_at, verification_reason=excluded.verification_reason,
      parser_strategy=excluded.parser_strategy, detail_fetch_mode=excluded.detail_fetch_mode,
      detail_fetch_fallback_reason=excluded.detail_fetch_fallback_reason, detail_http_status=excluded.detail_http_status,
      detail_html_bytes=excluded.detail_html_bytes, detail_blocked_signals_json=excluded.detail_blocked_signals_json
  `).bind(
    listingId, o.observed_at ?? nowIso(), o.verification_reason ?? null, o.parser_strategy ?? null,
    o.detail_fetch_mode ?? null, o.detail_fetch_fallback_reason ?? null, o.detail_http_status ?? null,
    o.detail_html_bytes ?? null, JSON.stringify(o.detail_blocked_signals ?? [])
  ).run();

  await env.DB.prepare(`
    INSERT INTO listing_field_provenance(listing_id,updated_at,field_sources_json) VALUES (?,?,?)
    ON CONFLICT(listing_id) DO UPDATE SET updated_at=excluded.updated_at, field_sources_json=excluded.field_sources_json
  `).bind(listingId, o.observed_at ?? nowIso(), JSON.stringify(o.field_sources ?? {})).run();

  // Keep every deep-verification attempt as an event, not only the latest state.
  // This allows us to measure candidate/calibration success rates and parser regressions over time.
  if ((observationPolicy === "full" || changed) && (o.verification_reason || o.verification_level === "detail")) {
    await env.DB.prepare(`
      INSERT INTO verification_events(
        scan_run_id,listing_id,platform,observed_at,verification_reason,fetch_mode,fallback_reason,http_status,
        html_bytes,blocked_signals_json,identity_verified,strict_live,extraction_quality,quality_flags_json
      ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    `).bind(
      scanRunId,listingId,o.platform,o.observed_at??nowIso(),o.verification_reason??null,o.detail_fetch_mode??null,
      o.detail_fetch_fallback_reason??null,o.detail_http_status??null,o.detail_html_bytes??null,
      JSON.stringify(o.detail_blocked_signals??[]),o.identity_verified?1:0,o.strict_live?1:0,
      o.extraction_quality??null,JSON.stringify(o.quality_flags??[])
    ).run();
    await env.DB.prepare(`
      INSERT INTO verification_provenance_events(
        scan_run_id,listing_id,platform,observed_at,verification_reason,field_sources_json
      ) VALUES (?,?,?,?,?,?)
    `).bind(
      scanRunId,listingId,o.platform,o.observed_at??nowIso(),o.verification_reason??null,
      JSON.stringify(o.field_sources??{})
    ).run();
  }

  const oldMeta = await env.DB.prepare("SELECT market_status FROM listing_market_meta WHERE listing_id=?").bind(listingId).first();
  let newStatus = String(o.market_status || (o.strict_live ? "STRICT_LIVE" : "ACTIVE_UNCONFIRMED"));
  const oldStatus = oldMeta?.market_status ? String(oldMeta.market_status) : null;
  // Do not downgrade a strong historical annotation just because an archived page appears in an index again.
  if (["SOLD_CONFIRMED", "SOLD_CLAIMED", "RISK_CONTAMINATED"].includes(oldStatus || "") && newStatus === "ACTIVE_UNCONFIRMED") {
    newStatus = oldStatus!;
  }
  const statusConfidence = Number(o.status_confidence ?? (o.strict_live ? 0.97 : 0.6));
  const statusEvidence = String(o.status_evidence || "collector_observation");

  await env.DB.prepare(`
    INSERT INTO listing_market_meta(
      listing_id, market_status, status_confidence, status_evidence, status_updated_at,
      first_removed_at, relisting_fingerprint, limited_c6_characters_json,
      c6r1_characters_json, character_tags_json, discovery_paths_json
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(listing_id) DO UPDATE SET
      market_status=excluded.market_status, status_confidence=excluded.status_confidence,
      status_evidence=excluded.status_evidence,
      status_updated_at=CASE WHEN listing_market_meta.market_status<>excluded.market_status THEN excluded.status_updated_at ELSE listing_market_meta.status_updated_at END,
      first_removed_at=CASE WHEN excluded.market_status='EXPIRED_REMOVED' THEN COALESCE(listing_market_meta.first_removed_at, excluded.status_updated_at) ELSE listing_market_meta.first_removed_at END,
      relisting_fingerprint=excluded.relisting_fingerprint,
      limited_c6_characters_json=excluded.limited_c6_characters_json,
      c6r1_characters_json=excluded.c6r1_characters_json,
      character_tags_json=excluded.character_tags_json,
      discovery_paths_json=excluded.discovery_paths_json
  `).bind(
    listingId, newStatus, statusConfidence, statusEvidence, o.observed_at ?? nowIso(),
    newStatus === "EXPIRED_REMOVED" ? (o.observed_at ?? nowIso()) : null,
    o.relisting_fingerprint ?? null, JSON.stringify(o.limited_c6_characters ?? []),
    JSON.stringify(o.c6r1_characters ?? []), JSON.stringify(o.character_tags ?? []), JSON.stringify(o.discovery_paths ?? [])
  ).run();
  await recordStatusEvent(env, listingId, oldStatus, newStatus, statusConfidence, statusEvidence, scanRunId);

  for (const pathKey of (o.discovery_paths ?? [])) {
    await env.DB.prepare(`
      INSERT OR IGNORE INTO listing_seen_paths(listing_id, scan_run_id, path_key, observed_at)
      VALUES (?,?,?,?)
    `).bind(listingId, scanRunId, String(pathKey), o.observed_at ?? nowIso()).run();
    await env.DB.prepare(`
      INSERT INTO listing_path_state(listing_id, path_key, first_seen, last_seen, last_checked, miss_count, last_result)
      VALUES (?,?,?,?,?,0,'seen')
      ON CONFLICT(listing_id,path_key) DO UPDATE SET
        last_seen=excluded.last_seen, last_checked=excluded.last_checked, miss_count=0, last_result='seen'
    `).bind(listingId, String(pathKey), o.observed_at ?? nowIso(), o.observed_at ?? nowIso(), o.observed_at ?? nowIso()).run();
  }

  if (o.is_candidate && (observationPolicy === "full" || changed)) {
    await env.DB.prepare(`
      INSERT INTO candidate_events(listing_id, scan_run_id, created_at, priority, reason, event_type, detector_version)
      VALUES (?,?,?,?,?,?,?)
    `).bind(listingId, scanRunId, o.observed_at ?? nowIso(), o.collector_priority ?? 0,
      o.detector_reason ?? "candidate", changed ? "new_or_changed" : "seen_again", o.detector_version ?? "v1").run();
  }

  return { id: listingId, changed };
}

async function processDisappearance(env: Env, scanRunId: string) {
  await ensureV05Tables(env);
  const successful = await env.DB.prepare(`
    SELECT DISTINCT path_key FROM coverage_paths
    WHERE scan_run_id=? AND status LIKE 'ok:%'
      AND query_family='manual_exact_url' AND page_label='exact'
  `).bind(scanRunId).all();

  let missUpdates = 0;
  for (const r of successful.results as AnyRow[]) {
    const pathKey = String(r.path_key);
    const res = await env.DB.prepare(`
      UPDATE listing_path_state
      SET miss_count=miss_count+1, last_checked=?, last_result='miss'
      WHERE path_key=?
        AND listing_id NOT IN (
          SELECT listing_id FROM listing_seen_paths WHERE scan_run_id=? AND path_key=?
        )
    `).bind(nowIso(), pathKey, scanRunId, pathKey).run();
    missUpdates += Number((res as any).meta?.changes || 0);
  }

  const expired = await env.DB.prepare(`
    SELECT m.listing_id, m.market_status
    FROM listing_market_meta m
    WHERE m.market_status IN ('STRICT_LIVE','ACTIVE_UNCONFIRMED')
      AND EXISTS (SELECT 1 FROM listing_path_state s WHERE s.listing_id=m.listing_id)
      AND NOT EXISTS (SELECT 1 FROM listing_path_state s WHERE s.listing_id=m.listing_id AND s.miss_count < 3)
  `).all();

  let expiredCount = 0;
  for (const r of expired.results as AnyRow[]) {
    await env.DB.prepare(`
      UPDATE listing_market_meta
      SET market_status='EXPIRED_REMOVED', status_confidence=0.72,
          status_evidence='three_misses_in_each_successfully_rescanned_known_path',
          status_updated_at=?, first_removed_at=COALESCE(first_removed_at, ?)
      WHERE listing_id=?
    `).bind(nowIso(), nowIso(), r.listing_id).run();
    await recordStatusEvent(env, r.listing_id, r.market_status, "EXPIRED_REMOVED", 0.72,
      "three_misses_in_each_successfully_rescanned_known_path", scanRunId);
    expiredCount++;
  }
  return { successful_paths: successful.results.length, miss_updates: missUpdates, newly_expired: expiredCount };
}


async function updateSourceHealthFromScan(env: Env, scanRunId: string) {
  await ensureV07Tables(env);
  const rows = await env.DB.prepare(`
    SELECT d.platform, COUNT(*) AS pages, SUM(COALESCE(d.parsed_count,0)) AS parsed,
      SUM(CASE WHEN (d.blocked_signals_json IS NOT NULL AND d.blocked_signals_json<>'[]')
        OR COALESCE(x.browser_early_blocked,0)=1 THEN 1 ELSE 0 END) AS blocked_pages,
      SUM(CASE WHEN COALESCE(x.circuit_breaker_triggered,0)=1 THEN 1 ELSE 0 END) AS breaker_triggers
    FROM coverage_diagnostics d
    LEFT JOIN coverage_diagnostics_v07_extra x ON x.scan_run_id=d.scan_run_id AND x.path_key=d.path_key
    WHERE d.scan_run_id=? GROUP BY d.platform
  `).bind(scanRunId).all();

  const updates: AnyRow[] = [];
  for (const r of rows.results as AnyRow[]) {
    const platform = String(r.platform);
    const pages = Number(r.pages || 0), parsed = Number(r.parsed || 0), blockedPages = Number(r.blocked_pages || 0);
    if (pages <= 0) continue;
    const prev = await env.DB.prepare(`SELECT * FROM source_health_state WHERE platform=?`).bind(platform).first() as AnyRow | null;
    let consecutiveBlocked = Number(prev?.consecutive_blocked || 0);
    let consecutiveZero = Number(prev?.consecutive_zero_yield || 0);
    let status = 'healthy', cooldownUntil: string | null = null, reason: string | null = null;
    let lastSuccess = prev?.last_success_at ?? null, lastBlocked = prev?.last_blocked_at ?? null;
    const now = nowIso();

    if (parsed > 0) {
      consecutiveBlocked = 0; consecutiveZero = 0; lastSuccess = now;
      status = 'healthy'; reason = 'parsed_listings';
    } else if (blockedPages > 0) {
      consecutiveBlocked += 1; consecutiveZero = 0; lastBlocked = now;
      reason = 'blocked_or_challenge_zero_yield';
      if (consecutiveBlocked >= 2) {
        status = 'cooldown';
        cooldownUntil = new Date(Date.now() + 2 * 3600_000).toISOString();
      } else status = 'degraded';
    } else {
      consecutiveZero += 1; consecutiveBlocked = 0;
      reason = 'zero_yield_without_block_signal';
      if (consecutiveZero >= 4) {
        status = 'cooldown';
        cooldownUntil = new Date(Date.now() + 3600_000).toISOString();
      } else status = 'degraded';
    }

    await env.DB.prepare(`
      INSERT INTO source_health_state(platform,status,consecutive_blocked,consecutive_zero_yield,last_success_at,
        last_blocked_at,last_probe_at,cooldown_until,last_reason,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(platform) DO UPDATE SET status=excluded.status,consecutive_blocked=excluded.consecutive_blocked,
        consecutive_zero_yield=excluded.consecutive_zero_yield,last_success_at=excluded.last_success_at,
        last_blocked_at=excluded.last_blocked_at,last_probe_at=excluded.last_probe_at,cooldown_until=excluded.cooldown_until,
        last_reason=excluded.last_reason,updated_at=excluded.updated_at
    `).bind(platform,status,consecutiveBlocked,consecutiveZero,lastSuccess,lastBlocked,now,cooldownUntil,reason,now).run();
    updates.push({ platform, status, pages, parsed, blocked_pages: blockedPages, consecutive_blocked: consecutiveBlocked,
      consecutive_zero_yield: consecutiveZero, cooldown_until: cooldownUntil, reason });
  }
  return updates;
}

async function qualitySnapshot(env: Env, hours: number) {
  await ensureV07Tables(env);
  const since = new Date(Date.now() - hours * 3600_000).toISOString();

  const completeness = await env.DB.prepare(`
    SELECT COUNT(*) AS n,
      SUM(CASE WHEN price_value IS NOT NULL THEN 1 ELSE 0 END) AS with_price,
      SUM(CASE WHEN server IS NOT NULL THEN 1 ELSE 0 END) AS with_server,
      SUM(CASE WHEN seller IS NOT NULL THEN 1 ELSE 0 END) AS with_seller,
      SUM(CASE WHEN availability IS NOT NULL THEN 1 ELSE 0 END) AS with_availability,
      SUM(CASE WHEN q.identity_verified=1 THEN 1 ELSE 0 END) AS identity_verified,
      SUM(CASE WHEN q.strict_live=1 THEN 1 ELSE 0 END) AS strict_live
    FROM listings l LEFT JOIN listing_quality q ON q.listing_id=l.id
    WHERE l.last_seen>=?
  `).bind(since).first();

  const byPlatform = await env.DB.prepare(`
    SELECT l.platform, COUNT(*) AS listings,
      SUM(CASE WHEN l.price_value IS NOT NULL THEN 1 ELSE 0 END) AS with_price,
      SUM(CASE WHEN l.seller IS NOT NULL THEN 1 ELSE 0 END) AS with_seller,
      SUM(CASE WHEN l.server IS NOT NULL THEN 1 ELSE 0 END) AS with_server,
      SUM(CASE WHEN l.availability IS NOT NULL THEN 1 ELSE 0 END) AS with_availability,
      SUM(CASE WHEN q.verification_level='detail' THEN 1 ELSE 0 END) AS detail_verified,
      SUM(CASE WHEN q.identity_verified=1 THEN 1 ELSE 0 END) AS identity_verified,
      SUM(CASE WHEN q.strict_live=1 THEN 1 ELSE 0 END) AS strict_live,
      AVG(q.extraction_quality) AS avg_extraction_quality
    FROM listings l LEFT JOIN listing_quality q ON q.listing_id=l.id
    WHERE l.last_seen>=? GROUP BY l.platform ORDER BY listings DESC
  `).bind(since).all();

  const coverage = await env.DB.prepare(`
    SELECT platform, query_family, status, COUNT(*) AS observations, SUM(result_count) AS results
    FROM coverage_paths WHERE observed_at>=?
    GROUP BY platform, query_family, status ORDER BY platform, query_family, status
  `).bind(since).all();

  const diagnostics = await env.DB.prepare(`
    SELECT d.platform,
      COUNT(*) AS pages,
      SUM(CASE WHEN d.fetch_mode='browser' THEN 1 ELSE 0 END) AS browser_pages,
      SUM(CASE WHEN d.fallback_reason IS NOT NULL THEN 1 ELSE 0 END) AS fallback_pages,
      SUM(CASE WHEN COALESCE(d.detail_link_count,0)=0 THEN 1 ELSE 0 END) AS zero_detail_pages,
      SUM(CASE WHEN COALESCE(d.parsed_count,0)=0 THEN 1 ELSE 0 END) AS zero_parsed_pages,
      SUM(CASE WHEN d.blocked_signals_json IS NOT NULL AND d.blocked_signals_json<>'[]' THEN 1 ELSE 0 END) AS blocked_pages,
      SUM(CASE WHEN d.http_probe_blocked_signals_json IS NOT NULL AND d.http_probe_blocked_signals_json<>'[]' THEN 1 ELSE 0 END) AS http_probe_blocked_pages,
      SUM(CASE WHEN d.http_probe_detail_link_count=0 AND d.fallback_reason IS NOT NULL THEN 1 ELSE 0 END) AS http_zero_link_fallbacks,
      SUM(COALESCE(d.unmatched_listing_like_count,0)) AS unmatched_listing_like_links,
      SUM(COALESCE(d.http_probe_unmatched_listing_like_count,0)) AS http_probe_unmatched_listing_like_links,
      SUM(COALESCE(d.detail_link_count,0)) AS detail_links,
      SUM(COALESCE(d.parsed_count,0)) AS parsed_rows,
      AVG(d.elapsed_ms) AS avg_elapsed_ms,
      COUNT(DISTINCT d.content_hash) AS unique_content_hashes,
      COUNT(DISTINCT d.http_probe_content_hash) AS unique_http_probe_hashes,
      SUM(CASE WHEN COALESCE(x.browser_early_blocked,0)=1 THEN 1 ELSE 0 END) AS browser_early_blocked_pages,
      SUM(CASE WHEN COALESCE(x.circuit_breaker_triggered,0)=1 THEN 1 ELSE 0 END) AS circuit_breaker_triggers,
      SUM(CASE WHEN x.http_probe_http_status IS NOT NULL THEN 1 ELSE 0 END) AS http_status_observed
    FROM coverage_diagnostics d
    LEFT JOIN coverage_diagnostics_v07_extra x ON x.scan_run_id=d.scan_run_id AND x.path_key=d.path_key
    WHERE d.observed_at>=?
    GROUP BY d.platform ORDER BY pages DESC
  `).bind(since).all();

  const repeatedContent = await env.DB.prepare(`
    SELECT platform, content_hash, COUNT(DISTINCT path_key) AS paths, MAX(observed_at) AS latest
    FROM coverage_diagnostics
    WHERE observed_at>=? AND content_hash IS NOT NULL
    GROUP BY platform, content_hash HAVING COUNT(DISTINCT path_key)>=3
    ORDER BY paths DESC, latest DESC LIMIT 50
  `).bind(since).all();

  const repeatedHttpContent = await env.DB.prepare(`
    SELECT platform, http_probe_content_hash AS content_hash, COUNT(DISTINCT path_key) AS paths, MAX(observed_at) AS latest
    FROM coverage_diagnostics
    WHERE observed_at>=? AND http_probe_content_hash IS NOT NULL
    GROUP BY platform, http_probe_content_hash HAVING COUNT(DISTINCT path_key)>=3
    ORDER BY paths DESC, latest DESC LIMIT 50
  `).bind(since).all();

  const verificationReasons = await env.DB.prepare(`
    SELECT verification_reason, COUNT(*) AS n FROM listing_verification_meta v
    JOIN listings l ON l.id=v.listing_id WHERE l.last_seen>=? AND verification_reason IS NOT NULL
    GROUP BY verification_reason ORDER BY n DESC
  `).bind(since).all();

  const verificationPerformance = await env.DB.prepare(`
    SELECT platform, verification_reason, COUNT(*) AS attempts,
      SUM(identity_verified) AS identity_verified, SUM(strict_live) AS strict_live,
      SUM(CASE WHEN blocked_signals_json IS NOT NULL AND blocked_signals_json<>'[]' THEN 1 ELSE 0 END) AS blocked_attempts,
      AVG(extraction_quality) AS avg_extraction_quality
    FROM verification_events WHERE observed_at>=?
    GROUP BY platform, verification_reason ORDER BY attempts DESC
  `).bind(since).all();

  const statuses = await env.DB.prepare(`
    SELECT market_status, COUNT(*) AS n FROM listing_market_meta GROUP BY market_status ORDER BY n DESC
  `).all();

  const historical = await env.DB.prepare(`
    SELECT SUM(n) AS n, SUM(sold_confirmed) AS sold_confirmed, SUM(sold_claimed) AS sold_claimed, SUM(expired_removed) AS expired_removed
    FROM (
      SELECT COUNT(*) AS n,
        SUM(CASE WHEN market_status='SOLD_CONFIRMED' THEN 1 ELSE 0 END) AS sold_confirmed,
        SUM(CASE WHEN market_status='SOLD_CLAIMED' THEN 1 ELSE 0 END) AS sold_claimed,
        SUM(CASE WHEN market_status='EXPIRED_REMOVED' THEN 1 ELSE 0 END) AS expired_removed
      FROM listing_market_meta WHERE market_status IN ('SOLD_CONFIRMED','SOLD_CLAIMED','EXPIRED_REMOVED','OUTCOME_UNKNOWN','RISK_CONTAMINATED')
      UNION ALL
      SELECT COUNT(*) AS n,
        SUM(CASE WHEN market_status='SOLD_CONFIRMED' THEN 1 ELSE 0 END) AS sold_confirmed,
        SUM(CASE WHEN market_status='SOLD_CLAIMED' THEN 1 ELSE 0 END) AS sold_claimed,
        SUM(CASE WHEN market_status='EXPIRED_REMOVED' THEN 1 ELSE 0 END) AS expired_removed
      FROM historical_offers
    )
  `).first();

  const duplicateGroups = await env.DB.prepare(`
    SELECT COUNT(*) AS n FROM (
      SELECT relisting_fingerprint FROM listing_market_meta
      WHERE relisting_fingerprint IS NOT NULL
      GROUP BY relisting_fingerprint HAVING COUNT(*)>1
    )
  `).first();

  const feedback = await env.DB.prepare(`
    SELECT label, COUNT(*) AS n FROM review_feedback WHERE created_at>=?
    GROUP BY label ORDER BY n DESC
  `).bind(since).all();

  const staleFlags = await env.DB.prepare(`
    SELECT COUNT(*) AS n FROM listing_quality q JOIN listings l ON l.id=q.listing_id
    WHERE l.last_seen>=? AND q.verification_level='detail' AND q.quality_flags_json LIKE '%not_detail_verified%'
  `).bind(since).first();

  const provenanceRows = await env.DB.prepare(`
    SELECT l.platform,p.field_sources_json FROM listing_field_provenance p JOIN listings l ON l.id=p.listing_id
    WHERE l.last_seen>=?
  `).bind(since).all();
  const fieldSourceUsage: AnyRow = {};
  for (const r of provenanceRows.results as AnyRow[]) {
    const platform = String(r.platform || 'Unknown');
    fieldSourceUsage[platform] ||= {};
    let fields: AnyRow = {};
    try { fields = JSON.parse(String(r.field_sources_json || '{}')); } catch {}
    for (const [field, source] of Object.entries(fields)) {
      fieldSourceUsage[platform][field] ||= {};
      const src = String(source || 'unknown');
      fieldSourceUsage[platform][field][src] = Number(fieldSourceUsage[platform][field][src] || 0) + 1;
    }
  }

  const sourceHealth = await env.DB.prepare(`SELECT * FROM source_health_state ORDER BY platform`).all();
  const n = Number(completeness?.n || 0);
  const pct = (v: any) => n ? Number((100 * Number(v || 0) / n).toFixed(1)) : 0;
  const suggestions: AnyRow[] = [];
  if (n >= 10 && pct(completeness?.with_seller) < 60) suggestions.push({ priority: "high", code: "seller_extraction_low", message: "Seller coverage is below 60%; add platform-specific seller selectors/JSON-LD handling." });
  if (n >= 10 && pct(completeness?.with_server) < 70) suggestions.push({ priority: "high", code: "server_extraction_low", message: "Server coverage is below 70%; calibrate server extraction per marketplace." });
  if (n >= 10 && pct(completeness?.with_price) < 80) suggestions.push({ priority: "high", code: "price_extraction_low", message: "Price coverage is below 80%; inspect card/detail selectors before expanding volume." });
  if (Number(historical?.n || 0) < 30) suggestions.push({ priority: "medium", code: "historical_pool_thin", message: "Historical comparable pool is still small; keep accumulating outcomes and import known historical URLs with explicit status evidence." });
  if (Number(historical?.sold_confirmed || 0) < 8) suggestions.push({ priority: "medium", code: "confirmed_sold_pool_thin", message: "Few exact-detail sold/closed anchors exist. Treat price comparisons as low-confidence until this grows." });
  const coverageRows = coverage.results as AnyRow[];
  const diagRows = diagnostics.results as AnyRow[];
  const platformRows = byPlatform.results as AnyRow[];
  for (const p of platformRows) {
    const pn = Number(p.listings || 0);
    const sellerPct = pn ? 100 * Number(p.with_seller || 0) / pn : 0;
    if (pn >= 5 && sellerPct < 40) suggestions.push({ priority: "high", code: `seller_extraction_low:${p.platform}`, message: `${p.platform} seller extraction is only ${sellerPct.toFixed(1)}%.` });
  }
  for (const d of diagRows) {
    const links = Number(d.detail_links || 0), parsed = Number(d.parsed_rows || 0), pages = Number(d.pages || 0);
    if (pages && parsed === 0) suggestions.push({ priority: "high", code: `source_zero_yield:${d.platform}`, message: `${d.platform} fetched pages but parsed zero listings; inspect challenge/fallback and detail URL patterns.` });
    if (links >= 5 && parsed / links < 0.55) suggestions.push({ priority: "high", code: `parser_yield_low:${d.platform}`, message: `${d.platform} parser converted less than 55% of discovered detail links into listing rows.` });
    if (Number(d.blocked_pages || 0) > 0) suggestions.push({ priority: "high", code: `blocking_detected:${d.platform}`, message: `${d.platform} showed challenge/block signals on ${d.blocked_pages} final page(s).` });
    if (Number(d.http_probe_blocked_pages || 0) > 0) suggestions.push({ priority: "medium", code: `http_probe_blocked:${d.platform}`, message: `${d.platform} HTTP fetches showed challenge/block signals before browser fallback on ${d.http_probe_blocked_pages} page(s).` });
    if (Number(d.http_zero_link_fallbacks || 0) >= 2) suggestions.push({ priority: "medium", code: `http_shell_or_redirect:${d.platform}`, message: `${d.platform} repeatedly returned HTTP pages with zero listing links; browser fallback was required.` });
    if (Number(d.unmatched_listing_like_links || 0) > 0 || Number(d.http_probe_unmatched_listing_like_links || 0) > 0) suggestions.push({ priority: "high", code: `detail_pattern_drift:${d.platform}`, message: `${d.platform} exposed listing-like URLs that did not match the configured detail pattern; inspect diagnostics samples.` });
  }
  for (const v of verificationPerformance.results as AnyRow[]) {
    const attempts = Number(v.attempts || 0);
    const identityRate = attempts ? 100 * Number(v.identity_verified || 0) / attempts : 0;
    if (String(v.verification_reason) === "candidate" && attempts >= 4 && identityRate < 25) {
      suggestions.push({ priority: "high", code: `candidate_verification_low:${v.platform}`, message: `${v.platform} candidate deep checks verify identity only ${identityRate.toFixed(1)}% of the time; inspect seller/server/detail extraction before trusting alerts.` });
    }
  }
  if ((repeatedContent.results as AnyRow[]).length) suggestions.push({ priority: "medium", code: "same_content_across_queries", message: "Three or more query paths returned identical final page content. This can indicate redirects, challenge pages, or dead category URLs." });
  if ((repeatedHttpContent.results as AnyRow[]).length) suggestions.push({ priority: "medium", code: "same_http_probe_content_across_queries", message: "Three or more query paths returned identical HTTP-probe content before browser fallback; likely shell, redirect, or challenge behavior." });
  const errors = coverageRows.filter((r) => String(r.status) === "error");
  if (errors.length) suggestions.push({ priority: "high", code: "source_errors_present", message: `${errors.length} coverage bucket(s) errored in the selected window.` });
  const zeroHits = coverageRows.filter((r) => String(r.status).startsWith("ok:") && Number(r.results || 0) === 0);
  if (zeroHits.length >= 3) suggestions.push({ priority: "medium", code: "repeated_zero_hit_queries", message: "Several successful fetches produced zero listing URLs; verify detail URL patterns and marketplace markup." });
  if (Number(duplicateGroups?.n || 0) > 0) suggestions.push({ priority: "info", code: "duplicate_review_available", message: "Probable relisting/duplicate groups exist; review them before using historical counts as independent observations." });
  if (Number(staleFlags?.n || 0) > 0) suggestions.push({ priority: "high", code: "stale_quality_flags", message: `${staleFlags?.n} detail-verified listing(s) still carry not_detail_verified; recompute derived flags.` });
  for (const h of sourceHealth.results as AnyRow[]) {
    if (String(h.status) === "cooldown") suggestions.push({ priority: "info", code: `source_cooldown:${h.platform}`, message: `${h.platform} is temporarily cooled down until ${h.cooldown_until}; this prevents repeated blocked requests.` });
  }
  const falseNeg = (feedback.results as AnyRow[]).find((x) => String(x.label) === "false_negative");
  if (Number(falseNeg?.n || 0) > 0) suggestions.push({ priority: "high", code: "false_negatives_recorded", message: `${falseNeg?.n} false-negative review(s) were recorded in this window; add them to the benchmark corpus.` });

  return {
    since,
    completeness: {
      ...completeness,
      price_pct: pct(completeness?.with_price), server_pct: pct(completeness?.with_server),
      seller_pct: pct(completeness?.with_seller), availability_pct: pct(completeness?.with_availability),
      identity_verified_pct: pct(completeness?.identity_verified), strict_live_pct: pct(completeness?.strict_live),
    },
    by_platform: (byPlatform.results as AnyRow[]).map((p) => {
      const pn = Number(p.listings || 0);
      const ppct = (v: any) => pn ? Number((100 * Number(v || 0) / pn).toFixed(1)) : 0;
      return { ...p, price_pct: ppct(p.with_price), seller_pct: ppct(p.with_seller), server_pct: ppct(p.with_server),
        availability_pct: ppct(p.with_availability), detail_verified_pct: ppct(p.detail_verified),
        identity_verified_pct: ppct(p.identity_verified), strict_live_pct: ppct(p.strict_live) };
    }),
    coverage: coverage.results,
    coverage_diagnostics: diagnostics.results,
    repeated_content_groups: repeatedContent.results,
    repeated_http_probe_content_groups: repeatedHttpContent.results,
    verification_reasons: verificationReasons.results,
    verification_performance: (verificationPerformance.results as AnyRow[]).map((v) => {
      const attempts = Number(v.attempts || 0);
      return { ...v, identity_success_pct: attempts ? Number((100*Number(v.identity_verified||0)/attempts).toFixed(1)) : 0,
        strict_live_pct: attempts ? Number((100*Number(v.strict_live||0)/attempts).toFixed(1)) : 0 };
    }),
    market_statuses: statuses.results,
    historical_pool: historical,
    probable_duplicate_groups: Number(duplicateGroups?.n || 0),
    feedback: feedback.results,
    stale_quality_flag_count: Number(staleFlags?.n || 0),
    field_source_usage: fieldSourceUsage,
    source_health: sourceHealth.results,
    suggestions,
  };
}

async function joinedListingByUrl(env: Env, listingUrl: string) {
  await ensureV05Tables(env);
  return await env.DB.prepare(`
    SELECT l.*, q.favorite_character_fit, q.identity_verified, q.strict_live, q.verification_level,
      q.extraction_quality, q.favorite_characters_json, q.archetypes_json, q.risk_flags_json,
      q.quality_flags_json, q.detail_verified_at, q.manufactured_hits, q.risk_hits, q.old_alt_hits,
      m.market_status, m.status_confidence, m.status_evidence, m.status_updated_at, m.first_removed_at,
      m.relisting_fingerprint, m.limited_c6_characters_json, m.c6r1_characters_json, m.character_tags_json, m.discovery_paths_json,
      v.verification_reason, v.parser_strategy, v.detail_fetch_mode, v.detail_fetch_fallback_reason,
      v.detail_http_status, v.detail_html_bytes, v.detail_blocked_signals_json
    FROM listings l
    LEFT JOIN listing_quality q ON q.listing_id=l.id
    LEFT JOIN listing_market_meta m ON m.listing_id=l.id
    LEFT JOIN listing_verification_meta v ON v.listing_id=l.id
    WHERE l.url=?
  `).bind(listingUrl).first();
}

async function historicalStats(env: Env) {
  await ensureV05Tables(env);
  const tracked = await env.DB.prepare(`
    SELECT market_status, COUNT(*) AS n FROM listing_market_meta
    WHERE market_status IN ('SOLD_CONFIRMED','SOLD_CLAIMED','EXPIRED_REMOVED','OUTCOME_UNKNOWN','RISK_CONTAMINATED')
    GROUP BY market_status
  `).all();
  const imported = await env.DB.prepare(`
    SELECT market_status, COUNT(*) AS n FROM historical_offers GROUP BY market_status
  `).all();
  const importedCount = await env.DB.prepare(`SELECT COUNT(*) AS n FROM historical_offers`).first() as AnyRow | null;
  const trackedCount = await env.DB.prepare(`
    SELECT COUNT(*) AS n FROM listing_market_meta
    WHERE market_status IN ('SOLD_CONFIRMED','SOLD_CLAIMED','EXPIRED_REMOVED','OUTCOME_UNKNOWN','RISK_CONTAMINATED')
  `).first() as AnyRow | null;
  const seed = await env.DB.prepare(`
    SELECT COUNT(*) AS n, MAX(observed_at) AS latest FROM historical_offers
    WHERE source_key LIKE 'tracker-v26:%' OR provenance LIKE 'tracker_historical_view%'
  `).first() as AnyRow | null;
  const currencies = await env.DB.prepare(`
    SELECT currency, COUNT(*) AS n FROM historical_offers GROUP BY currency ORDER BY n DESC
  `).all();
  const byStatus: AnyRow = {};
  for (const row of [...(tracked.results as AnyRow[]), ...(imported.results as AnyRow[])]) {
    const key = String(row.market_status || 'UNKNOWN');
    byStatus[key] = Number(byStatus[key] || 0) + Number(row.n || 0);
  }
  const trackedN = Number(trackedCount?.n || 0), importedN = Number(importedCount?.n || 0);
  return {
    total: trackedN + importedN,
    tracked: trackedN,
    imported: importedN,
    tracker_seed_records: Number(seed?.n || 0),
    tracker_seed_latest: seed?.latest ?? null,
    by_status: byStatus,
    imported_currencies: currencies.results,
    caveat: 'Historical counts are evidence records, not guaranteed settled transactions.',
  };
}

async function comparablesFor(env: Env, targetUrl: string, limit: number) {
  const target = await joinedListingByUrl(env, targetUrl) as AnyRow | null;
  if (!target) return { error: "listing_not_found", url: targetUrl };
  if (!target.currency) return { error: "target_currency_unknown", target };

  const pool = await env.DB.prepare(`
    SELECT l.*, q.archetypes_json, q.risk_hits,
      m.market_status, m.status_confidence, m.status_evidence,
      m.relisting_fingerprint, m.limited_c6_characters_json, m.c6r1_characters_json, m.character_tags_json
    FROM listings l
    LEFT JOIN listing_quality q ON q.listing_id=l.id
    LEFT JOIN listing_market_meta m ON m.listing_id=l.id
    WHERE l.url<>? AND l.price_value IS NOT NULL AND l.currency=?
      AND (? IS NULL OR l.server=? OR l.server IS NULL)
    ORDER BY l.last_seen DESC LIMIT 1200
  `).bind(targetUrl, target.currency, target.server ?? null, target.server ?? null).all();

  const imported = await env.DB.prepare(`
    SELECT NULL AS id, platform, external_id, url, title, seller, server, ar, price_value, currency,
      observed_at AS last_seen, limited_c6_count, c6r1_count, limited_pulls, history_richness,
      discovery_headroom, resource_richness, legacy_collector_value, archetypes_json, risk_hits,
      market_status, status_confidence, status_evidence, relisting_fingerprint,
      limited_c6_characters_json, c6r1_characters_json, character_tags_json, source_key, provenance, notes
    FROM historical_offers
    WHERE price_value IS NOT NULL AND currency=? AND (? IS NULL OR server=? OR server IS NULL)
    ORDER BY observed_at DESC LIMIT 1200
  `).bind(target.currency, target.server ?? null, target.server ?? null).all();

  const combinedPool: AnyRow[] = [
    ...(pool.results as AnyRow[]).map((r) => ({ ...r, comparable_source: "tracked_listing" })),
    ...(imported.results as AnyRow[]).map((r) => ({ ...r, comparable_source: "imported_historical" })),
  ];

  const scored: AnyRow[] = combinedPool.map((row): AnyRow => {
    const similarity = comparableSimilarity(target, row);
    const historicalWeight = evidenceWeight(row, similarity);
    return { ...row, similarity: Number(similarity.toFixed(4)), recency_weight: Number(recencyWeight(row).toFixed(4)), historical_weight: Number(historicalWeight.toFixed(4)) };
  }).filter((r: AnyRow) => Number(r.similarity) >= 0.45).sort((a: AnyRow, b: AnyRow) => Number(b.similarity) - Number(a.similarity));

  const historical: AnyRow[] = scored.filter((r: AnyRow) => HISTORICAL_WEIGHTS[String(r.market_status)] != null);
  const active: AnyRow[] = scored.filter((r: AnyRow) => ["STRICT_LIVE", "ACTIVE_UNCONFIRMED"].includes(String(r.market_status)));

  // Deduplicate historical price evidence by probable relisting fingerprint. Keep the strongest evidence per fingerprint.
  const bestByFingerprint = new Map<string, AnyRow>();
  for (const r of historical) {
    const key = String(r.relisting_fingerprint || `url:${r.url}`);
    const current = bestByFingerprint.get(key);
    if (!current || Number(r.historical_weight) > Number(current.historical_weight)) bestByFingerprint.set(key, r);
  }
  const dedupHistorical = Array.from(bestByFingerprint.values()).sort((a, b) => Number(b.historical_weight) - Number(a.historical_weight));
  const values = dedupHistorical.map((r) => ({ value: Number(r.price_value), weight: Number(r.historical_weight) })).filter((x) => x.weight > 0);
  const summary = weightedSummary(values);
  const confirmedCount = dedupHistorical.filter((r) => String(r.market_status) === "SOLD_CONFIRMED").length;
  const eff = Number(summary.effective_weight || 0);
  let comparisonConfidence = "very_low";
  if (eff >= 5 && summary.count >= 6 && confirmedCount >= 3) comparisonConfidence = "high";
  else if (eff >= 2.5 && summary.count >= 4 && confirmedCount >= 1) comparisonConfidence = "medium";
  else if (eff >= 1 && summary.count >= 2) comparisonConfidence = "low";

  const activeByFingerprint = new Map<string, AnyRow>();
  for (const r of active) {
    const key = String(r.relisting_fingerprint || `url:${r.url}`);
    const current = activeByFingerprint.get(key);
    if (!current || Number(r.similarity) > Number(current.similarity)) activeByFingerprint.set(key, r);
  }
  const dedupActive = Array.from(activeByFingerprint.values());
  const activeSummary = weightedSummary(dedupActive.map((r) => ({ value: Number(r.price_value), weight: Math.pow(Number(r.similarity || 0), 2) })));

  const median = summary.weighted_median as number | null;
  const targetPrice = target.price_value == null ? null : Number(target.price_value);
  const positionPct = median != null && targetPrice != null && median !== 0 ? Number((100 * (targetPrice - median) / median).toFixed(1)) : null;

  return {
    target,
    method: {
      currency_rule: "same-currency only; no implicit FX conversion",
      historical_weights: HISTORICAL_WEIGHTS,
      similarity_threshold: 0.45,
      duplicate_rule: "probable relistings share one historical price vote; no records are auto-merged",
      recency_rule: "historical evidence decays with ~270-day half-life, floor 0.25",
      caveat: "SOLD_CONFIRMED confirms exact-listing sold/closed status, not the final transaction settlement price.",
    },
    historical_summary: { ...summary, sold_confirmed_count: confirmedCount, comparison_confidence: comparisonConfidence },
    active_asking_summary: activeSummary,
    target_vs_historical_weighted_median_pct: positionPct,
    historical_comparables: dedupHistorical.slice(0, limit),
    active_asking_comparables: dedupActive.slice(0, limit),
    raw_comparable_count: scored.length,
    dedup_historical_count: dedupHistorical.length,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: {
        "access-control-allow-origin": "*", "access-control-allow-methods": "GET,POST,OPTIONS",
        "access-control-allow-headers": "authorization,content-type",
      }});
    }

    if (request.method === "GET" && path === "/health") {
      await ensureV10Tables(env);
      const db = await env.DB.prepare("SELECT COUNT(*) AS n FROM listings").first();
      const wfDb = await env.DB.prepare("SELECT COUNT(*) AS n FROM warframe_founder_listings").first();
      const wfLast = await env.DB.prepare("SELECT * FROM warframe_founder_scans ORDER BY finished_at DESC LIMIT 1").first();
      const hist = await historicalStats(env);
      const last = await env.DB.prepare("SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 1").first();
      const lastCompleted = await env.DB.prepare(
        "SELECT * FROM scan_runs WHERE finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1",
      ).first();
      const running = await env.DB.prepare(
        "SELECT * FROM scan_runs WHERE status='running' ORDER BY started_at ASC LIMIT 1",
      ).first();
      const runningCount = await env.DB.prepare(
        "SELECT COUNT(*) AS n FROM scan_runs WHERE status='running'",
      ).first();
      const runningStartedAt = running?.started_at ? Date.parse(String(running.started_at)) : Number.NaN;
      const runningScanAgeSeconds = Number.isFinite(runningStartedAt)
        ? Math.max(0, Math.floor((Date.now() - runningStartedAt) / 1000))
        : null;
      return json({
        ok: true, version: "1.1", listing_count: db?.n ?? 0, historical_count: hist.total,
        historical_seed_records: hist.tracker_seed_records, last_scan: last ?? null,
        last_completed_scan: lastCompleted ?? null, running_scan: running ?? null,
        running_scan_count: Number(runningCount?.n ?? 0), running_scan_age_seconds: runningScanAgeSeconds,
        warframe_founder_count: wfDb?.n ?? 0, warframe_last_scan: wfLast ?? null, now: nowIso(),
        capabilities: ["source_health", "field_provenance", "historical_stats", "comparables", "quality_by_version", "multi_game", "warframe_founder", "smart_scan_profiles", "sparse_snapshots", "scan_lifecycle_health"],
      });
    }

    if (request.method === "GET" && (path === "/v1/warframe/founder/recent" || path === "/v1/warframe/founder/alerts")) {
      await ensureV10Tables(env);
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "168"), 1), 24 * 365);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "100"), 1), 500);
      const since = new Date(Date.now() - hours * 3600_000).toISOString();
      const alertsOnly = path.endsWith("/alerts");
      const result = await env.DB.prepare(`
        SELECT platform,url,title,seller,price_value,currency,first_seen,last_seen,evidence_level,
          founder_terms_json,prime_items_json,evidence_snippets_json,evidence_score,detail_verified,
          alert_eligible,budget_fit,safety_note,last_scan_id
        FROM warframe_founder_listings
        WHERE last_seen>=? AND (?=0 OR alert_eligible=1)
        ORDER BY alert_eligible DESC,evidence_score DESC,last_seen DESC LIMIT ?
      `).bind(since, alertsOnly ? 1 : 0, limit).all();
      const rows = (result.results as AnyRow[]).map((r) => ({
        ...r,
        founder_terms: parseArray(r.founder_terms_json),
        prime_items: parseArray(r.prime_items_json),
        evidence_snippets: parseArray(r.evidence_snippets_json),
      }));
      return json({ since, count: rows.length, listings: rows,
        caveat: "Claim evidence comes from listing text; authenticity, ownership and transferability are not verified." });
    }

    if (request.method === "GET" && path === "/v1/candidates/recent") {
      await ensureV05Tables(env);
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "24"), 1), 168);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "100"), 1), 500);
      const since = new Date(Date.now() - hours * 3600_000).toISOString();
      const result = await env.DB.prepare(`
        SELECT l.platform, l.external_id, l.url, l.title, l.seller, l.server, l.ar, l.price_value,
          l.currency, l.availability, l.instant_delivery, l.after_sale_protection, l.last_seen,
          l.limited_c6_count, l.c6r1_count, l.primogems, l.intertwined, l.limited_pulls,
          l.legacy_hits, l.history_hits, l.discovery_hits, l.resource_hits, l.archetype,
          l.history_richness, l.discovery_headroom, l.resource_richness, l.organic_account_feel,
          l.legacy_collector_value, l.personal_experience_fit, l.collector_priority,
          l.detector_reason, l.data_confidence, l.security_hint, l.is_alert_candidate,
          q.favorite_character_fit, q.identity_verified, q.strict_live, q.verification_level,
          q.extraction_quality, q.favorite_characters_json, q.archetypes_json, q.risk_flags_json,
          q.quality_flags_json, q.detail_verified_at, q.manufactured_hits, q.risk_hits, q.old_alt_hits,
          m.market_status, m.status_confidence, m.status_evidence, m.relisting_fingerprint,
          m.limited_c6_characters_json, m.c6r1_characters_json
        FROM listings l
        LEFT JOIN listing_quality q ON q.listing_id=l.id
        LEFT JOIN listing_market_meta m ON m.listing_id=l.id
        WHERE l.is_candidate=1 AND l.last_seen>=? AND COALESCE(m.market_status,'ACTIVE_UNCONFIRMED') IN ('STRICT_LIVE','ACTIVE_UNCONFIRMED')
        ORDER BY l.collector_priority DESC, l.last_seen DESC LIMIT ?
      `).bind(since, limit).all();
      return json({ since, count: result.results.length, candidates: result.results });
    }

    if (request.method === "GET" && path === "/v1/review-queue") {
      await ensureV05Tables(env);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "50"), 1), 200);
      const result = await env.DB.prepare(`
        SELECT l.id, l.platform, l.external_id, l.url, l.title, l.seller, l.server, l.ar,
          l.price_value, l.currency, l.availability, l.last_seen, l.archetype, l.collector_priority,
          l.detector_reason, l.data_confidence, l.security_hint, l.is_alert_candidate,
          q.favorite_character_fit, q.identity_verified, q.strict_live, q.verification_level,
          q.extraction_quality, q.favorite_characters_json, q.archetypes_json, q.risk_flags_json,
          q.quality_flags_json, m.market_status, m.status_confidence, m.status_evidence
        FROM listings l LEFT JOIN listing_quality q ON q.listing_id=l.id
        LEFT JOIN listing_market_meta m ON m.listing_id=l.id
        WHERE l.is_candidate=1 AND COALESCE(m.market_status,'ACTIVE_UNCONFIRMED') IN ('STRICT_LIVE','ACTIVE_UNCONFIRMED')
        ORDER BY l.is_alert_candidate DESC, l.collector_priority DESC, l.last_seen DESC LIMIT ?
      `).bind(limit).all();
      return json({ count: result.results.length, queue: result.results });
    }

    if (request.method === "GET" && path === "/v1/coverage/recent") {
      await ensureV05Tables(env);
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "24"), 1), 168);
      const since = new Date(Date.now() - hours * 3600_000).toISOString();
      const result = await env.DB.prepare(`
        SELECT scan_run_id, platform, query_family, query_text, page_label, path_key, status,
          result_count, error, observed_at FROM coverage_paths WHERE observed_at>=?
        ORDER BY observed_at DESC LIMIT 1500
      `).bind(since).all();
      return json({ since, rows: result.results });
    }

    if (request.method === "GET" && path === "/v1/coverage/diagnostics") {
      await ensureV07Tables(env);
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "24"), 1), 168);
      const since = new Date(Date.now() - hours * 3600_000).toISOString();
      const platform = url.searchParams.get("platform");
      const result = await env.DB.prepare(`
        SELECT d.scan_run_id,d.platform,d.path_key,d.observed_at,d.fetch_mode,d.http_status,d.elapsed_ms,d.html_bytes,d.text_chars,
          d.anchor_count,d.detail_link_count,d.parsed_count,d.page_title,d.content_hash,d.blocked_signals_json,
          d.sample_detail_urls_json,d.fallback_reason,d.parser_strategy,d.final_url,d.unmatched_listing_like_count,
          d.sample_unmatched_listing_like_urls_json,d.http_probe_html_bytes,d.http_probe_text_chars,
          d.http_probe_detail_link_count,d.http_probe_content_hash,d.http_probe_blocked_signals_json,
          d.http_probe_final_url,d.http_probe_unmatched_listing_like_count,d.http_probe_sample_unmatched_listing_like_urls_json,
          x.http_probe_http_status,x.safe_headers_json,x.http_probe_safe_headers_json,x.browser_early_blocked,
          x.circuit_breaker_triggered,x.circuit_breaker_reason
        FROM coverage_diagnostics d LEFT JOIN coverage_diagnostics_v07_extra x
          ON x.scan_run_id=d.scan_run_id AND x.path_key=d.path_key
        WHERE d.observed_at>=? AND (? IS NULL OR d.platform=?)
        ORDER BY d.observed_at DESC LIMIT 2000
      `).bind(since, platform, platform).all();
      return json({ since, platform_filter: platform, count: result.results.length, diagnostics: result.results });
    }

    if (request.method === "GET" && path === "/v1/verification/events") {
      await ensureV07Tables(env);
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "24"), 1), 24 * 30);
      const since = new Date(Date.now() - hours * 3600_000).toISOString();
      const platform = url.searchParams.get("platform");
      const result = await env.DB.prepare(`
        SELECT e.id,e.scan_run_id,e.platform,e.observed_at,e.verification_reason,e.fetch_mode,e.fallback_reason,
          e.http_status,e.html_bytes,e.blocked_signals_json,e.identity_verified,e.strict_live,e.extraction_quality,
          e.quality_flags_json,p.field_sources_json,l.url,l.title,l.seller,l.server,l.price_value,l.currency
        FROM verification_events e JOIN listings l ON l.id=e.listing_id
        LEFT JOIN verification_provenance_events p ON p.scan_run_id=e.scan_run_id AND p.listing_id=e.listing_id
          AND p.observed_at=e.observed_at
        WHERE e.observed_at>=? AND (? IS NULL OR e.platform=?)
        ORDER BY e.observed_at DESC LIMIT 2000
      `).bind(since,platform,platform).all();
      return json({ since, platform_filter: platform, count: result.results.length, events: result.results });
    }

    if (request.method === "GET" && path === "/v1/quality/recent") {
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "24"), 1), 168);
      return json(await qualitySnapshot(env, hours));
    }

    if (request.method === "GET" && path === "/v1/quality/snapshots") {
      await ensureV05Tables(env);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "20"), 1), 100);
      const r = await env.DB.prepare("SELECT * FROM quality_snapshots ORDER BY created_at DESC LIMIT ?").bind(limit).all();
      return json({ count: r.results.length, snapshots: r.results });
    }

    if (request.method === "GET" && path === "/v1/quality/trends") {
      await ensureV07Tables(env);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "20"), 2), 100);
      const r = await env.DB.prepare("SELECT id,scan_run_id,created_at,metrics_json FROM quality_snapshots ORDER BY created_at DESC LIMIT ?").bind(limit).all();
      const points = (r.results as AnyRow[]).map((x) => {
        let m: AnyRow = {};
        try { m = JSON.parse(String(x.metrics_json || "{}")); } catch {}
        const c = m.completeness || {};
        const platformSummary: AnyRow = {};
        for (const p of (m.by_platform || [])) platformSummary[String(p.platform)] = {
          listings: Number(p.listings || 0), price_pct: p.price_pct ?? null, server_pct: p.server_pct ?? null,
          seller_pct: p.seller_pct ?? null, availability_pct: p.availability_pct ?? null,
          detail_verified_pct: p.detail_verified_pct ?? null, identity_verified_pct: p.identity_verified_pct ?? null,
          strict_live_pct: p.strict_live_pct ?? null, avg_extraction_quality: p.avg_extraction_quality ?? null,
        };
        return { id: x.id, scan_run_id: x.scan_run_id, created_at: x.created_at,
          price_pct: c.price_pct ?? null, server_pct: c.server_pct ?? null, seller_pct: c.seller_pct ?? null,
          availability_pct: c.availability_pct ?? null, identity_verified_pct: c.identity_verified_pct ?? null,
          strict_live_pct: c.strict_live_pct ?? null,
          historical_pool_n: Number(m.historical_pool?.n || 0), probable_duplicate_groups: Number(m.probable_duplicate_groups || 0),
          platforms: platformSummary, suggestions: m.suggestions || [] };
      });
      const newest = points[0] || null, oldest = points[points.length - 1] || null;
      const delta: AnyRow = {};
      if (newest && oldest) for (const k of ["price_pct","server_pct","seller_pct","availability_pct","identity_verified_pct","strict_live_pct","historical_pool_n"]) {
        const a = Number((newest as AnyRow)[k]), b = Number((oldest as AnyRow)[k]);
        delta[k] = Number.isFinite(a) && Number.isFinite(b) ? Number((a-b).toFixed(2)) : null;
      }
      const platformDelta: AnyRow = {};
      if (newest && oldest) {
        const names = new Set([...Object.keys((newest as AnyRow).platforms || {}), ...Object.keys((oldest as AnyRow).platforms || {})]);
        for (const name of names) {
          const a = ((newest as AnyRow).platforms || {})[name] || {};
          const b = ((oldest as AnyRow).platforms || {})[name] || {};
          platformDelta[name] = {};
          for (const k of ["listings","price_pct","server_pct","seller_pct","availability_pct","detail_verified_pct","identity_verified_pct","strict_live_pct","avg_extraction_quality"]) {
            const av = Number(a[k]), bv = Number(b[k]);
            platformDelta[name][k] = Number.isFinite(av) && Number.isFinite(bv) ? Number((av-bv).toFixed(2)) : null;
          }
        }
      }
      return json({ count: points.length, newest, oldest, delta, platform_delta: platformDelta, points });
    }

    if (request.method === "GET" && path === "/v1/source-health") {
      await ensureV07Tables(env);
      const r = await env.DB.prepare(`SELECT * FROM source_health_state ORDER BY platform`).all();
      return json({ now: nowIso(), count: r.results.length, sources: r.results });
    }

    if (request.method === "GET" && path === "/v1/quality/by-version") {
      await ensureV07Tables(env);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "50"), 2), 200);
      const r = await env.DB.prepare(`
        SELECT id,created_at,code,message,details_json FROM system_events
        WHERE component='collector' AND code LIKE 'SCAN_QUALITY_V%'
        ORDER BY created_at DESC LIMIT ?
      `).bind(limit).all();
      const latestByVersion = new Map<string, AnyRow>();
      const allPoints: AnyRow[] = [];
      for (const row of r.results as AnyRow[]) {
        let m: AnyRow = {}; try { m = JSON.parse(String(row.details_json || '{}')); } catch {}
        const code = String(row.code || '');
        const suffix = code.replace('SCAN_QUALITY_V','');
        const version = suffix.length >= 2 ? `0.${Number(suffix)}` : suffix || 'unknown';
        const c = m.completeness || {};
        const point = {
          collector_version: version, created_at: row.created_at, event_id: row.id,
          listing_count: Number(m.listing_count || 0), candidate_count: Number(m.candidate_count || 0),
          price_pct: c.price_pct ?? null, server_pct: c.server_pct ?? null, seller_pct: c.seller_pct ?? null,
          availability_pct: c.availability_pct ?? null, detail_verified_pct: c.detail_verified_pct ?? null,
          identity_verified_pct: c.identity_verified_pct ?? null, strict_live_pct: c.strict_live_pct ?? null,
          avg_extraction_quality: c.avg_extraction_quality ?? null,
          historical_anchor_observations: Number(m.historical_anchor_observations || 0),
          historical_pool_count: Number(m.historical_pool?.total || 0),
          historical_sold_confirmed: Number(m.historical_pool?.sold_confirmed || 0),
          candidate_comparable_coverage_pct: Number(m.candidate_comparable_coverage_pct || 0),
          worker_version_compatible: Boolean(m.worker_api?.compatible),
          requests_avoided: Number(m.requests_avoided || 0),
          stale_quality_flag_count: Number(m.stale_quality_flag_count || 0),
          improvement_signals: m.improvement_signals || [], platform_quality: m.platform_quality || {},
          coverage_diagnostics: m.coverage_diagnostics || {},
        };
        allPoints.push(point);
        if (!latestByVersion.has(version)) latestByVersion.set(version, point);
      }
      const versions = Array.from(latestByVersion.values());
      const newest = versions[0] || null, previous = versions[1] || null;
      const delta: AnyRow = {};
      if (newest && previous) for (const k of ['listing_count','candidate_count','price_pct','server_pct','seller_pct','availability_pct','detail_verified_pct','identity_verified_pct','strict_live_pct','avg_extraction_quality','historical_anchor_observations','historical_pool_count','historical_sold_confirmed','candidate_comparable_coverage_pct','requests_avoided','stale_quality_flag_count']) {
        const a=Number((newest as AnyRow)[k]),b=Number((previous as AnyRow)[k]); delta[k]=Number.isFinite(a)&&Number.isFinite(b)?Number((a-b).toFixed(2)):null;
      }
      return json({ source: 'exact_collector_scan_events', newest, previous, delta, versions, points: allPoints });
    }

    if (request.method === "GET" && path === "/v1/historical/stats") {
      return json(await historicalStats(env));
    }

    if (request.method === "GET" && path === "/v1/historical/recent") {
      await ensureV05Tables(env);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "100"), 1), 500);
      const status = url.searchParams.get("status");
      const allowed = status && ALLOWED_HISTORICAL_STATUSES.has(status) ? status : null;
      const result = await env.DB.prepare(`
        SELECT l.platform, l.external_id, l.url, l.title, l.seller, l.server, l.ar, l.price_value,
          l.currency, l.last_seen, l.limited_c6_count, l.c6r1_count, l.limited_pulls,
          l.history_richness, l.discovery_headroom, l.resource_richness, l.legacy_collector_value,
          q.archetypes_json, q.risk_hits, q.risk_flags_json,
          m.market_status, m.status_confidence, m.status_evidence, m.status_updated_at,
          m.first_removed_at, m.relisting_fingerprint, m.limited_c6_characters_json,
          m.c6r1_characters_json, m.character_tags_json
        FROM listing_market_meta m JOIN listings l ON l.id=m.listing_id
        LEFT JOIN listing_quality q ON q.listing_id=l.id
        WHERE m.market_status IN ('SOLD_CONFIRMED','SOLD_CLAIMED','EXPIRED_REMOVED','OUTCOME_UNKNOWN','RISK_CONTAMINATED')
          AND (? IS NULL OR m.market_status=?)
        ORDER BY m.status_updated_at DESC LIMIT ?
      `).bind(allowed, allowed, limit).all();
      const imported = await env.DB.prepare(`
        SELECT platform, external_id, url, title, seller, server, ar, price_value, currency,
          observed_at AS last_seen, limited_c6_count, c6r1_count, limited_pulls,
          history_richness, discovery_headroom, resource_richness, legacy_collector_value,
          archetypes_json, risk_hits, market_status, status_confidence, status_evidence,
          observed_at AS status_updated_at, NULL AS first_removed_at, relisting_fingerprint,
          limited_c6_characters_json, c6r1_characters_json, character_tags_json, source_key, provenance
        FROM historical_offers
        WHERE (? IS NULL OR market_status=?) ORDER BY observed_at DESC LIMIT ?
      `).bind(allowed, allowed, limit).all();
      const combined: AnyRow[] = ([
        ...(result.results as AnyRow[]).map((r): AnyRow => ({ ...r, provenance: "tracker_history" })),
        ...(imported.results as AnyRow[]),
      ] as AnyRow[]).sort((a: AnyRow,b: AnyRow) => String(b.status_updated_at || b.last_seen).localeCompare(String(a.status_updated_at || a.last_seen))).slice(0, limit);
      return json({ count: combined.length, status_filter: allowed, historical: combined,
        caveat: "Historical rows store listing/status evidence. SOLD_CONFIRMED does not prove the final settlement price." });
    }

    if (request.method === "GET" && path === "/v1/comparables") {
      const targetUrl = url.searchParams.get("url");
      if (!targetUrl) return json({ error: "url_required" }, 400);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "30"), 3), 100);
      const result: any = await comparablesFor(env, targetUrl, limit);
      return json(result, result.error ? 404 : 200);
    }

    if (request.method === "GET" && path === "/v1/duplicates/recent") {
      await ensureV05Tables(env);
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "168"), 1), 24 * 365);
      const since = new Date(Date.now() - hours * 3600_000).toISOString();
      const groups = await env.DB.prepare(`
        SELECT m.relisting_fingerprint, COUNT(*) AS n, MIN(l.first_seen) AS first_seen, MAX(l.last_seen) AS last_seen
        FROM listing_market_meta m JOIN listings l ON l.id=m.listing_id
        WHERE m.relisting_fingerprint IS NOT NULL AND l.last_seen>=?
        GROUP BY m.relisting_fingerprint HAVING COUNT(*)>1
        ORDER BY n DESC, last_seen DESC LIMIT 100
      `).bind(since).all();
      const detailed: AnyRow[] = [];
      for (const g of groups.results as AnyRow[]) {
        const rows = await env.DB.prepare(`
          SELECT l.platform,l.url,l.title,l.seller,l.server,l.ar,l.price_value,l.currency,l.first_seen,l.last_seen,
            m.market_status,m.status_confidence FROM listings l JOIN listing_market_meta m ON m.listing_id=l.id
          WHERE m.relisting_fingerprint=? ORDER BY l.last_seen DESC LIMIT 20
        `).bind(g.relisting_fingerprint).all();
        detailed.push({ ...g, listings: rows.results });
      }
      return json({ since, count: detailed.length, groups: detailed,
        caveat: "Fingerprint matches are duplicate/relisting suggestions only; they are never auto-merged." });
    }

    if (request.method === "GET" && path === "/v1/status/history") {
      await ensureV05Tables(env);
      const targetUrl = url.searchParams.get("url");
      if (!targetUrl) return json({ error: "url_required" }, 400);
      const listing = await env.DB.prepare("SELECT id,url,title FROM listings WHERE url=?").bind(targetUrl).first();
      if (!listing) return json({ error: "listing_not_found" }, 404);
      const events = await env.DB.prepare("SELECT * FROM listing_status_events WHERE listing_id=? ORDER BY created_at DESC LIMIT 200").bind(listing.id).all();
      return json({ listing, events: events.results });
    }

    if (request.method === "GET" && path === "/v1/feedback/summary") {
      await ensureQualityTables(env);
      const days = Math.min(Math.max(Number(url.searchParams.get("days") || "30"), 1), 365);
      const since = new Date(Date.now() - days * 86400_000).toISOString();
      const result = await env.DB.prepare(`
        SELECT label,COUNT(*) AS n,MAX(created_at) AS latest FROM review_feedback
        WHERE created_at>=? GROUP BY label ORDER BY n DESC
      `).bind(since).all();
      return json({ since, labels: result.results });
    }

    if (!isAuthorized(request, env)) return unauthorized();

    if (request.method === "POST" && path === "/v1/warframe/founder/batch") {
      await ensureV10Tables(env);
      const body = await readJson<AnyRow>(request);
      const rows = Array.isArray(body.listings) ? body.listings : [];
      if (!body.scan_id || rows.length > 100) return json({ error: "scan_id_required_and_max_100_listings" }, 400);
      await env.DB.prepare(`
        INSERT INTO warframe_founder_scans(id,started_at,finished_at,sources_attempted,listings_found,alert_eligible,errors_json)
        VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING
      `).bind(body.scan_id,body.started_at||nowIso(),body.finished_at||nowIso(),body.sources_attempted||0,
        body.listings_found||rows.length,body.alert_eligible||0,JSON.stringify(body.errors||[])).run();
      let stored = 0;
      for (const r of rows) {
        if (!r.url || !r.title || !["POTENTIAL_LEAD","CLAIM_EVIDENCE"].includes(String(r.evidence_level))) continue;
        const previous = await env.DB.prepare(
          "SELECT price_value,currency,evidence_level,evidence_score,detail_verified,alert_eligible FROM warframe_founder_listings WHERE url=?"
        ).bind(r.url).first() as AnyRow | null;
        const changed = !previous || (previous.price_value ?? null) !== (r.price_value ?? null) ||
          (previous.currency ?? null) !== (r.currency ?? null) ||
          previous.evidence_level !== r.evidence_level || Number(previous.evidence_score) !== Number(r.evidence_score || 0) ||
          Number(previous.detail_verified) !== (r.detail_verified ? 1 : 0) || Number(previous.alert_eligible) !== (r.alert_eligible ? 1 : 0);
        await env.DB.prepare(`
          INSERT INTO warframe_founder_listings(
            platform,url,title,seller,price_value,currency,first_seen,last_seen,evidence_level,
            founder_terms_json,prime_items_json,evidence_snippets_json,evidence_score,detail_verified,
            alert_eligible,budget_fit,safety_note,last_scan_id
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(url) DO UPDATE SET platform=excluded.platform,title=excluded.title,seller=excluded.seller,
            price_value=excluded.price_value,currency=excluded.currency,last_seen=excluded.last_seen,
            evidence_level=excluded.evidence_level,founder_terms_json=excluded.founder_terms_json,
            prime_items_json=excluded.prime_items_json,evidence_snippets_json=excluded.evidence_snippets_json,
            evidence_score=excluded.evidence_score,detail_verified=excluded.detail_verified,
            alert_eligible=excluded.alert_eligible,budget_fit=excluded.budget_fit,
            safety_note=excluded.safety_note,last_scan_id=excluded.last_scan_id
        `).bind(
          r.platform||"Unknown",String(r.url),String(r.title),r.seller??null,r.price_value??null,r.currency??null,
          r.observed_at||nowIso(),r.observed_at||nowIso(),r.evidence_level,JSON.stringify(r.founder_terms||[]),
          JSON.stringify(r.prime_items||[]),JSON.stringify(r.evidence_snippets||[]),clamp(Number(r.evidence_score||0),0,100),
          r.detail_verified?1:0,r.alert_eligible?1:0,r.budget_fit||"unknown",
          r.safety_note||"Listing claim only; authenticity not verified.",body.scan_id
        ).run();
        const listing = await env.DB.prepare("SELECT id FROM warframe_founder_listings WHERE url=?").bind(r.url).first();
        if (body.observation_policy !== "changes_only" || changed) {
          await env.DB.prepare(`
            INSERT INTO warframe_founder_events(listing_id,scan_id,observed_at,evidence_level,evidence_score,alert_eligible)
            VALUES (?,?,?,?,?,?)
          `).bind(listing?.id,body.scan_id,r.observed_at||nowIso(),r.evidence_level,
            clamp(Number(r.evidence_score||0),0,100),r.alert_eligible?1:0).run();
        }
        stored++;
      }
      return json({ ok: true, stored, scan_id: body.scan_id }, 201);
    }

    if (request.method === "POST" && path === "/v1/scan/start") {
      const body = await readJson<AnyRow>(request);
      await ensureV05Tables(env);
      const startedAt = body.started_at || nowIso();
      await env.DB.prepare(`
        UPDATE scan_runs
        SET finished_at=?, status='interrupted',
          notes=CASE
            WHEN notes IS NULL OR notes='' THEN 'automatically closed before a newer scan'
            ELSE notes || '; automatically closed before a newer scan'
          END
        WHERE status='running' AND finished_at IS NULL
          AND datetime(started_at) <= datetime(?, '-10 minutes')
      `).bind(startedAt, startedAt).run();
      await env.DB.prepare(`INSERT INTO scan_runs(id,started_at,collector_version,status,notes) VALUES (?,?,?,?,?)`)
        .bind(body.id, startedAt, body.collector_version || null, "running", body.notes || null).run();
      return json({ ok: true, id: body.id }, 201);
    }

    if (request.method === "POST" && path === "/v1/coverage/batch") {
      await ensureV07Tables(env);
      const body = await readJson<{ scan_run_id: string; rows: AnyRow[] }>(request);
      for (const r of body.rows) {
        await env.DB.prepare(`
          INSERT INTO coverage(scan_run_id,platform,query_family,query_text,page_label,status,result_count,error,observed_at)
          VALUES (?,?,?,?,?,?,?,?,?)
        `).bind(body.scan_run_id,r.platform,r.query_family,r.query_text??null,r.page_label??null,
          r.status,r.result_count??0,r.error??null,r.observed_at??nowIso()).run();
        await env.DB.prepare(`
          INSERT INTO coverage_paths(scan_run_id,platform,query_family,query_text,page_label,path_key,status,result_count,error,observed_at)
          VALUES (?,?,?,?,?,?,?,?,?,?)
        `).bind(body.scan_run_id,r.platform,r.query_family,r.query_text??null,r.page_label??null,
          synthPathKey(r),r.status,r.result_count??0,r.error??null,r.observed_at??nowIso()).run();
        // Diagnostics are only meaningful for paths that actually fetched a page.
        // Rotation skips / disabled sources remain visible in coverage_paths without polluting parser-health metrics.
        if (r.fetch_mode || r.content_hash || r.elapsed_ms != null || r.html_bytes != null) {
          await env.DB.prepare(`
            INSERT INTO coverage_diagnostics(
              scan_run_id,platform,path_key,observed_at,fetch_mode,http_status,elapsed_ms,html_bytes,text_chars,
              anchor_count,detail_link_count,parsed_count,page_title,content_hash,blocked_signals_json,
              sample_detail_urls_json,fallback_reason,parser_strategy,final_url,unmatched_listing_like_count,
              sample_unmatched_listing_like_urls_json,http_probe_html_bytes,http_probe_text_chars,
              http_probe_detail_link_count,http_probe_content_hash,http_probe_blocked_signals_json,http_probe_final_url,
              http_probe_unmatched_listing_like_count,http_probe_sample_unmatched_listing_like_urls_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          `).bind(
            body.scan_run_id,r.platform,synthPathKey(r),r.observed_at??nowIso(),r.fetch_mode??null,r.http_status??null,
            r.elapsed_ms??null,r.html_bytes??null,r.text_chars??null,r.anchor_count??null,r.detail_link_count??null,
            r.parsed_count??r.result_count??null,r.page_title??null,r.content_hash??null,
            JSON.stringify(r.blocked_signals??[]),JSON.stringify(r.sample_detail_urls??[]),r.fallback_reason??null,
            r.parser_strategy??null,r.final_url??null,r.unmatched_listing_like_count??null,
            JSON.stringify(r.sample_unmatched_listing_like_urls??[]),r.http_probe_html_bytes??null,r.http_probe_text_chars??null,
            r.http_probe_detail_link_count??null,r.http_probe_content_hash??null,
            JSON.stringify(r.http_probe_blocked_signals??[]),r.http_probe_final_url??null,
            r.http_probe_unmatched_listing_like_count??null,JSON.stringify(r.http_probe_sample_unmatched_listing_like_urls??[])
          ).run();
          await env.DB.prepare(`
            INSERT INTO coverage_diagnostics_v07_extra(
              scan_run_id,path_key,http_probe_http_status,safe_headers_json,http_probe_safe_headers_json,
              browser_early_blocked,circuit_breaker_triggered,circuit_breaker_reason
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(scan_run_id,path_key) DO UPDATE SET
              http_probe_http_status=excluded.http_probe_http_status,safe_headers_json=excluded.safe_headers_json,
              http_probe_safe_headers_json=excluded.http_probe_safe_headers_json,browser_early_blocked=excluded.browser_early_blocked,
              circuit_breaker_triggered=excluded.circuit_breaker_triggered,circuit_breaker_reason=excluded.circuit_breaker_reason
          `).bind(
            body.scan_run_id,synthPathKey(r),r.http_probe_http_status??null,JSON.stringify(r.safe_headers??{}),
            JSON.stringify(r.http_probe_safe_headers??{}),r.browser_early_blocked?1:0,r.circuit_breaker_triggered?1:0,
            r.circuit_breaker_reason??null
          ).run();
        }
      }
      return json({ ok: true, inserted: body.rows.length });
    }

    if (request.method === "POST" && path === "/v1/listings/batch") {
      await ensureV07Tables(env);
      const body = await readJson<{ scan_run_id: string; listings: AnyRow[]; observation_policy?: string }>(request);
      const observationPolicy: "full" | "changes_only" = body.observation_policy === "changes_only" ? "changes_only" : "full";
      let changed = 0;
      for (const observation of body.listings) {
        const res = await upsertListing(env, observation, body.scan_run_id, observationPolicy);
        if (res.changed) changed++;
      }
      return json({ ok: true, received: body.listings.length, changed, observation_policy: observationPolicy });
    }

    if (request.method === "POST" && path === "/v1/scan/finish") {
      await ensureV07Tables(env);
      const body = await readJson<AnyRow>(request);
      const sourceHealthUpdate = await updateSourceHealthFromScan(env, body.id);
      const disappearance = body.process_disappearance === false
        ? { skipped: true, reason: "fast_profile" }
        : await processDisappearance(env, body.id);
      await env.DB.prepare(`
        UPDATE scan_runs SET finished_at=?,status=?,source_count=?,listing_count=?,candidate_count=?,error_count=?,notes=? WHERE id=?
      `).bind(body.finished_at||nowIso(),body.status||"ok",body.source_count||0,body.listing_count||0,
        body.candidate_count||0,body.error_count||0,body.notes||null,body.id).run();
      let quality: AnyRow = { suggestions: [] };
      if (body.create_quality_snapshot !== false) {
        quality = await qualitySnapshot(env, 24) as AnyRow;
        await env.DB.prepare(`INSERT INTO quality_snapshots(scan_run_id,created_at,metrics_json,suggestions_json) VALUES (?,?,?,?)`)
          .bind(body.id, nowIso(), JSON.stringify({ ...quality, disappearance, source_health_update: sourceHealthUpdate }), JSON.stringify(quality.suggestions || [])).run();
      }
      return json({ ok: true, disappearance, source_health_update: sourceHealthUpdate, quality_suggestions: quality.suggestions || [] });
    }

    if (request.method === "POST" && path === "/v1/system-event") {
      const body = await readJson<AnyRow>(request);
      await env.DB.prepare(`INSERT INTO system_events(created_at,component,severity,code,message,details_json) VALUES (?,?,?,?,?,?)`)
        .bind(body.created_at||nowIso(),body.component||"unknown",body.severity||"info",body.code||null,
          body.message||"",body.details_json?JSON.stringify(body.details_json):null).run();
      return json({ ok: true }, 201);
    }

    if (request.method === "POST" && path === "/v1/review-feedback") {
      await ensureQualityTables(env);
      const body = await readJson<AnyRow>(request);
      if (!body.listing_url || !body.label) return json({ error: "listing_url_and_label_required" }, 400);
      const listing = await env.DB.prepare("SELECT id FROM listings WHERE url=?").bind(body.listing_url).first();
      await env.DB.prepare(`
        INSERT INTO review_feedback(listing_id,listing_url,created_at,reviewer,label,notes,detector_version)
        VALUES (?,?,?,?,?,?,?)
      `).bind(listing?.id??null,body.listing_url,body.created_at||nowIso(),body.reviewer||"manual",
        body.label,body.notes||null,body.detector_version||null).run();
      return json({ ok: true }, 201);
    }

    if (request.method === "POST" && path === "/v1/historical/annotate") {
      await ensureV05Tables(env);
      const body = await readJson<AnyRow>(request);
      if (!body.listing_url || !ALLOWED_HISTORICAL_STATUSES.has(String(body.status))) {
        return json({ error: "listing_url_and_valid_historical_status_required", allowed_statuses: Array.from(ALLOWED_HISTORICAL_STATUSES) }, 400);
      }
      const listing = await env.DB.prepare("SELECT id FROM listings WHERE url=?").bind(body.listing_url).first();
      if (!listing) return json({ error: "listing_not_found_ingest_it_first" }, 404);
      const old = await env.DB.prepare("SELECT market_status FROM listing_market_meta WHERE listing_id=?").bind(listing.id).first();
      const confidence = clamp(Number(body.confidence ?? 0.8), 0, 1);
      const evidence = String(body.evidence || "manual_annotation");
      await env.DB.prepare(`
        INSERT INTO historical_annotations(listing_id,listing_url,created_at,status,confidence,evidence,notes,reviewer)
        VALUES (?,?,?,?,?,?,?,?)
      `).bind(listing.id,body.listing_url,body.created_at||nowIso(),body.status,confidence,evidence,
        body.notes||null,body.reviewer||"manual").run();
      await env.DB.prepare(`
        INSERT INTO listing_market_meta(listing_id,market_status,status_confidence,status_evidence,status_updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(listing_id) DO UPDATE SET market_status=excluded.market_status,
          status_confidence=excluded.status_confidence,status_evidence=excluded.status_evidence,
          status_updated_at=excluded.status_updated_at,
          first_removed_at=CASE WHEN excluded.market_status='EXPIRED_REMOVED' THEN COALESCE(listing_market_meta.first_removed_at,excluded.status_updated_at) ELSE listing_market_meta.first_removed_at END
      `).bind(listing.id,body.status,confidence,evidence,body.created_at||nowIso()).run();
      await recordStatusEvent(env, listing.id, old?.market_status ?? null, String(body.status), confidence, evidence, null);
      return json({ ok: true, listing_url: body.listing_url, status: body.status }, 201);
    }

    if (request.method === "POST" && path === "/v1/historical/import") {
      await ensureV05Tables(env);
      const body = await readJson<{ records?: AnyRow[] }>(request);
      const records = body.records || [];
      if (!Array.isArray(records) || records.length === 0 || records.length > 500) {
        return json({ error: "records_required_max_500" }, 400);
      }
      let imported = 0;
      const errors: AnyRow[] = [];
      for (const r of records) {
        const status = String(r.market_status || r.status || "");
        if (!r.source_key || !r.provenance || !r.title || r.price_value == null || !r.currency || !ALLOWED_HISTORICAL_STATUSES.has(status)) {
          errors.push({ source_key: r.source_key ?? null, error: "missing_required_field_or_invalid_status" });
          continue;
        }
        await env.DB.prepare(`
          INSERT INTO historical_offers(
            source_key,provenance,platform,external_id,url,title,seller,server,ar,price_value,currency,
            market_status,status_confidence,status_evidence,observed_at,limited_c6_count,c6r1_count,limited_pulls,
            history_richness,discovery_headroom,resource_richness,legacy_collector_value,archetypes_json,
            limited_c6_characters_json,c6r1_characters_json,character_tags_json,risk_hits,relisting_fingerprint,notes
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(source_key) DO UPDATE SET
            provenance=excluded.provenance,platform=excluded.platform,external_id=excluded.external_id,url=excluded.url,
            title=excluded.title,seller=excluded.seller,server=excluded.server,ar=excluded.ar,price_value=excluded.price_value,
            currency=excluded.currency,market_status=excluded.market_status,status_confidence=excluded.status_confidence,
            status_evidence=excluded.status_evidence,observed_at=excluded.observed_at,limited_c6_count=excluded.limited_c6_count,
            c6r1_count=excluded.c6r1_count,limited_pulls=excluded.limited_pulls,history_richness=excluded.history_richness,
            discovery_headroom=excluded.discovery_headroom,resource_richness=excluded.resource_richness,
            legacy_collector_value=excluded.legacy_collector_value,archetypes_json=excluded.archetypes_json,
            limited_c6_characters_json=excluded.limited_c6_characters_json,c6r1_characters_json=excluded.c6r1_characters_json,
            character_tags_json=excluded.character_tags_json,risk_hits=excluded.risk_hits,relisting_fingerprint=excluded.relisting_fingerprint,notes=excluded.notes
        `).bind(
          String(r.source_key),String(r.provenance),r.platform??null,r.external_id??null,r.url??null,String(r.title),
          r.seller??null,r.server??null,r.ar??null,Number(r.price_value),String(r.currency).toUpperCase(),status,
          clamp(Number(r.status_confidence ?? r.confidence ?? 0.7),0,1),r.status_evidence??r.evidence??null,
          r.observed_at??nowIso(),r.limited_c6_count??0,r.c6r1_count??0,r.limited_pulls??null,
          r.history_richness??null,r.discovery_headroom??null,r.resource_richness??null,r.legacy_collector_value??null,
          JSON.stringify(r.archetypes??parseArray(r.archetypes_json)),
          JSON.stringify(r.limited_c6_characters??parseArray(r.limited_c6_characters_json)),
          JSON.stringify(r.c6r1_characters??parseArray(r.c6r1_characters_json)),
          JSON.stringify(r.character_tags??parseArray(r.character_tags_json)),r.risk_hits??0,
          r.relisting_fingerprint??null,r.notes??null
        ).run();
        imported++;
      }
      const stats = await historicalStats(env);
      return json({ ok: errors.length === 0, imported, errors, historical_stats: stats }, errors.length ? 207 : 201);
    }

    return json({ error: "not_found" }, 404);
  },
};
