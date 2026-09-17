# Quality Loop v0.2

Ziel: hohe Recall **und** sichtbar machen, wo der Collector noch unzuverlaessig ist.

## Neue Qualitaetsebenen

Der Collector trennt jetzt:

1. **Card observation** – Listing-Karte/Index, gut fuer breite Discovery.
2. **Detail verification** – exakte Produktseite wird erneut gelesen.
3. **Identity verified** – Detailseite hat belastbare Evidenz fuer Listing-ID/URL, Preis, Server, Seller und das kaufrelevante Kernmerkmal.
4. **Strict live** – Identity verified **und** die Detailseite selbst zeigt aktuell `BUY NOW`, `In Stock` oder `Available`.
5. **Review gate** – nur ein sehr seltener, streng verifizierter Kandidat fuer ChatGPT/Human-Review. Das ist **kein automatischer Kaufalarm**.

Fehlende Daten reduzieren Confidence. Sie werden nicht geraten.

## Parallel-Kategorien

Ein Account kann mehrere Kategorien gleichzeitig tragen:

- Dormant Veteran / Living History
- Favorite Character Account
- Value C6 / Collector
- Resource Rich / Wish Heavy
- Living Archive
- Manufactured Collector / Stock
- Old Alt / Abandoned Secondary
- Blank Slate / Reroll

`archetype` bleibt als rueckwaertskompatible Hauptkategorie bestehen; `archetypes` enthaelt alle passenden Kategorien.

## Quality Feed

Nach Deployment:

```text
GET /v1/quality/recent?hours=24
```

liefert u. a.:

- Preis-/Server-/Seller-/Availability-Completeness
- Identity-verified / Strict-live Counts
- Plattformvergleich
- Coverage-Familien und Fehler
- die letzten `SCAN_QUALITY_V2` Events
- Feedback-Zusammenfassung

Review Queue:

```text
GET /v1/review-queue?limit=50
```

Recent Candidates:

```text
GET /v1/candidates/recent?hours=24
```

Coverage:

```text
GET /v1/coverage/recent?hours=24
```

## Automatische Improvement Signals

Jeder Scan schreibt ein `SCAN_QUALITY_V2` System-Event. Beispiele:

- `seller_extraction_low`
- `server_extraction_low`
- `price_extraction_low`
- `deep_verification_coverage_low`
- `zero_hit_queries_present`
- `source_errors_present`

Damit kann man Parser-Qualitaet ueber Zeit vergleichen, statt nur subjektiv auf einzelne Treffer zu schauen.

## Feedback Loop

Authentifiziert:

```text
POST /v1/review-feedback
```

Body-Beispiel:

```json
{
  "listing_url": "https://example.com/listing/123",
  "label": "false_positive",
  "reviewer": "manual",
  "notes": "Preis wurde aus related listings gezogen",
  "detector_version": "v2.0"
}
```

Empfohlene Labels:

- `true_positive`
- `false_positive`
- `missed_candidate`
- `bad_parse`
- `good_parse`
- `wrong_price`
- `wrong_server`
- `wrong_seller`
- `security_concern`
- `duplicate`

Auch ein `missed_candidate` darf eine URL haben, die noch nicht in `listings` existiert. So koennen echte Misses gesammelt und spaeter in Regressionstests verwandelt werden.

## Regression-Regel

Jeder relevante Fehler, den wir real beobachten, sollte moeglichst zu einem kleinen reproduzierbaren Test werden. Dadurch wird das System mit jeder Korrektur robuster, statt denselben Fehler spaeter wieder einzufuehren.
