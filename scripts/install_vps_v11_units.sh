#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bitte als root ausführen: sudo bash scripts/install_vps_v11_units.sh" >&2
  exit 1
fi

repo_dir=/opt/Github-scanner
unit_dir=/etc/systemd/system

for service in market-scanner.service market-scanner-fast.service; do
  if systemctl is-active --quiet "$service"; then
    echo "$service läuft noch. Erst den Scan beenden lassen und erneut ausführen." >&2
    exit 1
  fi
done

systemctl stop market-scanner.timer market-scanner-fast.timer 2>/dev/null || true
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/market-scanner.service" "$unit_dir/market-scanner.service"
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/market-scanner.timer" "$unit_dir/market-scanner.timer"
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/market-scanner-fast.service" "$unit_dir/market-scanner-fast.service"
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/market-scanner-fast.timer" "$unit_dir/market-scanner-fast.timer"
systemctl daemon-reload
systemctl enable --now market-scanner.timer market-scanner-fast.timer

echo "v1.1-Timer aktiviert: fast ~10 Minuten, full ~30 Minuten."
