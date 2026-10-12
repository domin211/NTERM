"""UI configuration for mapping one NTERM climate entity to a HA sensor."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er, selector

DOMAIN = "term_bridge_sensor_map"


def room_options(hass) -> list[dict[str, str]]:
    registry = er.async_get(hass)
    result = []
    for entry in registry.entities.values():
        if entry.domain != "climate" or not entry.unique_id.startswith("term_bridge_"):
            continue
        if entry.platform != "mqtt":
            continue
        zone = entry.unique_id[len("term_bridge_"):]
        # MQTT climate entities often have no entity name because the device
        # itself carries the room name. Resolve it before falling back to IDs.
        state = hass.states.get(entry.entity_id)
        device = None
        if entry.device_id:
            from homeassistant.helpers import device_registry as dr

            device = dr.async_get(hass).async_get(entry.device_id)
        label = (
            entry.name
            or (device.name_by_user if device else None)
            or (device.name if device else None)
            or (state.attributes.get("friendly_name") if state else None)
            or entry.original_name
        )
        if not label or label.startswith("climate."):
            label = entry.entity_id.removeprefix("climate.").replace("_", " ").title()
        result.append({"value": zone, "label": label})
    return sorted(result, key=lambda x: x["label"])


class TermBridgeSensorMapFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        rooms = room_options(self.hass)
        if not rooms:
            return self.async_abort(reason="no_rooms")
        if user_input is not None:
            await self.async_set_unique_id(user_input["zone"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=next((r["label"] for r in rooms if r["value"] == user_input["zone"]), user_input["zone"]),
                data=user_input,
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("zone"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=rooms, mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("sensor"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
            }),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return TermBridgeSensorMapOptionsFlow(config_entry)


class TermBridgeSensorMapOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("sensor", default=self._entry.options.get("sensor", self._entry.data["sensor"])):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature"))
            }),
        )
