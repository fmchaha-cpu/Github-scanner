# Discord einrichten

1. In Discord den Zielkanal öffnen: **Kanal bearbeiten → Integrationen → Webhooks → Neuer Webhook**.
2. Zwei Webhooks sind ideal: einen Kanal für Genshin, einen für Warframe.
3. URLs ausschließlich auf dem Server in der bestehenden Datei `/etc/genshin-scanner.env` eintragen:

```dotenv
DISCORD_WEBHOOK_GENSHIN=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_WARFRAME=https://discord.com/api/webhooks/...
```

4. Testlauf starten:

```bash
sudo systemctl start market-scanner.service
sudo journalctl -u market-scanner.service -n 100 --no-pager
```

Die Anwendung sendet mit `allowed_mentions: {parse: []}`. Inhalte eines Angebots können dadurch keine Benutzer oder Rollen anpingen. Webhook-URLs nie in Screenshots, Commits oder Chatnachrichten veröffentlichen. Bei Verdacht auf Offenlegung den Webhook in Discord löschen und neu erzeugen.
