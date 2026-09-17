# Historical Comparable Engine v0.5

## Evidenzgewicht

Basisgewichte:

- `SOLD_CONFIRMED`: 1.00
- `SOLD_CLAIMED`: 0.65
- `EXPIRED_REMOVED`: 0.25
- `OUTCOME_UNKNOWN`: 0.15
- `RISK_CONTAMINATED`: 0.05

Danach wird mit **Similarity²** und **Recency Weight** multipliziert. Risk-Hits reduzieren historische Evidenz zusaetzlich stark.

## Warum kein normaler Durchschnitt?

Ein einfacher Durchschnitt waere empfindlich gegen Fantasiepreise, alte Marktphasen, unpassende Accounts und Relistings. v0.5 verwendet deshalb einen gewichteten Median und eine gewichtete mediane absolute Abweichung (MAD).

## Vergleichsmerkmale

- Server
- identische Waehrung
- AR-Naehe
- Anzahl Limited C6 / C6R1
- konkrete C6-/C6R1-Charaktere
- allgemeine Character-Signatur
- Limited Pull Reserve
- History Richness
- Discovery Headroom
- Resource Richness
- Legacy Collector Value
- Archetypen

## Duplikate / Relistings

Der Fingerprint ist absichtlich nur ein Vorschlag. Mehrere URLs mit demselben Fingerprint werden im historischen Preisvoting auf **eine Stimme** reduziert, aber die Listings werden nicht in der Datenbank zusammengefuehrt. Dadurch verlieren offensichtliche Relistings die Moeglichkeit, einen Median kuenstlich mehrfach zu beeinflussen.

## Status `SOLD_CONFIRMED`

Der Name bedeutet: Die exakte oeffentliche Listing-Seite wurde identity-bound geprueft und zeigt verkauft/geschlossen. Er bedeutet **nicht**, dass der oeffentlich angezeigte Preis nachweislich der tatsaechliche Settlement-Preis war.
