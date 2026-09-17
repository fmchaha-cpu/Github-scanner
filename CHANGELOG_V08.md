# v0.8.0 — hydration repair, deployment handshake, historical intelligence

## Why this version exists

v0.7 proved the circuit breaker works: the real scan dropped from roughly six minutes to about one minute without losing the 79-listing baseline. Two systematic weaknesses remained visible in repeated runs: ZeusX seller/live-detail evidence regressed, and the collector log still showed `historical_anchor_observations=0` even when the separate historical repertoire could already exist in D1.

## Core changes

- **False block-signal repair**: CAPTCHA/challenge words inside hidden scripts no longer make a healthy marketplace page look blocked.
- **Hydration-aware browser timing**: challenge pages still return quickly, while real ZeusX/PlayerUp pages with listing links receive a short settle period so seller/profile widgets can render.
- **ZeusX seller recovery**: seller extraction can use profile-link text, profile image alt text, and detail-page sidebars outside `<main>`.
- **Strong live-control evidence**: exact interactive controls such as `Buy Now` / `Add to cart` can establish detail-page availability without trusting generic marketing text; controls linking to unrelated listings are ignored.
- **Worker/collector deployment handshake**: GitHub Actions and the collector itself verify that the Worker reports v0.8 and the expected capabilities before scanning; stale deployments now fail closed instead of silently degrading telemetry.
- **Historical stats endpoint**: `/v1/historical/stats` separates the persistent historical repertoire from historical statuses encountered in the current live scan.
- **Verified historical seed import**: the import workflow now verifies the number of tracker seed rows and confirmed-sold anchors after upsert.
- **Passive comparable intelligence**: after ingesting current listings, the collector asks the Comparable Engine for historical evidence on up to eight top candidates and records median/spread/confidence without changing alerts yet.
- **Richer version benchmarks**: v0.8 quality events include historical-pool size, confirmed sold count, candidate comparable coverage, and Worker compatibility.

## Evidence rules

- Marketplace anti-bot controls are not bypassed.
- Script references to CAPTCHA/challenge libraries are ignored only when the visible page is otherwise usable; visible human-check/challenge pages still trigger the breaker.
- Interactive purchase controls are used as live evidence only on the listing detail page.
- Historical comparisons remain descriptive. `SOLD_CONFIRMED` confirms sold/closed evidence for the listing, not the exact final settlement price.
- Comparable output is passive telemetry in v0.8; it does not autonomously promote a candidate to an alert.
