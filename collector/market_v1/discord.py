from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

import httpx


COLORS = {"dream": 0xB76EFF, "strong": 0x2ECC71, "review": 0xF1C40F, "health": 0xE67E22}


def _safe(value: object, limit: int = 1000) -> str:
    # Prevent user-controlled marketplace text from pinging Discord users or roles.
    return str(value or "").replace("@", "＠").replace("`", "ʼ")[:limit]


def listing_payload(game: str, tier: str, row: dict) -> dict:
    price = "Preis unbekannt"
    if row.get("price_value") is not None:
        price = f"{row['price_value']:g} {row.get('currency') or ''}".strip()
    fields = [{"name": "Preis", "value": _safe(price), "inline": True}]
    if game == "Warframe":
        fields.extend([
            {"name": "Evidenz", "value": _safe(row.get("evidence_level")), "inline": True},
            {"name": "Founder-Items genannt", "value": _safe(", ".join(row.get("prime_items") or []) or "keine"), "inline": False},
        ])
        footer = "Nur Angebots-Evidenz – Echtheit, Besitz und Übertragbarkeit manuell prüfen."
    else:
        budget = "unbekannt"
        if row.get("price_value") is not None:
            budget = "im Wunschbereich" if 100 <= float(row["price_value"]) <= 200 else "außerhalb Wunschbereich – trotzdem gemeldet"
        fields.extend([
            {"name": "Profil", "value": _safe(row.get("archetype") or "mehrere Profile"), "inline": True},
            {"name": "Priorität", "value": _safe(row.get("collector_priority")), "inline": True},
            {"name": "Verifikation", "value": _safe(row.get("verification_level") or "unbekannt"), "inline": True},
            {"name": "Budget", "value": budget, "inline": False},
        ])
        footer = "Marktwert, Sicherheit und persönlicher Fit getrennt manuell prüfen."
    return {
        "username": "Dream Account Scanner",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": _safe(f"{game}: {tier.upper()} – {row.get('title')}", 250),
            "url": str(row.get("url") or ""),
            "color": COLORS.get(tier, COLORS["review"]),
            "fields": fields,
            "footer": {"text": footer},
        }],
    }


class AlertState:
    def __init__(self, path: str):
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS sent_alerts (alert_key TEXT PRIMARY KEY, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        self.db.commit()

    def seen(self, key: str) -> bool:
        return self.db.execute("SELECT 1 FROM sent_alerts WHERE alert_key=?", (key,)).fetchone() is not None

    def mark(self, key: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO sent_alerts(alert_key) VALUES (?)", (key,))
        self.db.commit()


async def send(webhook: str, payload: dict) -> None:
    separator = "&" if "?" in webhook else "?"
    url = webhook + separator + urlencode({"wait": "true"})
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
