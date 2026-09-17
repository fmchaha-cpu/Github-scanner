# Quality Loop v0.8

v0.8 trennt drei Ebenen, die in frueheren Logs leicht verwechselt werden konnten:

1. **Current-scan evidence**: Was der laufende Marketplace-Scan direkt gesehen hat.
2. **Persistent historical repertoire**: D1-Historie inkl. importierter Tracker-Seeds und beobachteter Statuswechsel.
3. **Candidate comparables**: Wie gut die aktuellen Kandidaten durch aehnliche historische Daten gestuetzt werden.

## Neue Diagnosefelder

- `worker_api.expected_version`
- `worker_api.reported_version`
- `worker_api.compatible`
- `historical_pool.total`
- `historical_pool.tracker_seed_records`
- `historical_pool.sold_confirmed`
- `candidate_comparables[]`
- `candidate_comparable_coverage_pct`

## Interpretation

`historical_anchor_observations=0` bedeutet weiterhin nur: Der **aktuelle Live-Scan** hat keine bereits sold/closed markierten Angebote direkt beobachtet. Fuer die Groesse des Repertoires ist `historical_pool.total` massgeblich.

Candidate-comparable-Werte werden in v0.8 nur gesammelt. Erst nach mehreren Scans und Backtests sollte entschieden werden, ob sie in AVP/Interest/Alert-Logik einfliessen.
