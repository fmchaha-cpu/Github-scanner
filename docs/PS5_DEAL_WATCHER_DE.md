# PS5-Angebotswächter

Der separate VPS-Scanner beobachtet die normale PS5 als Disc- und Digital-Version. Er berücksichtigt nur neue und zertifiziert generalüberholte Geräte. Die PS5 Pro und private Gebrauchtangebote bleiben ausgeschlossen.

## Quellen und Alarmgrenzen

- Geizhals und Idealo: aktuelle deutsche Bestpreise für Neuware; der Scanner behält pro Modell nur das beste bestätigte Angebot.
- PlayStation Direct: offizielle Neuware und zertifiziert generalüberholte Konsolen.
- MediaMarkt: zusätzliche direkte Neuware-Angebote als Ausweichquelle.
- Digital neu: Alert bis 519,99 EUR; sehr guter Alert bis 469,99 EUR.
- Disc neu: Alert bis 569,99 EUR; sehr guter Alert bis 519,99 EUR.
- Zertifiziert generalüberholt: Alert bis 499,99 EUR (Digital) oder 549,99 EUR (Disc).

Ein Preisalarm wird nur bei bestätigter Verfügbarkeit ausgelöst. Bei PlayStation Direct fragt der Scanner dafür zusätzlich die öffentliche Produkt-API ab; ausgeblendete Platzhalter-Schaltflächen im HTML werden nicht als Lagerbestand gewertet. Ein Idealo-Bestpreis gilt als aktiver Preisvergleich. Fehlt bei einer direkten Händlerseite ein verlässlicher Lagerstatus, wird der Preis gespeichert, aber nicht gemeldet.

Die Regeln stehen in `collector/ps5_sources.yaml` und können später ohne Codeänderung angepasst werden.

## Speicherung und Deduplizierung

Preise, Tiefstpreise, Scanläufe und bereits versandte Alerts werden lokal unter `/var/lib/genshin-scanner/ps5-deals.sqlite3` gespeichert. D1 wird dafür nicht verwendet. Derselbe Preis wird nur einmal gemeldet. Ein erneuter Alert entsteht erst bei mindestens 10 EUR Preisrückgang oder wenn ein Angebot die Stufe `excellent` erreicht.

## Installation auf der VPS

Nach `git pull origin main`:

```bash
sudo bash scripts/install_vps_ps5.sh
sudo systemctl start ps5-deal-scanner.service
sudo journalctl -u ps5-deal-scanner.service -n 100 --no-pager -l
```

Bei einem erfolgreichen One-shot-Lauf steht der Dienst danach wieder auf `inactive (dead)`; entscheidend ist `status=0/SUCCESS` beziehungsweise `Deactivated successfully`.

Wenn der Test erfolgreich war:

```bash
sudo systemctl start ps5-deal-scanner.timer
systemctl list-timers --all | grep ps5-deal
```

Der nächste Lauf wird ungefähr 15 Minuten nach dem Ende des vorherigen Laufs geplant. Ein gemeinsames `flock` verhindert, dass gleichzeitig ein Account- und PS5-Browserscan läuft.

## Discord

Optional kann in `/etc/genshin-scanner.env` ein eigener Kanal verwendet werden:

```text
DISCORD_WEBHOOK_PS5=https://discord.com/api/webhooks/...
```

Ohne eigenen PS5-Webhook wird zuerst der vorhandene Genshin-Webhook und danach `DISCORD_WEBHOOK_URL` verwendet. Webhook-Adressen niemals committen oder in Screenshots veröffentlichen.

## Backup

Die Datenbank ist klein und läuft im SQLite-WAL-Modus. Für ein konsistentes Backup während des Betriebs:

```bash
sudo -u market-scanner sqlite3 /var/lib/genshin-scanner/ps5-deals.sqlite3 ".backup '/var/lib/genshin-scanner/ps5-deals-backup.sqlite3'"
```

Die erzeugte Backup-Datei kann anschließend auf den Computer oder einen USB-Stick kopiert werden.
