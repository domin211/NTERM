# TERM Bridge — setup and external temperature sensors

TERM Bridge works **without any external sensors**. Install the add-on, configure MQTT and the serial HMPD controllers, and start it. Discovered rooms appear as Home Assistant MQTT climate entities and continue to use their **HMPD temperatures and HMPD setpoints**. You do not need to install the extra integration or configure `external_sensors` for normal use.

## Why are there two components?

The TERM Bridge **add-on** talks to HMPD hardware. The optional **TERM Bridge Sensor Mapping** custom integration provides the Home Assistant room/sensor selection UI. Both are kept in the same [NTERM repository](https://github.com/domin211/NTERM), but Home Assistant add-ons cannot automatically install Core custom integrations. Installing/updating the add-on alone will **not** make Sensor Mapping appear in **Add integration**.

## Install the optional mapping UI

1. Ensure the TERM Bridge add-on is running and that its room climate entities are visible in **Settings → Devices & services → Entities**.
2. In Home Assistant, open **File editor**, **Studio Code Server**, or the Samba share for the main Home Assistant configuration directory (usually `/config`). This is **not** the add-on's own `/config` folder.
3. Download the folder [`custom_components/term_bridge_sensor_map`](https://github.com/domin211/NTERM/tree/feature/external-room-thermostat/custom_components/term_bridge_sensor_map) from this repository's PR branch, including `__init__.py`, `config_flow.py`, `manifest.json` and `strings.json`.
4. Put that folder at **`/config/custom_components/term_bridge_sensor_map/`** (create `custom_components` if missing). Check that the files are directly inside the `term_bridge_sensor_map` folder, not in an extra nested directory.
5. **Restart Home Assistant Core** (restarting only the TERM Bridge add-on is not sufficient).
6. Go to **Settings → Devices & services → Add integration**, search for **TERM Bridge Sensor Mapping**, and select it.
7. Choose the **room climate entity** and the **external temperature sensor**, then submit. The MQTT base topic defaults to `term_bridge`; only change it if your bridge uses a different base topic.
8. Repeat **Add integration → TERM Bridge Sensor Mapping** for additional rooms. To change a sensor later, open the mapping entry's **Configure** options.

There is no separate external sensor dropdown in the TERM Bridge add-on's configuration screen. The room/sensor dropdowns appear only after the custom integration has been installed and Home Assistant Core restarted.

If the integration does not appear, check the folder path, restart Home Assistant Core again, and inspect **Settings → System → Logs** for `term_bridge_sensor_map`. If no rooms appear, wait for TERM Bridge MQTT climate discovery and verify the MQTT integration is enabled. The external sensor must be a Home Assistant sensor entity with the temperature device class.

## What happens with and without a mapping?

| Room state | Temperature shown | Setpoint behavior |
| --- | --- | --- |
| **No external mapping** | Original HMPD temperature | Original HMPD target; unchanged control logic |
| **Mapped, fresh external sensor** | Selected Home Assistant sensor | Virtual target; HMPD set to 32 °C for heat or 16 °C for idle |
| **Mapped, no first reading yet** | Reading unavailable until received | Allow an initial 15-minute sensor grace period |
| **Mapped, sensor stale for 15 minutes** | Last reading may still be shown | Request HMPD idle target (16 °C) without waiting for the usual dwell |

External control has global ±0.5 °C hysteresis and a 10-minute hold between successful heating-state switches (except stale-sensor fallback). **Unmapped rooms do not use this logic.** The HMPD's 16 °C target is not a guaranteed physical valve-off command. Verify one room on the physical controller before enabling many rooms.

## Alternative: manually published MQTT sensor temperatures

Advanced users can configure the add-on's `external_sensors` option directly, without installing the Sensor Mapping integration:

```yaml
external_sensors:
  - zone: usb0_ttyusb0_0
    topic: hotel/room101/temperature
```

Here `usb0_ttyusb0_0` is a zone key from `term_bridge/usb0_ttyusb0_0/state`. The topic must publish a **plain Celsius number** (e.g. `21.5`) whenever the reading changes and periodically (more frequently than every 15 minutes). Do not retain the sensor reading, because a retained historical reading could be mistaken for a new measurement. Leave `external_sensors: []` if you are not using manual mappings.

**Do not map the same room using both methods.** Use the UI mapping integration for Home Assistant temperature sensors.
