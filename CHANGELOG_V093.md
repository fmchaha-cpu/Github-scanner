# Genshin Market Tracker v0.9.3

Hotfix for GitHub Actions CI.

- Rewrites the two v0.9.2 async API batching tests to use `asyncio.run()` instead of requiring `pytest-asyncio`.
- Keeps the v0.9.2 production changes unchanged: 8-listing upload batches, hard cap 20, 60s API timeout.
- No Cloudflare Worker redeploy is required.
