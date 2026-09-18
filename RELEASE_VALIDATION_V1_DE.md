# Freigabeprotokoll v1.0

Stand: 18. September 2026

## Erfolgreich geprüft

- 89 Python-Tests.
- 6/6 bekannte Genshin-Benchmarkfälle.
- TypeScript-Typprüfung des Cloudflare Workers.
- SQL-Syntax für frisches Schema und Migration 0006.
- Idempotenz der neuen Warframe-Migration.
- YAML-Konfigurationen, Python-Bytecode und Bash-Syntax.
- systemd-Service und Timer mit `systemd-analyze verify`.
- Warframe-Erkennung: Übersichtsseiten-Lead löst keinen Alert aus; Detailseiten-Evidenz ist erforderlich.
- Budget außerhalb des Wunschbereichs bleibt meldbar.
- Discord-Payload deaktiviert Mentions; lokale SQLite-Deduplizierung ist getestet.

## Bewusst nicht im Paket ausgeführt

- Kein Deployment in das echte GitHub-Repository, auf den VPS oder zu Cloudflare ohne autorisierten Zugang.
- Kein echter Discord-Test ohne Webhook.
- Kein Kauf, Login oder Umgehen von Marktplatz-Schutzmaßnahmen.

## Annahme

Die Zahlen 100–200 für Genshin und bis 300 für Warframe werden als weiche EUR/USD-Orientierung ohne automatische Währungsumrechnung behandelt. Andere Währungen und Treffer außerhalb dieser Bereiche werden nicht ausgeschlossen.

## Quellen für die technische Umsetzung

- Discord Webhooks: https://docs.discord.com/developers/resources/webhook
- Cloudflare D1 Migrationen: https://developers.cloudflare.com/d1/reference/migrations/
