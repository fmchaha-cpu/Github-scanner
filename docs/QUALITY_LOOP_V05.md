# Quality Loop v0.5

Nach jedem Scan speichert der Worker einen Quality Snapshot. `/v1/quality/recent` zeigt aktuelle Messwerte und Verbesserungsvorschlaege.

Beobachtet werden u. a.:

- Preis-/Server-/Seller-/Availability-Vollstaendigkeit
- Identity-Verified- und Strict-Live-Quote
- Coverage pro Plattform und Query-Familie
- Fetch-Fehler und Zero-Hit-Queries
- Groesse des historischen Vergleichspools
- Anzahl starker `SOLD_CONFIRMED`-Anker
- probable Duplicate/Relisting Groups
- manuelles Feedback

Die Verbesserungsschleife soll **Messung -> Fehlerklasse -> Parser/Query/Test -> erneute Messung** sein. Nicht einfach mehr URLs scannen.

Empfohlene Feedback-Labels:

```text
false_positive
false_negative
bad_price
bad_server
bad_seller
bad_status
bad_c6_parse
duplicate_confirmed
duplicate_rejected
security_issue
excellent_match
```

Wenn sich ein Fehler wiederholt, sollte daraus ein Regressionstest entstehen, bevor die Heuristik geaendert wird.
