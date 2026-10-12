"""Pure unit tests for NTERM's owner election and room mapping migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

PATH = Path(__file__).resolve().parents[3] / "term_bridge" / "sensor_map" / "mapping.py"
spec = importlib.util.spec_from_file_location("nterm_mapping_helpers", PATH)
assert spec is not None and spec.loader is not None
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def entry(key, *, data, options=None):
    return SimpleNamespace(entry_id=key, data=data, options=options or {})


def test_legacy_mapping_is_preserved_after_version_upgrade():
    old = entry("old", data={"zone": "usb0_ttyusb0_0", "sensor": "sensor.pokoj_6_teplota"})
    assert helpers.mapping_for_entry(old) == {"usb0_ttyusb0_0": "sensor.pokoj_6_teplota"}


def test_manager_wins_same_room_even_when_legacy_is_first():
    legacy = entry("a", data={"zone": "zone_1", "sensor": "sensor.old"})
    manager = entry("b", data={"mappings": {"zone_1": "sensor.new", "zone_2": "sensor.two"}})
    expected = {"zone_1": ("b", "sensor.new"), "zone_2": ("b", "sensor.two")}
    assert helpers.owners([legacy, manager]) == expected
    assert helpers.owners([manager, legacy]) == expected


def test_removing_manager_restores_surviving_legacy_owner():
    legacy = entry("a", data={"zone": "zone_1", "sensor": "sensor.old"})
    manager = entry("b", data={"mappings": {"zone_1": "sensor.new"}})
    assert helpers.owners([legacy, manager])["zone_1"] == ("b", "sensor.new")
    assert helpers.owners([legacy])["zone_1"] == ("a", "sensor.old")


def test_options_replace_manager_mappings_without_discarding_legacy():
    manager = entry("manager", data={"mappings": {"a": "sensor.a"}}, options={
        "mappings": {"b": "sensor.b"}, "pending_removals": ["a"],
    })
    assert helpers.mapping_for_entry(manager) == {"b": "sensor.b"}
