# v0.9.1 hotfix

This hotfix fixes the GitHub Actions Worker preflight introduced in v0.9.0.

## Root cause

The v0.9.0 scan performed an unauthenticated `/health` request with Python's default `urllib` user agent before the collector was installed. In production that request received HTTP 403, so the scan stopped before tests or marketplace collection started.

## Fix

- Send the existing `MARKET_API_TOKEN` as a Bearer header during Worker health checks.
- Use the same browser-like user agent family as the collector instead of Python's default user agent.
- Add up to three health-check attempts with a short backoff.
- Print a bounded HTTP response body when a health check still fails so future failures are diagnosable.
- Apply the same behavior to the periodic `Market collector health` workflow.

No collector scoring, parsing, D1 schema, or Worker business logic changed from v0.9.0. No Cloudflare redeploy is required solely for this hotfix.
