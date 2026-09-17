# Quality Loop v0.7

v0.7 optimiert nicht nur Trefferzahl, sondern die **Messbarkeit von Fehlerursachen**.

## Pro Scan messen

- Listings/Kandidaten/Strict-Live/Identity Verified
- Feldvollstaendigkeit pro Plattform
- Parser-Ausbeute Detail-Links -> Listing Rows
- HTTP-Status, Browser-Fallback, Challenge-Signale, Laufzeit
- Circuit-Breaker und persistente Source-Cooldowns
- Deep-Verification-Erfolg nach Grund: `candidate`, `calibration_gap`, `control`
- Feld-Provenienz: welcher Extraktionsweg lieferte Preis, Server, Seller usw.
- stale derived flags
- False-Positive/False-Negative Feedback
- Historical comparable pool + Evidenzklassen

## Verbesserungsregel

Eine neue Version soll gegen mindestens drei Ebenen verglichen werden:

1. Unit-/Regressionstests
2. Known-case Recall Benchmark
3. Echter Scan: Version-zu-Version-Metriken + per-platform Diagnose

Erst danach Scoring/Parser behalten oder weiter aendern. Ein groesserer Listing-Count allein ist kein Qualitaetsbeweis.
