"""Build an isolated offline diagnostic client; never launch or register it.

Usage: python -I tools/prepare_offline_baseline.py game/offline-baseline-2.9.2
The destination must not exist. Original installer and wrapper stay untouched.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_terminator
import install_wrapper
import menu_aspect
import patch_client
import physics_timestep
import prepare_client
from local_station import OFFSET

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--menu-fix", action="store_true", help="include the verified ship-selection aspect fix")
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        parser.error("destination already exists; use a new folder")
    installer = ROOT / "originals/2.9.2/aoa_2.9.2_installer_2.11.1.exe"
    wrapper = ROOT / "originals/wrappers/dgvoodoo2-2.87.5/dgVoodoo2_87_5.zip"
    manifest = json.loads(prepare_client.ASSET_MANIFEST.read_text())
    if prepare_client.sha(installer.read_bytes()) != manifest["installer_sha256"]:
        raise ValueError("installer does not match pinned 2.9.2 manifest")
    if prepare_client.sha(wrapper.read_bytes()) != "5ffde6927f7355ca3fdd5d785b581256a8e6539fa13e395a891ade6ba1040850":
        raise ValueError("wrapper archive does not match pinned release")
    subprocess.run([sys.executable, "-I", str(ROOT / "tools/make_install.py"),
                    str(installer), str(destination)], check=True)
    exe = destination / "AOACLIENT.EXE"
    original = exe.read_bytes()
    stable, _ = patch_client.configure(original)
    baseline = archive_terminator.configure(physics_timestep.configure(stable))
    # Avoid historical-host discovery even when opening the offline login UI.
    baseline = baseline[:OFFSET] + prepare_client.host_field("localhost") + baseline[OFFSET + 12:]
    if args.menu_fix:
        baseline = menu_aspect.configure(baseline)
    state = prepare_client.inspect(baseline)
    expected = {
        "logger-size-v1", "logger-lock-v1", "zero-time-physics-v1", "archive-terminator-v1"}
    if args.menu_fix:
        expected.add(menu_aspect.NAME)
    assert set(state["patches"]) == expected
    (destination / "AOACLIENT.EXE.orig").write_bytes(original)
    exe.write_bytes(baseline)
    subprocess.run([sys.executable, "-I", str(ROOT / "tools/install_wrapper.py"),
                    str(wrapper), str(destination)], check=True)
    config = (destination / "dgVoodoo.conf").read_text(encoding="latin1")
    (destination / "dgVoodoo.reference.conf").write_text(config, encoding="latin1")
    capped = install_wrapper.set_key(config, "[GeneralExt]", "FPSLimit", "60")
    (destination / "dgVoodoo.60fps.conf").write_text(capped, encoding="latin1")
    prepare_client.check_assets(destination)
    prepare_client.wrapper_state(destination)
    assert exe.read_bytes() == baseline
    record = {
        "schema": 1, "purpose": "offline rendering baseline, visual verification pending",
        "source_sha256": prepare_client.sha(original), **state,
        "network": "localhost discovery only; select Play Offline; no host started",
        "active_profile": "reference (uncapped)",
        "files": {p.name: prepare_client.sha(p.read_bytes())
                  for p in sorted(destination.iterdir()) if p.is_file()},
        "visual_results": {"ship_selection": "not tested", "flight": "not tested"},
    }
    (destination / "_offline_baseline.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"destination": str(destination), "patches": state["patches"],
                      "assets": "verified", "visual_verification": "pending manual run"}, indent=2))


if __name__ == "__main__":
    main()
