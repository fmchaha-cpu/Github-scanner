# v1.1.1

- Warframe-Preise im PlayerUp-Format `Price $: 2000` oder `Price EUR: 450` werden jetzt erkannt.
- Reiner Zahlentext ohne Währung bleibt weiterhin absichtlich ohne Preis, um MR-, Stunden- und Platinangaben nicht als Kaufpreis zu speichern.
- Der häufige Marktplatz-Tippfehler `Interwined Fate` wird als Intertwined Fate erkannt; Ressourcenangebote werden dadurch nicht mehr systematisch zu niedrig bewertet.
- Abgekürzte Ressourcenangaben wie `56K+ Primogems` werden korrekt in Primogems und Limited Pulls umgerechnet.
- Angaben mit vorangestelltem Label wie `Intertwined Fate：60-70` werden erkannt; bei Bereichen wird konservativ der angebotene Höchstwert gespeichert.
- Dynamische Markt- und Kategorieseiten dürfen Listings nicht mehr allein wegen dreier fehlender Sichtungen als `EXPIRED_REMOVED` markieren. Automatische Verschwinden-Erkennung akzeptiert dafür nur noch erfolgreich geprüfte exakte Listing-URLs.
- `/health` zeigt nun zusätzlich den letzten abgeschlossenen Scan und das Alter eines offenen Scans. Abgebrochene Collector-Läufe verdecken damit nicht mehr das letzte vollständige Ergebnis.
- Beim Start eines neuen Scans werden mindestens zehn Minuten alte, nicht abgeschlossene Scan-Datensätze als `interrupted` beendet. Dadurch sammeln sich nach Abbrüchen keine dauerhaft laufenden Statuszeilen an.
