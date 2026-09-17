# v0.9.2 hotfix

The v0.9.1 production scan reached the real marketplace collector, passed the Worker handshake, installed dependencies, and passed all 72 tests. It then failed while uploading the first large listing batch to Cloudflare D1 with `httpx.ReadTimeout`.

## Fix

- Reduce listing upload chunks from 40 rows to 8 rows by default.
- Cap any caller-provided listing batch at 20 rows.
- Increase the API client timeout from 30s to 60s.
- Deliberately avoid blind retries for ambiguous timed-out writes, because the Worker may already have persisted part of a batch and retrying could duplicate snapshot evidence.
- Add unit tests for default chunking and hard batch caps.

No Worker schema or business logic changed. A Cloudflare redeploy is not required for this hotfix; Worker v0.9 is compatible.
