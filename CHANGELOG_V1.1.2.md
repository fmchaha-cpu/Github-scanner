# v1.1.2

- Unveränderte Genshin- und Warframe-Listings umgehen jetzt den vollständigen Upsert-Pfad.
- Fast-Scans schreiben für unveränderte Listings nichts; Full-Scans aktualisieren `last_seen` höchstens stündlich.
- Snapshots, Candidate Events und Verification Events werden nur noch bei neuen oder semantisch geänderten Listings angelegt.
- Discovery-Pfade werden zusammengeführt. Zeilenbasierte Lifecycle-Verfolgung wird nur für exakte manuelle Listing-URLs geführt, weil nur diese die automatische Verschwinden-Erkennung speisen.
- Die doppelte Legacy-Coverage-Zeile entfällt; alle internen Auswertungen verwenden bereits `coverage_paths`.
- Batch-Antworten und Collector-Metriken enthalten Zähler für übersprungene Listings, Heartbeats, reine Metadatenupdates und Lifecycle-Schreibvorgänge.
- Der Collector verlangt vor dem Start die Worker-Capability `write_optimized_ingest`. Dadurch kann die alte schreibintensive Worker-Version nicht versehentlich mit dem neuen Collector betrieben werden.
- Keine neue D1-Migration erforderlich.
