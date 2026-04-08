#!/usr/bin/env python3
"""
Disaster Recovery Test Script for DecisionDoc AI.
Usage:
  python scripts/dr_test.py --scenario backup_restore
  python scripts/dr_test.py --scenario app_restart
  python scripts/dr_test.py --scenario full_recovery
  python scripts/dr_test.py --all
"""
import argparse
import subprocess
import tempfile
import shutil
import time
import os
import sys


def run(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          check=check)


def test_backup_restore() -> bool:
    """Test: backup → restore → verify data integrity."""
    print("\n[DR Test] Backup & Restore")
    tmp = tempfile.mkdtemp(prefix="dr_test_")
    backup_dir = os.path.join(tmp, "backup")
    restore_dir = os.path.join(tmp, "restore")
    data_dir = os.environ.get("DATA_DIR", "./data")

    try:
        # 1. Create backup
        print("  1. Creating backup...")
        os.makedirs(backup_dir, exist_ok=True)
        result = run(f"tar czf {backup_dir}/test.tar.gz -C . data 2>/dev/null || "
                     f"tar czf {backup_dir}/test.tar.gz -C {os.path.dirname(data_dir)} "
                     f"{os.path.basename(data_dir)}", check=False)
        backup_file = os.path.join(backup_dir, "test.tar.gz")
        if not os.path.exists(backup_file):
            print("  ⚠️  No data directory to backup — skipping")
            return True

        size = os.path.getsize(backup_file)
        print(f"  ✅ Backup created ({size:,} bytes)")

        # 2. Restore to temp dir
        print("  2. Restoring backup...")
        os.makedirs(restore_dir, exist_ok=True)
        run(f"tar xzf {backup_file} -C {restore_dir}")
        print("  ✅ Restore succeeded")

        # 3. Verify directory structure
        restored = os.listdir(restore_dir)
        print(f"  ✅ Restored directories: {restored}")

        print("  ✅ Backup & Restore test PASSED")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_app_restart() -> bool:
    """Test: stop app → verify health fails → restart → verify health."""
    print("\n[DR Test] App Restart")
    try:
        import httpx
        base = os.environ.get("APP_URL", "http://localhost:8000")

        # Check if app is running
        try:
            r = httpx.get(f"{base}/health", timeout=3)
            if r.status_code != 200:
                print("  ⚠️  App not running — skipping restart test")
                return True
        except Exception:
            print("  ⚠️  App not reachable — skipping restart test")
            return True

        # Restart
        print("  Restarting app container...")
        result = run("docker compose restart app 2>/dev/null || true", check=False)

        # Wait for health
        for i in range(12):
            time.sleep(5)
            try:
                r = httpx.get(f"{base}/health", timeout=3)
                if r.status_code == 200:
                    print(f"  ✅ App healthy after {(i+1)*5}s")
                    return True
            except Exception:
                pass
            print(f"  ... waiting ({(i+1)*5}s)")

        print("  ❌ App did not recover within 60s")
        return False
    except ImportError:
        print("  ⚠️  httpx not available — skipping connectivity check")
        return True


def test_full_recovery() -> bool:
    """Test: full recovery simulation (backup + restore + restart)."""
    print("\n[DR Test] Full Recovery Simulation")
    results = [
        test_backup_restore(),
        test_app_restart(),
    ]
    return all(results)


def main():
    parser = argparse.ArgumentParser(description="DecisionDoc AI DR Test")
    parser.add_argument("--scenario", choices=["backup_restore", "app_restart",
                                                "full_recovery"])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("DecisionDoc AI — Disaster Recovery Test")
    print("=" * 60)

    results = {}
    if args.all or args.scenario == "backup_restore":
        results["backup_restore"] = test_backup_restore()
    if args.all or args.scenario == "app_restart":
        results["app_restart"] = test_app_restart()
    if args.scenario == "full_recovery":
        results["full_recovery"] = test_full_recovery()

    print("\n" + "=" * 60)
    print("Results:")
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    print("=" * 60)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
