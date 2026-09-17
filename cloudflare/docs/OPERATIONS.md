# Betrieb und Zuverlaessigkeit

## Was als gesund gilt

- `/health` antwortet.
- Letzter `scan_run` ist juenger als 3 Stunden.
- Kein wichtiger Marktplatz meldet ueber mehrere Runs nur `error`.
- Trefferzahlen fallen nicht ploetzlich dauerhaft auf 0.
- `coverage` zeigt getrennt, was wirklich gescannt wurde und was nicht.

## Was das System bewusst NICHT behauptet

Es gibt keine Garantie auf 100 % Marktabdeckung. Marktplatz-HTML, Pagination, JavaScript und Anti-Bot-Regeln koennen sich aendern. Zuverlaessigkeit entsteht deshalb aus:

1. mehreren Quellen,
2. mehreren Query-/Kategoriepfaden,
3. Coverage-Logging,
4. Healthchecks,
5. Snapshots und Deduplizierung,
6. ChatGPT als unabhaengiger zweiter Verifikationskanal.

## Wenn ein Adapter kaputtgeht

1. GitHub Actions -> letzter fehlgeschlagener Run -> Log ansehen.
2. Cloudflare `/v1/coverage/recent?hours=24` pruefen.
3. Betroffene Source in `collector/sources.yaml` voruebergehend `enabled: false` setzen.
4. URL/Detail-Pattern aktualisieren.
5. `workflow_dispatch` manuell starten.
6. Erst wieder als abgedeckt behandeln, wenn Coverage echte Treffer zeigt.

## Empfehlenswerte Frequenz

Der mitgelieferte Workflow laeuft bei Minute 17 und 47. Das ist absichtlich nicht exakt zur vollen Stunde. GitHub weist darauf hin, dass geplante Workflows bei hoher Last verzoegert oder in seltenen Faellen verworfen werden koennen, insbesondere am Stundenanfang.

## Oeffentliches Repository oder privat?

Ein **oeffentliches Repo** ist technisch fuer dieses Projekt attraktiv: Standard-GitHub-Runner sind dort kostenlos; Secrets bleiben trotzdem als GitHub Actions Secrets gespeichert und werden nicht ins Repo geschrieben. Der Code enthaelt keine privaten Daten.

Wenn du das Repo privat halten willst, funktioniert alles ebenfalls, aber GitHub-Free hat ein monatliches Actions-Minutenkontingent. Dann wuerde ich den Scan eher stuendlich statt alle 30 Minuten ausfuehren.
