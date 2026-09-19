from __future__ import annotations

import httpx


class V1Api:
    def __init__(self, base_url: str, token: str, timeout: float = 60):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.timeout = timeout

    async def get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    async def post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}{path}", headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def send_warframe(self, outcome, observation_policy: str = "full") -> dict:
        payload = outcome.model_dump()
        payload["observation_policy"] = observation_policy
        return await self.post("/v1/warframe/founder/batch", payload)
