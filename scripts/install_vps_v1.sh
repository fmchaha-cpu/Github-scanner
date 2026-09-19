#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bitte als root ausführen: sudo bash scripts/install_vps_v1.sh" >&2
  exit 1
fi

repo_dir=/opt/Github-scanner
service_user=market-scanner
env_file=/etc/genshin-scanner.env
state_dir=/var/lib/genshin-scanner
browser_dir=/opt/ms-playwright

if [[ ! -f "$repo_dir/collector/requirements.txt" ]]; then
  echo "Repository fehlt unter $repo_dir. Erst dort klonen oder aktualisieren." >&2
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip git util-linux

if ! id "$service_user" >/dev/null 2>&1; then
  useradd --system --home-dir "$state_dir" --create-home --shell /usr/sbin/nologin "$service_user"
fi
install -d -o "$service_user" -g "$service_user" -m 0750 "$state_dir" "$browser_dir"

python3 -m venv "$repo_dir/.venv"
"$repo_dir/.venv/bin/pip" install --upgrade pip
"$repo_dir/.venv/bin/pip" install -r "$repo_dir/collector/requirements.txt"
PLAYWRIGHT_BROWSERS_PATH="$browser_dir" "$repo_dir/.venv/bin/python" -m playwright install-deps chromium
runuser -u "$service_user" -- env PLAYWRIGHT_BROWSERS_PATH="$browser_dir" "$repo_dir/.venv/bin/python" -m playwright install chromium

if [[ ! -f "$env_file" ]]; then
  install -o root -g root -m 0600 "$repo_dir/.env.example" "$env_file"
fi
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/market-scanner.service" /etc/systemd/system/market-scanner.service
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/market-scanner.timer" /etc/systemd/system/market-scanner.timer
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/market-scanner-fast.service" /etc/systemd/system/market-scanner-fast.service
install -o root -g root -m 0644 "$repo_dir/deploy/systemd/market-scanner-fast.timer" /etc/systemd/system/market-scanner-fast.timer
systemctl daemon-reload
systemctl enable market-scanner.timer market-scanner-fast.timer

echo "Installiert, aber noch nicht gestartet."
echo "1) $env_file prüfen"
echo "2) systemctl start market-scanner.service"
echo "3) journalctl -u market-scanner.service -n 100 --no-pager"
echo "4) systemctl start market-scanner.timer market-scanner-fast.timer"
