# Changelog

## 0.8.4

- Existing single-room Sensor Mapping entries now expose the same Add/Change/Remove controls as the multi-room manager, without losing their original sensor.
- Convert legacy entry options to multi-room mappings when adding the second room; preserve one authoritative publisher per room.

## 0.8.3

- Replaced blank sensor-manager action menu with a dropdown using explicit embedded option labels; works even if menu translations are not displayed.

## 0.8.2

- Fixed blank sensor-manager menu by including the Home Assistant custom integration English translations and explicit menu labels.
- Install nested translation files automatically with the companion integration.

## 0.8.1

- Fixed the companion integration installer omitting `mapping.py`, which prevented Home Assistant loading NTERM Sensor Mapping.
- Check for a complete bundled integration before copying files.
- Removed the redundant external sensor configuration field from the add-on UI; pre-existing manual mappings remain supported by the bridge.

## 0.8.0 (proposed)

- Introduced one NTERM Sensor Manager for multiple rooms with Add/Change/Remove controls.
- Migrates existing version-1 room entries to version 2 without discarding sensor mappings.
- Elects exactly one temperature publisher per room across manager and legacy entries.
- Stores pending MQTT mapping deletions durably and retries failed MQTT writes every minute.
- Preserved existing per-room entries during transition and added mapped-room overview.
- Added mapping and external-temperature receipt diagnostics to the NTERM add-on logs.
- Added a regression test for MQTT temperature propagation into climate state.

## 0.7.1

- Hardcoded the sensor-mapping MQTT prefix to `term_bridge` and removed the base-topic field from the setup and options dialogs.

## 0.7

- Rebranded the Home Assistant add-on to NTERM without changing existing integration identifiers or MQTT topics.
- Bundled and auto-installed the optional NTERM Sensor Mapping custom integration; a Home Assistant Core restart is required to load new integration code.
- Kept unmapped rooms on normal HMPD temperature/setpoint operation.
- Added safe installer regression tests.


## 5.1.4

- Fixed duplicated Home Assistant names by making each climate entity the main
  feature of its zone device.
- Added preferred default entity IDs such as `climate.21_pokoj`.
- Added a one-time cleanup of retained discovery/state/command topics from both
  TERM Bridge and the previous HMPD namespace.
- Added a persistent discovery registry that removes retained MQTT topics for
  zones that disappear or are renamed after a restart.

## 5.1.3

- Removed the overly restrictive custom AppArmor policy that blocked container
  DNS resolution and Python package discovery.
- Restored Home Assistant's default AppArmor protection profile.
- Added a complete container smoke test using hostname-based MQTT discovery and
  a simulated serial controller.

## 5.1.2

- Fixed AppArmor read/traversal access for the immutable Python application and
  virtual-environment package trees.

## 5.1.1

- Fixed AppArmor execution rules for virtual-environment Python and BusyBox
  utilities used by the restart runner.

## 5.1.0

- Added a Home Assistant connectivity sensor for every configured controller.
- Added retained controller online/offline state and failure details.
- Added MQTT TLS with mandatory certificate and hostname validation.
- Added stable, installation-specific MQTT client identities.
- Added strict configuration validation and an options transfer helper.
- Added structured bridge and controller health diagnostics.
- Added an AppArmor profile and hardened the container runtime.
- Added hashed runtime dependencies and a digest-pinned Alpine base image.
- Added dependency auditing, CodeQL, dependency review, and container vulnerability scanning.
- Added disposable Mosquitto integration tests.
- Reduced sensitive controller output to debug logging.
