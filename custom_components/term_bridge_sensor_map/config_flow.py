"""NTERM external temperature sensor mapping manager."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er, device_registry as dr, selector

DOMAIN = "term_bridge_sensor_map"
MANAGER_ID = "nterm_sensor_manager"


def room_options(hass) -> list[dict[str, str]]:
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    result = []
    for entry in registry.entities.values():
        if entry.domain != "climate" or entry.platform != "mqtt" or not entry.unique_id.startswith("term_bridge_"):
            continue
        zone = entry.unique_id.removeprefix("term_bridge_")
        device = devices.async_get(entry.device_id) if entry.device_id else None
        state = hass.states.get(entry.entity_id)
        label = (entry.name or (device.name_by_user or device.name if device else None)
                 or (state.attributes.get("friendly_name") if state else None)
                 or entry.original_name or entry.entity_id.removeprefix("climate.").replace("_", " ").title())
        result.append({"value": zone, "label": label})
    return sorted(result, key=lambda r: r["label"].casefold())


def sensor_field():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature"))


class NtermSensorMapFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        rooms = room_options(self.hass)
        if not rooms:
            return self.async_abort(reason="no_rooms")
        await self.async_set_unique_id(MANAGER_ID)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="NTERM Sensor Manager", data={"mappings": {user_input["zone"]: user_input["sensor"]}})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("zone"): selector.SelectSelector(selector.SelectSelectorConfig(
                options=rooms, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required("sensor"): sensor_field(),
        }))

    @staticmethod
    def async_get_options_flow(config_entry):
        return NtermSensorMapOptionsFlow(config_entry)


class NtermSensorMapOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._entry = config_entry

    def _mappings(self):
        return dict(self._entry.options.get("mappings", self._entry.data.get("mappings", {})))

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["add", "remove"])

    async def async_step_add(self, user_input=None):
        rooms = room_options(self.hass)
        if not rooms:
            return self.async_abort(reason="no_rooms")
        if user_input is not None:
            mappings = self._mappings()
            mappings[user_input["zone"]] = user_input["sensor"]
            return self.async_create_entry(title="", data={"mappings": mappings})
        return self.async_show_form(step_id="add", data_schema=vol.Schema({
            vol.Required("zone"): selector.SelectSelector(selector.SelectSelectorConfig(
                options=rooms, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required("sensor"): sensor_field(),
        }))

    async def async_step_remove(self, user_input=None):
        mappings = self._mappings()
        if not mappings:
            return self.async_abort(reason="no_mappings")
        if user_input is not None:
            mappings.pop(user_input["zone"], None)
            return self.async_create_entry(title="", data={"mappings": mappings})
        labels = {r["value"]: r["label"] for r in room_options(self.hass)}
        return self.async_show_form(step_id="remove", data_schema=vol.Schema({
            vol.Required("zone"): selector.SelectSelector(selector.SelectSelectorConfig(
                options=[{"value": z, "label": labels.get(z, z)} for z in mappings],
                mode=selector.SelectSelectorMode.DROPDOWN))
        }))
