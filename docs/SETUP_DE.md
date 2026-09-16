# Einrichtung – Schritt fuer Schritt

## Was du brauchst

- kostenloses Cloudflare-Konto
- GitHub-Konto
- Windows-PC fuer die erste Einrichtung
- Git
- Node.js LTS

Python musst du lokal nicht zwingend installieren, wenn der Collector nur in GitHub Actions laufen soll.

---

## 1. Projekt in GitHub hochladen

1. Auf GitHub ein neues Repository erstellen, z. B. `genshin-market-tracker`.
2. Fuer kostenlose haeufige Actions am einfachsten **Public** waehlen. Es werden keine Passwoerter oder privaten Accountdaten ins Repository geschrieben.
3. Dieses Projekt entpacken.
4. In PowerShell im Projektordner:

```powershell
git init
git add .
git commit -m "Initial Genshin market infrastructure"
git branch -M main
git remote add origin https://github.com/DEINNAME/genshin-market-tracker.git
git push -u origin main
```

---

## 2. Cloudflare Worker + D1 einrichten

Node.js LTS installieren, danach im Projektordner PowerShell starten:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_cloudflare.ps1
```

Das Skript:

1. installiert Wrangler,
2. oeffnet Cloudflare-Login,
3. erstellt D1,
4. laesst dich die `database_id` in `cloudflare/wrangler.toml` eintragen,
5. spielt das Schema ein,
6. erzeugt einen zufaelligen Schreib-Token,
7. speichert ihn als Cloudflare Secret,
8. deployt den Worker.

Am Ende bekommst du etwa:

```text
https://genshin-market-api.<dein-subdomain>.workers.dev
```

Teste im Browser:

```text
https://...workers.dev/health
```

Es sollte JSON mit `"ok": true` erscheinen.

---

## 3. GitHub Actions Secrets setzen

GitHub Repository -> **Settings -> Secrets and variables -> Actions -> New repository secret**.

Zwei Secrets:

### MARKET_API_URL

```text
https://genshin-market-api.<dein-subdomain>.workers.dev
```

### MARKET_API_TOKEN

In der lokalen Datei:

```text
.generated_ingest_token.txt
```

Den Inhalt kopieren. Die Datei niemals hochladen; `.gitignore` schuetzt sie bereits.

---

## 4. Ersten Scan starten

GitHub -> Repository -> **Actions -> Genshin market scan -> Run workflow**.

Nach erfolgreichem Lauf oeffnen:

```text
https://...workers.dev/health
```

und

```text
https://...workers.dev/v1/candidates/recent?hours=24
```

Der zweite Link ist absichtlich nur ein **read-only Feed aus oeffentlichen Marktplatzdaten**. Er enthaelt keine Secrets. Diesen Link kann spaeter auch ChatGPT regelmaessig lesen.

---

## 5. ChatGPT anbinden

Wenn der Worker funktioniert, gib ChatGPT diese URL:

```text
https://...workers.dev
```

Dann kann die bestehende Markt-Automation zuerst den Collector-Feed pruefen und danach nur die interessanten Kandidaten auf ihren exakten Produktseiten tief verifizieren.

Empfohlener Ablauf:

```text
GET /v1/candidates/recent?hours=2
GET /v1/coverage/recent?hours=24
```

Danach weiterhin unabhaengige Websuche als zweite Quelle, damit ein kaputter Collector nicht unbemerkt zum Single Point of Failure wird.

---

## 6. Excel

Die D1-Datenbank wird die Rohdatenquelle. Deine bestehende Datei

`/Genshin Market Tracker/Genshin_Account_Market_Tracker(1).xlsx`

bleibt der Analyse-/Ranking-Tracker und wird nur einmal taeglich gebuendelt aktualisiert. Dadurch sollte die Library-Bestaetigung nicht mehr stuendlich erscheinen.

---

## 7. Was noch manuell kalibriert werden muss

Nach den ersten 2–3 Runs schauen wir gemeinsam in `/v1/coverage/recent` und die Actions-Logs. Dann koennen wir fuer jede Plattform sehen:

- Parser liefert echte Listings -> aktiv lassen.
- Seite ist JavaScript-lastig -> Browser-Fallback optimieren.
- URL/Pattern falsch -> Adapter korrigieren.
- Zugriff blockiert -> nicht umgehen; Quelle auf partial setzen und ueber ChatGPT/Websuche abdecken.

Das ist kein Fehler des Designs, sondern absichtlich sichtbar gemachte Source-Health.
