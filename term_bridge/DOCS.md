# TERM Bridge — setup and external temperature sensors

TERM Bridge works **without any external sensors**. Install the add-on, configure MQTT and the serial HMPD controllers, and start it. Discovered rooms appear as Home Assistant MQTT climate entities and continue to use their **HMPD temperatures and HMPD setpoints**. You do not need to install the extra integration or configure `external_sensors` for normal use.

## One-add-on installation

**Only install the NTERM add-on.** Version 0.7 bundles and installs its companion **NTERM Sensor Mapping** Home Assistant custom integration automatically under `/config/custom_components/term_bridge_sensor_map/` (the add-on sees Home Assistant's main config at `/homeassistant`). A writable Home Assistant configuration mount is required for this feature.

1. Update/install the **NTERM** add-on (version **0.7**) and start it.
2. Check the add-on log for `NTERM: sensor mapping integration installed/updated` or `already up to date`.
3. **Restart Home Assistant Core once** after the first installation or any integration code update. Restarting only the add-on will not load the integration in Home Assistant.
4. Go to **Settings → Devices & services → Add integration → NTERM Sensor Mapping**.
5. Select an NTERM thermostat room and a Home Assistant temperature sensor. The MQTT base topic defaults to `term_bridge`; only change it if your bridge uses another prefix.
6. Repeat **Add integration** for every other room that needs an external sensor. Existing mappings can be reconfigured through **Configure**.

If the integration does not appear, inspect the add-on logs for a copy or permission error, confirm `/config/custom_components/term_bridge_sensor_map/` exists in the **main Home Assistant config**, and restart Home Assistant Core. NTERM does **not** restart Home Assistant automatically. The integration is optional; failures do not stop ordinary HMPD thermostat control.

**Privacy and upgrade note:** Auto-installation requires write access to Home Assistant's full configuration directory. NTERM only writes the four companion integration files, leaves other files untouched, and refuses to overwrite a different integration's manifest. If you already manually installed `term_bridge_sensor_map`, bundled versions of its four files will be updated on the next add-on start. The integration's internal domain stays `term_bridge_sensor_map` to preserve existing config entries. Existing NTERM add-on IDs and MQTT topics are likewise unchanged to preserve installations.

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
