"""NTERM room-to-temperature-sensor MQTT bridge.

One manager entry holds multiple mappings. Existing individual entries remain
supported to avoid breaking installed mappings during transition.
"""
from __future__ import annotations

import logging
import math
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

DOMAIN = "term_bridge_sensor_map"
BASE_TOPIC = "term_bridge"
_LOGGER = logging.getLogger(__name__)


def mapping_for_entry(entry) -> dict[str, str]:
    mappings = entry.options.get("mappings", entry.data.get("mappings"))
    if isinstance(mappings, dict):
        return {k: v for k, v in mappings.items() if isinstance(k, str) and isinstance(v, str)}
    # Backward compatibility with pre-0.8 entries.
    if "zone" in entry.data and "sensor" in entry.data:
        return {entry.data["zone"]: entry.options.get("sensor", entry.data["sensor"])}
    return {}


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
        if math.isfinite(value) and 0 <= value <= 50:
            return value
    except (ValueError, TypeError):
        pass
    return None


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    mappings = mapping_for_entry(entry)
    token = object()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"token": token, "mappings": mappings}

    async def publish(zone: str, sensor: str) -> None:
        if hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("token") is not token:
            return
        reading = celsius(hass.states.get(sensor))
        if reading is None:
            _LOGGER.warning("NTERM external sensor %s for zone %s unavailable or invalid", sensor, zone)
            return
        # The bridge subscribes to this topic and republishes the climate state.
        if hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("token") is token:
            await mqtt.async_publish(hass, f"{BASE_TOPIC}/external/{zone}", f"{reading:.2f}", qos=1, retain=False)

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

    remove_state = async_track_state_change_event(hass, list(set(mappings.values())), on_change) if mappings else None
    remove_interval = async_track_time_interval(hass, on_interval, timedelta(minutes=2))
    if remove_state is not None:
        entry.async_on_unload(remove_state)
    entry.async_on_unload(remove_interval)
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    for zone, sensor in mappings.items():
        await mqtt.async_publish(hass, f"{BASE_TOPIC}/external_map/{zone}", sensor, qos=1, retain=True)
    await publish_all()
    _LOGGER.info("NTERM manager activated %d external room sensor mapping(s)", len(mappings))
    return True


async def async_update_listener(hass: HomeAssistant, entry) -> None:
    current = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("mappings", {})
    updated = mapping_for_entry(entry)
    # An explicit Remove action must delete its retained mapping.
    for zone in set(current) - set(updated):
        await mqtt.async_publish(hass, f"{BASE_TOPIC}/external_map/{zone}", "", qos=1, retain=True)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    entry.async_unload_callbacks()
    # No empty retained mapping on routine reload: a restart must not disable safety fallback.
    return True


async def async_remove_entry(hass: HomeAssistant, entry) -> None:
    """Clear MQTT mapping only when an entry is permanently deleted."""
    for zone in mapping_for_entry(entry):
        await mqtt.async_publish(hass, f"{BASE_TOPIC}/external_map/{zone}", "", qos=1, retain=True)
    _LOGGER.info("NTERM removed %d retained mappings", len(mapping_for_entry(entry)))
