export interface Env {
  DB: D1Database;
  INGEST_TOKEN: string;
}

type Json = Record<string, unknown>;

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

async function upsertListing(env: Env, o: any, scanRunId: string) {
  const existing = await env.DB.prepare(
    "SELECT id, raw_hash, price_value, availability, seller FROM listings WHERE url = ?"
  ).bind(o.url).first();

  const changed = !existing || existing.raw_hash !== o.raw_hash || existing.price_value !== o.price_value || existing.availability !== o.availability || existing.seller !== o.seller;
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
    ) VALUES (
      ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
    )
    ON CONFLICT(url) DO UPDATE SET
      external_id=excluded.external_id,
      title=excluded.title,
      seller=COALESCE(excluded.seller, listings.seller),
      server=COALESCE(excluded.server, listings.server),
      ar=COALESCE(excluded.ar, listings.ar),
      price_value=COALESCE(excluded.price_value, listings.price_value),
      currency=COALESCE(excluded.currency, listings.currency),
      availability=COALESCE(excluded.availability, listings.availability),
      instant_delivery=excluded.instant_delivery,
      after_sale_protection=COALESCE(excluded.after_sale_protection, listings.after_sale_protection),
      last_seen=excluded.last_seen,
      last_changed=CASE WHEN ? THEN excluded.last_seen ELSE listings.last_changed END,
      raw_text=excluded.raw_text,
      raw_hash=excluded.raw_hash,
      data_confidence=excluded.data_confidence,
      security_hint=excluded.security_hint,
      limited_c6_count=excluded.limited_c6_count,
      c6r1_count=excluded.c6r1_count,
      multi_c6=excluded.multi_c6,
      primogems=excluded.primogems,
      intertwined=excluded.intertwined,
      limited_pulls=excluded.limited_pulls,
      legacy_hits=excluded.legacy_hits,
      history_hits=excluded.history_hits,
      discovery_hits=excluded.discovery_hits,
      resource_hits=excluded.resource_hits,
      archetype=excluded.archetype,
      history_richness=excluded.history_richness,
      discovery_headroom=excluded.discovery_headroom,
      resource_richness=excluded.resource_richness,
      organic_account_feel=excluded.organic_account_feel,
      legacy_collector_value=excluded.legacy_collector_value,
      personal_experience_fit=excluded.personal_experience_fit,
      collector_priority=excluded.collector_priority,
      detector_reason=excluded.detector_reason,
      is_candidate=excluded.is_candidate,
      is_alert_candidate=excluded.is_alert_candidate,
      last_scan_run_id=excluded.last_scan_run_id
  `).bind(
    o.platform, o.external_id ?? null, o.url, o.title, o.seller ?? null, o.server ?? null,
    o.ar ?? null, o.price_value ?? null, o.currency ?? null, o.availability ?? null,
    o.instant_delivery ? 1 : 0, o.after_sale_protection ?? null,
    firstSeen ?? o.observed_at ?? nowIso(), o.observed_at ?? nowIso(),
    lastChanged ?? o.observed_at ?? nowIso(), o.raw_text ?? null, o.raw_hash ?? null,
    o.data_confidence ?? null, o.security_hint ?? null, o.limited_c6_count ?? 0,
    o.c6r1_count ?? 0, o.multi_c6 ? 1 : 0, o.primogems ?? null,
    o.intertwined ?? null, o.limited_pulls ?? null, o.legacy_hits ?? 0,
    o.history_hits ?? 0, o.discovery_hits ?? 0, o.resource_hits ?? 0,
    o.archetype ?? null, o.history_richness ?? null, o.discovery_headroom ?? null,
    o.resource_richness ?? null, o.organic_account_feel ?? null,
    o.legacy_collector_value ?? null, o.personal_experience_fit ?? null,
    o.collector_priority ?? 0, o.detector_reason ?? null, o.is_candidate ? 1 : 0,
    o.is_alert_candidate ? 1 : 0, scanRunId, changed ? 1 : 0
  ).run();

  const row = await env.DB.prepare("SELECT id FROM listings WHERE url = ?").bind(o.url).first();
  if (!row) throw new Error("listing upsert did not return an id");

  await env.DB.prepare(`
    INSERT INTO listing_snapshots (listing_id, observed_at, price_value, currency, availability, seller, raw_hash, raw_text, changed)
    VALUES (?,?,?,?,?,?,?,?,?)
  `).bind(row.id, o.observed_at ?? nowIso(), o.price_value ?? null, o.currency ?? null,
    o.availability ?? null, o.seller ?? null, o.raw_hash ?? null, o.raw_text ?? null, changed ? 1 : 0).run();

  if (o.is_candidate) {
    await env.DB.prepare(`
      INSERT INTO candidate_events (listing_id, scan_run_id, created_at, priority, reason, event_type, detector_version)
      VALUES (?,?,?,?,?,?,?)
    `).bind(row.id, scanRunId, o.observed_at ?? nowIso(), o.collector_priority ?? 0,
      o.detector_reason ?? "candidate", changed ? "new_or_changed" : "seen_again", o.detector_version ?? "v1").run();
  }

  return { id: row.id, changed };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET,POST,OPTIONS",
          "access-control-allow-headers": "authorization,content-type",
        },
      });
    }

    if (request.method === "GET" && path === "/health") {
      const db = await env.DB.prepare("SELECT COUNT(*) AS n FROM listings").first();
      const last = await env.DB.prepare("SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 1").first();
      return json({ ok: true, listing_count: db?.n ?? 0, last_scan: last ?? null, now: nowIso() });
    }

    // Public feed: only marketplace-public facts, no tokens or private user data.
    if (request.method === "GET" && path === "/v1/candidates/recent") {
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "24"), 1), 168);
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "100"), 1), 500);
      const since = new Date(Date.now() - hours * 3600_000).toISOString();
      const result = await env.DB.prepare(`
        SELECT platform, external_id, url, title, seller, server, ar, price_value, currency,
               availability, instant_delivery, after_sale_protection, last_seen,
               limited_c6_count, c6r1_count, primogems, intertwined, limited_pulls,
               legacy_hits, history_hits, discovery_hits, resource_hits, archetype,
               history_richness, discovery_headroom, resource_richness,
               organic_account_feel, legacy_collector_value, personal_experience_fit,
               collector_priority, detector_reason, data_confidence, security_hint
        FROM listings
        WHERE is_candidate = 1 AND last_seen >= ?
        ORDER BY collector_priority DESC, last_seen DESC
        LIMIT ?
      `).bind(since, limit).all();
      return json({ since, count: result.results.length, candidates: result.results });
    }

    if (request.method === "GET" && path === "/v1/coverage/recent") {
      const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || "24"), 1), 168);
      const since = new Date(Date.now() - hours * 3600_000).toISOString();
      const result = await env.DB.prepare(`
        SELECT scan_run_id, platform, query_family, query_text, page_label, status,
               result_count, error, observed_at
        FROM coverage WHERE observed_at >= ?
        ORDER BY observed_at DESC
        LIMIT 1000
      `).bind(since).all();
      return json({ since, rows: result.results });
    }

    if (!isAuthorized(request, env)) return unauthorized();

    if (request.method === "POST" && path === "/v1/scan/start") {
      const body = await readJson<any>(request);
      await env.DB.prepare(`
        INSERT INTO scan_runs (id, started_at, collector_version, status, notes)
        VALUES (?,?,?,?,?)
      `).bind(body.id, body.started_at || nowIso(), body.collector_version || null, "running", body.notes || null).run();
      return json({ ok: true, id: body.id }, 201);
    }

    if (request.method === "POST" && path === "/v1/coverage/batch") {
      const body = await readJson<{ scan_run_id: string; rows: any[] }>(request);
      const statements = body.rows.map((r) => env.DB.prepare(`
        INSERT INTO coverage (scan_run_id, platform, query_family, query_text, page_label, status, result_count, error, observed_at)
        VALUES (?,?,?,?,?,?,?,?,?)
      `).bind(body.scan_run_id, r.platform, r.query_family, r.query_text ?? null,
        r.page_label ?? null, r.status, r.result_count ?? 0, r.error ?? null,
        r.observed_at ?? nowIso()));
      for (let i = 0; i < statements.length; i += 40) {
        await env.DB.batch(statements.slice(i, i + 40));
      }
      return json({ ok: true, inserted: statements.length });
    }

    if (request.method === "POST" && path === "/v1/listings/batch") {
      const body = await readJson<{ scan_run_id: string; listings: any[] }>(request);
      let changed = 0;
      for (const observation of body.listings) {
        const res = await upsertListing(env, observation, body.scan_run_id);
        if (res.changed) changed++;
      }
      return json({ ok: true, received: body.listings.length, changed });
    }

    if (request.method === "POST" && path === "/v1/scan/finish") {
      const body = await readJson<any>(request);
      await env.DB.prepare(`
        UPDATE scan_runs SET finished_at=?, status=?, source_count=?, listing_count=?, candidate_count=?, error_count=?, notes=?
        WHERE id=?
      `).bind(body.finished_at || nowIso(), body.status || "ok", body.source_count || 0,
        body.listing_count || 0, body.candidate_count || 0, body.error_count || 0,
        body.notes || null, body.id).run();
      return json({ ok: true });
    }

    if (request.method === "POST" && path === "/v1/system-event") {
      const body = await readJson<any>(request);
      await env.DB.prepare(`
        INSERT INTO system_events (created_at, component, severity, code, message, details_json)
        VALUES (?,?,?,?,?,?)
      `).bind(body.created_at || nowIso(), body.component || "unknown", body.severity || "info",
        body.code || null, body.message || "", body.details_json ? JSON.stringify(body.details_json) : null).run();
      return json({ ok: true }, 201);
    }

    return json({ error: "not_found" }, 404);
  },
};
