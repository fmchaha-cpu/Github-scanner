#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bitte als root ausführen: sudo bash scripts/install_vps_ps5.sh" >&2
  exit 1
fi

repo_dir=/opt/Github-scanner
unit_dir=/etc/systemd/system
service_user=market-scanner
state_dir=/var/lib/genshin-scanner

if [[ ! -f "$repo_dir/collector/ps5_sources.yaml" ]]; then
  echo "PS5-Konfiguration fehlt unter $repo_dir/collector/ps5_sources.yaml" >&2
  exit 1
fi
if ! id "$service_user" >/dev/null 2>&1; then
  echo "Service-Benutzer $service_user fehlt. Erst das normale VPS-Setup ausführen." >&2
  exit 1
fi
if systemctl is-active --quiet ps5-deal-scanner.service; then
  echo "PS5-Scan läuft noch. Erst beenden lassen und erneut ausführen." >&2
  exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  apt-get update
  apt-get install -y sqlite3
fi

install -d -o "$service_user" -g "$service_user" -m 0750 "$state_dir"
systemctl stop ps5-deal-scanner.timer 2>/dev/null || true
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/ps5-deal-scanner.service" "$unit_dir/ps5-deal-scanner.service"
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/ps5-deal-scanner.timer" "$unit_dir/ps5-deal-scanner.timer"
systemctl daemon-reload
systemctl enable ps5-deal-scanner.timer

echo "PS5-Angebotswächter installiert, aber noch nicht gestartet."
echo "Optional DISCORD_WEBHOOK_PS5 in /etc/genshin-scanner.env setzen."
echo "Test: systemctl start ps5-deal-scanner.service"
echo "Logs: journalctl -u ps5-deal-scanner.service -n 100 --no-pager -l"
echo "Timer: systemctl start ps5-deal-scanner.timer"
