# Upgrade auf v0.10.0

1. Inhalt des kumulativen ZIPs ueber den bestehenden `Github-scanner`-Ordner kopieren. `.git` nicht loeschen.
2. In GitHub Desktop committen und pushen.
3. **Kein Cloudflare-Deploy noetig.** v0.10 nutzt bewusst weiterhin Worker API v0.9.
4. Einen neuen `Genshin market scan` starten.

Empfohlener Commit:

`Upgrade market tracker to v0.10.0`

Der erste v0.10-Lauf sollte besonders auf `identity_diagnostics`, `price_plausibility_flagged`, `detail_blocked`, `merit_unconfirmed`, `candidate_comparable_any_coverage_pct` und `candidate_comparable_usable_coverage_pct` geprueft werden.
