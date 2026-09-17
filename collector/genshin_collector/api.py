from __future__ import annotations

import httpx
from .models import ListingObservation, CoverageRow


class MarketApi:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.timeout = timeout

    async def _post(self, path: str, payload: dict):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}{path}", headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json()

    async def start_scan(self, scan_id: str, version: str, notes: str | None = None):
        return await self._post("/v1/scan/start", {
            "id": scan_id,
            "collector_version": version,
            "notes": notes,
        })

    async def send_coverage(self, scan_id: str, rows: list[CoverageRow]):
        if not rows:
            return {"ok": True, "inserted": 0}
        return await self._post("/v1/coverage/batch", {
            "scan_run_id": scan_id,
            "rows": [r.model_dump() for r in rows],
        })

    async def send_listings(self, scan_id: str, rows: list[ListingObservation], batch_size: int = 40):
        total = 0
        changed = 0
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i+batch_size]
            res = await self._post("/v1/listings/batch", {
                "scan_run_id": scan_id,
                "listings": [r.model_dump() for r in chunk],
            })
            total += res.get("received", len(chunk))
            changed += res.get("changed", 0)
        return {"ok": True, "received": total, "changed": changed}

    async def send_system_event(
        self,
        component: str,
        severity: str,
        code: str,
        message: str,
        details_json: dict | None = None,
    ):
        return await self._post("/v1/system-event", {
            "component": component,
            "severity": severity,
            "code": code,
            "message": message,
            "details_json": details_json or {},
        })

    async def annotate_historical(
        self,
        listing_url: str,
        status: str,
        confidence: float = 0.8,
        evidence: str = "manual_annotation",
        notes: str | None = None,
        reviewer: str = "manual",
    ):
        return await self._post("/v1/historical/annotate", {
            "listing_url": listing_url,
            "status": status,
            "confidence": confidence,
            "evidence": evidence,
            "notes": notes,
            "reviewer": reviewer,
        })

    async def finish_scan(
        self,
        scan_id: str,
        status: str,
        source_count: int,
        listing_count: int,
        candidate_count: int,
        error_count: int,
        notes: str | None = None,
    ):
        return await self._post("/v1/scan/finish", {
            "id": scan_id,
            "status": status,
            "source_count": source_count,
            "listing_count": listing_count,
            "candidate_count": candidate_count,
            "error_count": error_count,
            "notes": notes,
        })
