# v1.0 auf dem Contabo-VPS installieren

Die Anleitung nimmt das vorhandene Repository unter `/opt/Github-scanner` und Ubuntu 24.04 an.

## 1. Code aktualisieren

```bash
cd /opt/Github-scanner
sudo git pull --ff-only origin main
```

Vorher lokale Serveränderungen mit `git status --short` prüfen. Das Installationsskript überschreibt keine vorhandene Secret-Datei.

## 2. D1-Migration und Worker ausrollen

Auf einem Rechner mit gültigem Cloudflare-Login:

```bash
cd cloudflare
npm ci
npm run typecheck
npm run db:migrate:v10
npm run deploy
```

Danach muss `GET /health` die Version `1.0` und die Fähigkeiten `multi_game` sowie `warframe_founder` melden. Erst dann den v1-Collector starten.

## 3. VPS-Dienst installieren

```bash
cd /opt/Github-scanner
sudo bash scripts/install_vps_v1.sh
sudo nano /etc/genshin-scanner.env
```

Mindestens ausfüllen:

```dotenv
MARKET_API_URL=https://DEIN-WORKER.workers.dev
MARKET_API_TOKEN=DEIN_LANGES_TOKEN
DISCORD_WEBHOOK_GENSHIN=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_WARFRAME=https://discord.com/api/webhooks/...
ALERT_STATE_DB=/var/lib/genshin-scanner/alerts.sqlite3
PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
```

Dann zuerst genau einen kontrollierten Lauf ausführen:

```bash
sudo systemctl start market-scanner.service
sudo systemctl status market-scanner.service --no-pager
sudo journalctl -u market-scanner.service -n 150 --no-pager
```

Wenn der Lauf erfolgreich war:

```bash
sudo systemctl start market-scanner.timer
systemctl list-timers market-scanner.timer
```

Der Timer läuft ungefähr alle 30 Minuten mit zufälliger Verzögerung. Die zufällige Verzögerung und quellenspezifische Pausen vermeiden unnötig starre Zugriffsmuster; Sperrseiten werden protokolliert und nicht umgangen.

## 4. GitHub als Fallback

Der Workflow **Genshin market scan** hat keinen Zeitplan mehr. Er kann unter **Actions → Genshin market scan → Run workflow** manuell gestartet werden. Dafür in GitHub folgende Secrets setzen:

- `MARKET_API_URL`
- `MARKET_API_TOKEN`
- `DISCORD_WEBHOOK_GENSHIN`
- `DISCORD_WEBHOOK_WARFRAME`

`Quality checks` läuft weiter bei Änderungen. Health und Audit sind manuell startbare Diagnose-Workflows; dadurch konkurrieren sie nicht mit dem VPS.

## 5. Betrieb

```bash
journalctl -u market-scanner.service --since today --no-pager
systemctl status market-scanner.timer --no-pager
curl -fsS "$MARKET_API_URL/health"
```

Rollback: Timer stoppen, vorherigen Git-Stand deployen und erst danach wieder starten. Migration 0006 fügt nur separate Tabellen hinzu und verändert keine Genshin-Tabelle.
