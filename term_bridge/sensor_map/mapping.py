"""Pure helpers for NTERM mapping ownership.

Manager entries take precedence over legacy entries; a room always has one
publisher even while both versions coexist during migration.
"""
from __future__ import annotations


def mapping_for_entry(entry) -> dict[str, str]:
    mappings = entry.options.get("mappings", entry.data.get("mappings"))
    if isinstance(mappings, dict):
        return {z: s for z, s in mappings.items() if isinstance(z, str) and z and isinstance(s, str) and s}
    if isinstance(entry.data.get("zone"), str) and isinstance(entry.data.get("sensor"), str):
        return {entry.data["zone"]: entry.options.get("sensor", entry.data["sensor"])}
    return {}


def owners(entries) -> dict[str, tuple[str, str]]:
    """Return zone -> (entry_id, sensor); managers win over legacy entries."""
    result: dict[str, tuple[str, str]] = {}
    ordered = sorted(
        entries,
        key=lambda e: (0 if "mappings" in e.data or "mappings" in e.options else 1, e.entry_id),
    )
    for entry in ordered:
        for zone, sensor in mapping_for_entry(entry).items():
            result.setdefault(zone, (entry.entry_id, sensor))
    return result
