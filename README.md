# Genshin Market Tracker v0.5.0

Hybrid-System fuer hohe Markt-Abdeckung, identity-bound Verifikation, historische Preisvergleiche und kontinuierliche Qualitaetsverbesserung.

## Was v0.5 wirklich hinzufuegt

- **Historical Comparable Engine**: Historische Angebote bleiben getrennt vom Live-Markt und dienen als gewichtete Vergleichsanker.
- **Status-Taxonomie**: `STRICT_LIVE`, `ACTIVE_UNCONFIRMED`, `SOLD_CONFIRMED`, `SOLD_CLAIMED`, `EXPIRED_REMOVED`, `OUTCOME_UNKNOWN`, `RISK_CONTAMINATED`.
- **Konservative Entfernungserkennung**: Erst nach 3 Misses in jedem bekannten, erfolgreich erneut gescannten Suchpfad wird ein Listing als `EXPIRED_REMOVED` markiert. Ein Verschwinden wird niemals als Verkauf interpretiert.
- **Verkaufs-Evidenz statt falscher Gewissheit**: `SOLD_CONFIRMED` bedeutet, dass die exakte Listing-Seite den Status verkauft/geschlossen zeigt. Es beweist nicht, dass der angezeigte Preis der tatsaechlich gezahlte Transaktionspreis war.
- **Comparable Sets**: Vergleich nach Server, Waehrung, AR, C6/C6R1, Character-Signatur, Pull-Reserve, Living-History-, Discovery-, Resource- und Legacy-Profilen sowie Archetypen.
- **Keine stille FX-Mischung**: EUR/USD/GBP werden nur innerhalb derselben Waehrung verglichen. Keine erfundene Wechselkurs-Praezision.
- **Zeitgewichtung**: Historische Evidenz verliert mit dem Alter langsam Gewicht; alte seltene Legacy-Anker bleiben mit kleinem Mindestgewicht erhalten.
- **Relisting-/Duplicate-Erkennung**: Fingerprints schlagen moegliche Wiederverkaeufe/Duplikate vor. Nichts wird automatisch zusammengefuehrt.
- **Importierbare Historie**: Saubere historische Workbook-/Recherche-Anker koennen ueber `/v1/historical/import` in einen separaten Datensatz importiert werden.
- **Quality Loop**: Nach Scans werden Qualitaets-Snapshots und konkrete Verbesserungssignale gespeichert (Seller-/Server-/Preis-Extraction, Zero-Hit-Queries, Historical-Pool, Source Errors, Duplicate Review usw.).
- **Feedback Loop**: False Positives, False Negatives und Parserprobleme koennen ueber `/v1/review-feedback` dokumentiert und spaeter in Regressionstests uebernommen werden.
- **Breitere Account-Signatur**: Nicht nur C6-Charaktere, sondern erkannte Charakter-Tags helfen bei Comparables und Duplicate-Vorschlaegen.
- **Stündlicher Scan**: Ein Lauf pro Stunde, damit das Runtime-Budget in Pagination und Deep Verification fliesst.

## Wichtigste Read-only Endpunkte

```text
/health
/v1/candidates/recent?hours=24
/v1/review-queue
/v1/coverage/recent?hours=24
/v1/quality/recent?hours=24
/v1/quality/snapshots?limit=20
/v1/historical/recent?limit=100
/v1/comparables?url=<URL-ENCODED-LISTING>&limit=30
/v1/duplicates/recent?hours=168
/v1/status/history?url=<URL-ENCODED-LISTING>
/v1/feedback/summary?days=30
```

## Schreib-Endpunkte (Bearer Token)

```text
POST /v1/historical/annotate
POST /v1/historical/import
POST /v1/review-feedback
```

## Rollen im System

- Collector = Recall + Triage + Evidenz sammeln.
- D1 = Rohdaten, Snapshots, Statushistorie, historische Anker, Coverage, Feedback.
- Comparable Engine = deskriptiver Marktvergleich, keine Kaufentscheidung.
- ChatGPT/Human Review = tiefe Pruefung von Identitaet, Security, Seller, Relevanz und finaler Interpretation.
- Excel = taeglicher Analyse-/Ranking-Output; nicht primaere Rohdatenbank.

## Upgrade von deinem aktuellen Repo

Siehe **`docs/V05_UPGRADE_DE.md`**. Fuer deinen bestehenden D1 ist die eingetragene `database_id` bereits die bekannte `genshin-market` Datenbank; der Token wird nicht veraendert.

## Grenzen

Keine Garantie auf 100 % Markt-Abdeckung. Keine Umgehung von Login, CAPTCHA, Rate Limits oder Anti-Bot-Schutz. Marktplatz-HTML kann sich aendern. Historische Asking-Prices sind nicht automatisch tatsaechliche Settlement-Prices. Deshalb werden Evidenzstaerke, Datenqualitaet und Unsicherheit explizit gespeichert.
