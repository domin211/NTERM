"""Install NTERM's optional Home Assistant sensor mapping integration.

The bridge does not depend on this integration. Installation failures are logged
and must never prevent ordinary HMPD thermostats from starting.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger("nterm.install")
SOURCE = Path("/opt/nterm-sensor-map")
DESTINATION = Path("/homeassistant/custom_components/term_bridge_sensor_map")
FILES = ("__init__.py", "config_flow.py", "mapping.py", "manifest.json", "strings.json", "translations/en.json")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(source: Path = SOURCE, destination: Path = DESTINATION) -> bool:
    """Install/update the bundled custom integration, preserving unrelated files."""
    if not source.is_dir():
        print("NTERM: bundled sensor mapping not found; continuing without it", flush=True)
        return False

    try:
        missing = [name for name in FILES if not (source / name).is_file()]
        if missing:
            print(f"NTERM: incomplete sensor mapping bundle: missing {missing}", flush=True)
            return False
        manifest = destination / "manifest.json"
        if manifest.exists():
            installed = json.loads(manifest.read_text(encoding="utf-8"))
            if installed.get("domain") != "term_bridge_sensor_map":
                print("NTERM: conflicting custom integration; refusing to overwrite it", flush=True)
                return False

        destination.mkdir(parents=True, exist_ok=True)
        changed = False
        for filename in FILES:
            src = source / filename
            dst = destination / filename
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and _digest(dst) == _digest(src):
                continue
            staged = destination / (filename + ".nterm-tmp")
            try:
                shutil.copyfile(src, staged)
                os.replace(staged, dst)
            finally:
                staged.unlink(missing_ok=True)
            changed = True
        if changed:
            print(
                "NTERM: sensor mapping integration installed/updated. "
                "Restart Home Assistant Core to load the new files; "
                "then go to Settings > Devices & services > Add integration > NTERM Sensor Mapping.",
                flush=True,
            )
        else:
            print("NTERM: sensor mapping integration is already up to date", flush=True)
        return True
    except (OSError, ValueError, TypeError) as exc:
        print(f"NTERM: could not install sensor mapping: {exc}", flush=True)
        return False


if __name__ == "__main__":
    install()
