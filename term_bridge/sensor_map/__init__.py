"""NTERM temperature forwarding and durable MQTT reconciliation."""
from __future__ import annotations

import logging
import math
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store

from .mapping import mapping_for_entry, owners

DOMAIN = "term_bridge_sensor_map"
BASE_TOPIC = "term_bridge"
_LOGGER = logging.getLogger(__name__)
STORAGE_KEY = "nterm_sensor_mapping_pending_clears"


def celsius(state) -> float | None:
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    try:
        value = float(state.state)
        unit = state.attributes.get("unit_of_measurement")
        if unit == UnitOfTemperature.FAHRENHEIT:
            value = (value - 32) * 5 / 9
        elif unit == UnitOfTemperature.KELVIN:
            value -= 273.15
        return value if math.isfinite(value) and 0 <= value <= 50 else None
    except (ValueError, TypeError):
        return None


def active_owners(hass: HomeAssistant, *, exclude: str | None = None):
    entries = [entry for entry in hass.config_entries.async_entries(DOMAIN)
               if entry.entry_id != exclude]
    return owners(entries)


async def _persist(hass: HomeAssistant) -> None:
    state = hass.data[DOMAIN]
    await state["store"].async_save({"pending": sorted(state["pending"])})


async def request_clear(hass: HomeAssistant, zones: set[str]) -> None:
    """Record tombstones BEFORE making a best-effort MQTT clear."""
    if not zones:
        return
    state = hass.data[DOMAIN]
    async with state["lock"]:
        state["pending"].update(zones)
        await _persist(hass)


async def reconcile(hass: HomeAssistant, *, exclude: str | None = None) -> None:
    """Republish all authoritative mappings and retry pending clears.

    Periodic reconciliation also repairs MQTT reconnects and incomplete startup
    publishes. Tombstones survive add-on/HA/broker restarts until acknowledged.
    """
    state = hass.data[DOMAIN]
    async with state["lock"]:
        current = active_owners(hass, exclude=exclude)
        for zone, (_, sensor) in current.items():
            try:
                await mqtt.async_publish(hass, f"{BASE_TOPIC}/external_map/{zone}", sensor, qos=1, retain=True)
            except Exception:
                _LOGGER.warning("Could not publish mapping for %s; retrying", zone, exc_info=True)
        for zone in tuple(state["pending"]):
            # Another entry might still own this room; never clear it.
            if zone in current:
                state["pending"].discard(zone)
                continue
            try:
                await mqtt.async_publish(hass, f"{BASE_TOPIC}/external_map/{zone}", "", qos=1, retain=True)
            except Exception:
                _LOGGER.warning("Could not clear retained mapping %s; retrying", zone, exc_info=True)
            else:
                state["pending"].discard(zone)
        await _persist(hass)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    import asyncio

    store = Store(hass, 1, STORAGE_KEY)
    previous = await store.async_load() or {}
    state = hass.data.setdefault(DOMAIN, {})
    state.update({
        "store": store,
        "lock": asyncio.Lock(),
        "pending": set(previous.get("pending", [])),
        "entries": {},
    })

    @callback
    def on_interval(now) -> None:
        hass.async_create_task(reconcile(hass))

    state["cancel_retry"] = async_track_time_interval(hass, on_interval, timedelta(minutes=1))
    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    if DOMAIN not in hass.data or "store" not in hass.data[DOMAIN]:
        await async_setup(hass, {})
    mappings = mapping_for_entry(entry)
    token = object()
    hass.data[DOMAIN]["entries"][entry.entry_id] = {"token": token, "mappings": mappings}
    await request_clear(hass, set(entry.options.get("pending_removals", [])))

    async def publish(zone: str, sensor: str) -> None:
        active = hass.data[DOMAIN]["entries"].get(entry.entry_id)
        if not active or active["token"] is not token:
            return
        if active_owners(hass).get(zone) != (entry.entry_id, sensor):
            return
        value = celsius(hass.states.get(sensor))
        if value is None:
            _LOGGER.warning("Invalid or unavailable NTERM external sensor %s for %s", sensor, zone)
            return
        try:
            await mqtt.async_publish(hass, f"{BASE_TOPIC}/external/{zone}", f"{value:.2f}", qos=1, retain=False)
        except Exception:
            _LOGGER.warning("NTERM temperature publish failed for %s; retrying", zone, exc_info=True)

    async def publish_all() -> None:
        for zone, sensor in mappings.items():
            await publish(zone, sensor)

    @callback
    def on_change(event) -> None:
        for zone, sensor in mappings.items():
            if event.data["entity_id"] == sensor:
                hass.async_create_task(publish(zone, sensor))

    @callback
    def on_interval(now) -> None:
        hass.async_create_task(publish_all())

    if mappings:
        entry.async_on_unload(async_track_state_change_event(hass, list(set(mappings.values())), on_change))
    entry.async_on_unload(async_track_time_interval(hass, on_interval, timedelta(minutes=2)))
    entry.async_on_unload(entry.add_update_listener(async_update_listener))
    await reconcile(hass)
    await publish_all()
    return True


async def async_update_listener(hass: HomeAssistant, entry) -> None:
    old = hass.data[DOMAIN]["entries"].get(entry.entry_id, {}).get("mappings", {})
    new = mapping_for_entry(entry)
    # Save removals even if publishing fails or Home Assistant stops mid-reload.
    try:
        await request_clear(hass, set(old) - set(new))
    finally:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    hass.data.get(DOMAIN, {}).get("entries", {}).pop(entry.entry_id, None)
    entry.async_unload_callbacks()
    return True


async def async_remove_entry(hass: HomeAssistant, entry) -> None:
    # Delete is distinct from reload: only a permanent deletion tombstones zones.
    await request_clear(hass, set(mapping_for_entry(entry)))
    await reconcile(hass, exclude=entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry) -> bool:
    """Migrate version-1 individual room entries without changing their mapping."""
    if entry.version == 1:
        _LOGGER.info("Migrating NTERM room mapping %s to v2", entry.entry_id)
        hass.config_entries.async_update_entry(entry, version=2)
        return True
    return entry.version == 2
