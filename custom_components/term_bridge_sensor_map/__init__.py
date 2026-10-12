"""Forward a selected HA temperature sensor to TERM Bridge over MQTT."""
from __future__ import annotations

import logging
import math
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

DOMAIN = "term_bridge_sensor_map"
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    zone = entry.data["zone"]
    sensor = entry.options.get("sensor", entry.data["sensor"])
    base_topic = "term_bridge"
    mapping_topic = f"{base_topic}/external_map/{zone}"
    value_topic = f"{base_topic}/external/{zone}"
    active = object()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = active

    async def publish_value() -> None:
        if hass.data.get(DOMAIN, {}).get(entry.entry_id) is not active:
            return
        state = hass.states.get(sensor)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        try:
            val = float(state.state)
            unit = state.attributes.get("unit_of_measurement")
            if unit == UnitOfTemperature.FAHRENHEIT:
                val = (val - 32) * 5 / 9
            elif unit == UnitOfTemperature.KELVIN:
                val -= 273.15
            if not math.isfinite(val) or not 0 <= val <= 50:
                return
        except (TypeError, ValueError):
            return
        if hass.data.get(DOMAIN, {}).get(entry.entry_id) is active:
            await mqtt.async_publish(hass, value_topic, f"{val:.2f}", qos=1, retain=False)

    @callback
    def on_change(event) -> None:
        hass.async_create_task(publish_value())

    @callback
    def on_interval(now) -> None:
        hass.async_create_task(publish_value())

    if hass.data.get(DOMAIN, {}).get(entry.entry_id) is active:
        await mqtt.async_publish(hass, mapping_topic, sensor, qos=1, retain=True)
    remove_state = async_track_state_change_event(hass, [sensor], on_change)
    remove_interval = async_track_time_interval(hass, on_interval, timedelta(minutes=2))
    entry.async_on_unload(remove_state)
    entry.async_on_unload(remove_interval)
    entry.async_on_unload(entry.add_update_listener(async_update_listener))
    await publish_value()
    return True


async def async_update_listener(hass: HomeAssistant, entry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    entry.async_unload_callbacks()
    # Retained mapping survives a reload or temporary integration outage.
    return True
