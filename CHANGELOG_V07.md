# v0.7.0 — Source health, provenance, benchmarks, historical seeds

## Core changes

- **In-run circuit breaker**: a confirmed blocked/challenge page with zero listings can stop the remaining searches for that marketplace in the same run.
- **Persistent source health**: repeated blocked or zero-yield scans create a temporary cooldown in D1. The collector reads `/v1/source-health` before scanning and skips a source while the cooldown is active.
- **Faster challenge handling**: Playwright contexts are reused and obvious challenge pages return early instead of waiting for network-idle.
- **HTTP diagnostics**: HTTP status plus a small allow-list of non-sensitive response headers is recorded for parser/block analysis.
- **Field provenance**: price/server/seller/title/resources/etc. record where the value came from (card text, profile link, detail text, JSON-LD, URL...).
- **Adaptive verification v2**: candidate checks + calibration-gap samples + control samples.
- **Stale quality flag repair**: derived flags are recomputed after detail verification.
- **Exact scan benchmarks**: `/v1/quality/by-version` compares collector quality events version-by-version instead of mixing rolling 24h windows.
- **Known-case regression corpus**: six benchmark accounts cover cheap limited C6, favorite C6, standard-banner C6, dormant veteran, risk flags, and 500+ pulls.
- **Historical seed**: 17 price-known rows from the existing tracker Historical_View v26 can be imported once through GitHub Actions. Unconfirmed outcomes stay explicitly low-confidence.

## Safety / evidence rules

- No CAPTCHA, login, rate-limit or anti-bot bypass is added.
- Blocked pages are not counted as successful rescans for disappearance detection.
- Historical tracker imports preserve their evidence label; a sold/closed listing is not treated as proof of the final settlement price.
- Imported tracker rows with an unknown original observation date receive conservative recency weighting.

- **Efficiency telemetry:** scan quality now reports fetch paths avoided by the in-run circuit breaker or persistent cooldown, so we can measure saved requests/time instead of guessing.
