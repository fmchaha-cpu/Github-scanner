from pathlib import Path


def test_worker_exposes_separate_warframe_api():
    worker = (Path(__file__).parents[2] / "cloudflare" / "src" / "index.ts").read_text(encoding="utf-8")
    assert 'version: "1.0"' in worker
    assert '"multi_game"' in worker
    assert '"warframe_founder"' in worker
    assert '/v1/warframe/founder/batch' in worker
    assert '/v1/warframe/founder/alerts' in worker


def test_github_scan_is_manual_fallback_only():
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "scan.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow


def test_vps_service_reuses_existing_secret_file_and_state_directory():
    root = Path(__file__).parents[2]
    service = (root / "deploy" / "systemd" / "market-scanner.service").read_text(encoding="utf-8")
    installer = (root / "scripts" / "install_vps_v1.sh").read_text(encoding="utf-8")
    assert "EnvironmentFile=/etc/genshin-scanner.env" in service
    assert "/var/lib/genshin-scanner" in service
    assert "env_file=/etc/genshin-scanner.env" in installer
    assert "/etc/market-scanner" not in service + installer
