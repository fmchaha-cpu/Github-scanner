from pathlib import Path


def test_worker_exposes_separate_warframe_api():
    worker = (Path(__file__).parents[2] / "cloudflare" / "src" / "index.ts").read_text(encoding="utf-8")
    assert 'version: "1.1"' in worker
    assert '"multi_game"' in worker
    assert '"warframe_founder"' in worker
    assert '"smart_scan_profiles"' in worker
    assert '"sparse_snapshots"' in worker
    assert '"scan_lifecycle_health"' in worker
    assert 'last_completed_scan: lastCompleted' in worker
    assert 'running_scan_count: Number(runningCount?.n ?? 0)' in worker
    assert 'running_scan_age_seconds: runningScanAgeSeconds' in worker
    assert '/v1/warframe/founder/batch' in worker
    assert '/v1/warframe/founder/alerts' in worker
    assert 'observation_policy' in worker
    assert 'process_disappearance === false' in worker
    assert 'create_quality_snapshot !== false' in worker


def test_disappearance_requires_exact_url_coverage():
    worker = (Path(__file__).parents[2] / "cloudflare" / "src" / "index.ts").read_text(encoding="utf-8")
    assert "query_family='manual_exact_url'" in worker
    assert "page_label='exact'" in worker


def test_new_scan_closes_only_old_interrupted_runs():
    worker = (Path(__file__).parents[2] / "cloudflare" / "src" / "index.ts").read_text(encoding="utf-8")
    assert "status='interrupted'" in worker
    assert "datetime(?, '-10 minutes')" in worker
    assert "automatically closed before a newer scan" in worker


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


def test_two_tier_vps_timers_share_one_lock_and_use_expected_profiles():
    root = Path(__file__).parents[2]
    full_service = (root / "deploy" / "systemd" / "market-scanner.service").read_text(encoding="utf-8")
    fast_service = (root / "deploy" / "systemd" / "market-scanner-fast.service").read_text(encoding="utf-8")
    full_timer = (root / "deploy" / "systemd" / "market-scanner.timer").read_text(encoding="utf-8")
    fast_timer = (root / "deploy" / "systemd" / "market-scanner-fast.timer").read_text(encoding="utf-8")
    assert "/var/lib/genshin-scanner/scan.lock" in full_service
    assert "/var/lib/genshin-scanner/scan.lock" in fast_service
    assert "--profile full" in full_service
    assert "--profile fast" in fast_service
    assert "OnUnitActiveSec=30min" in full_timer
    assert "OnUnitActiveSec=10min" in fast_timer
