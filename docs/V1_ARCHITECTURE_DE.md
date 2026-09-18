# Scanner v1.0 – Architektur

## Zielbild

Der Contabo-VPS ist der Hauptscanner. GitHub Actions führt Tests bei Änderungen aus und bietet einen manuell startbaren Fallback-Scan. Cloudflare Worker + D1 bleiben die zentrale API und Historie. Discord ist der schnelle Benachrichtigungskanal.

Genshin und Warframe teilen nur Betrieb und Benachrichtigung. Tabellen, Detektoren, Scores und Vergleichsdaten bleiben getrennt.

## Entscheidungslogik

### Genshin

- Wunschbereich: 100–200 (nur Präferenz, kein Filter).
- Parallel bewertete Profile: Living History/Dormant Veteran, Favorite Character, Value C6/Collector, Resource Rich, Living Archive.
- Discord nur für geprüfte Review-, Strong- oder Dream-Kandidaten.
- Marktwert, Sicherheit und persönlicher Erlebniswert bleiben getrennte Aussagen.

### Warframe Founder

- Wunschbereich: bis 300 (nur Präferenz, kein Filter).
- `POTENTIAL_LEAD`: Founder- oder Prime-Begriff auf einer öffentlichen Übersichtsseite. Wird gespeichert, aber nicht alarmiert.
- `CLAIM_EVIDENCE`: Detailseite nennt Founder und mindestens eines von Excalibur Prime, Lato Prime oder Skana Prime. Erst dann ist Discord möglich.
- Das ist Angebots-Evidenz, niemals Beweis für Echtheit, Besitz oder sichere Übertragbarkeit.

## Sicherheitsgrenzen

- Nur öffentliche Seiten; kein Login-, CAPTCHA-, Rate-Limit- oder Anti-Bot-Bypass.
- Webhook-Geheimnisse stehen nur in `/etc/genshin-scanner.env` beziehungsweise GitHub Secrets.
- Discord-Mentions sind deaktiviert und fremde Marktplatztexte werden entschärft.
- SQLite-Deduplizierung verhindert wiederholte Meldungen desselben Treffers/Tiers.
- `flock` verhindert parallele VPS-Läufe.

## API v1.0

- `GET /health`
- `GET /v1/candidates/recent` (Genshin)
- `GET /v1/warframe/founder/recent`
- `GET /v1/warframe/founder/alerts`
- `POST /v1/warframe/founder/batch` (Bearer-Token erforderlich)

Die Warframe-Antwort enthält immer einen Caveat zur nicht geprüften Echtheit.
