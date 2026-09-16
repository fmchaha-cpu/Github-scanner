# Architektur

```text
Public marketplace pages
  PlayerAuctions / ZeusX / EpicNPC / PlayerUp / later Eldorado & G2G
                   |
                   v
        GitHub Actions collector
         every 30 minutes
   HTTP first -> Playwright fallback
                   |
                   v
         Cloudflare Worker API
        authenticated writes only
                   |
                   v
             Cloudflare D1
 listings + snapshots + coverage + scan health
                   |
        +----------+----------+
        |                     |
        v                     v
/public candidate feed    daily analysis/export
        |                     |
        v                     v
ChatGPT deep verification   Excel tracker
+ personal fit + risk       once per day
```

## Warum diese Trennung?

1. **Collector = Recall.** Er soll moeglichst viele oeffentlich sichtbare Angebote erkennen, nicht perfekt bewerten.
2. **D1 = Wahrheit/Historie.** Ein Excel-Fehler verliert keine Marktbeobachtungen.
3. **Detector = Triage.** Auffaellige Accounts werden priorisiert, aber niemals automatisch als Kaufempfehlung bezeichnet.
4. **ChatGPT = Precision.** Produktseite, Identitaet, LIVE-Status, Risiko, Marktwert und persoenlicher Fit werden erst hier tief geprueft.
5. **Excel = Analysebericht.** Nicht die Rohdatenbank.

## Sicherheitsprinzip

Der Collector darf nur oeffentlich zugaengliche Seiten lesen. Keine Logins, CAPTCHA-Umgehung, Proxy-Rotation, Rate-Limit-Umgehung oder andere Anti-Bot-Bypasses. Wenn eine Quelle den automatisierten Zugriff nicht sinnvoll zulaesst, wird sie als `partial/blocked` markiert und weiterhin durch ChatGPT/Websuche oder manuelle URL-Zufuhr abgedeckt.
