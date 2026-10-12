"""External sensor thermostat behavior without physical HMPD hardware."""
import time

from term_bridge.bridge import TERMBridge
from term_bridge.config import Controller, ExternalSensor, Options
from term_bridge.models import Zone


def make_bridge():
    controller = Controller(name="usb0", dev="/dev/ttyUSB0", baud=4800, expected_regs=1)
    key = f"{controller.key}_0"
    options = Options(
        controllers=(controller,),
        mqtt_client_id="term_bridge_external_test",
        discovery_registry_path=None,
        naming_migration_marker_path=None,
        external_sensors=(ExternalSensor(zone=key, topic="hotel/room101/temperature"),),
    )
    bridge = TERMBridge(options)
    zone = Zone(
        controller_name=controller.name,
        controller_key=controller.key,
        controller_dev=controller.dev,
        zone_index=0,
        zone_name="Room 101",
        unique_id=key,
        current_temp=23.0,
        controller_target_temp=16.0,
        target_temp=22.5,
        external_topic="hotel/room101/temperature",
    )
    bridge.zones[key] = zone
    jobs = []
    bridge._enqueue_set = lambda z, temp, reason="": jobs.append(temp)  # type: ignore[method-assign]
    bridge.mqtt.publish = lambda *args, **kwargs: None  # type: ignore[method-assign]
    return bridge, zone, jobs


def test_requests_heat_at_32_with_external_sensor():
    bridge, zone, jobs = make_bridge()
    zone.external_temp = 20.0
    zone.external_received_at = time.monotonic()
    bridge._tick_external(zone)
    assert jobs == [32.0]
    assert zone.pending_target == 32.0


def test_minimum_switch_interval_prevents_chattering():
    bridge, zone, jobs = make_bridge()
    zone.external_temp = 23.0
    zone.external_received_at = time.monotonic()
    zone.heat_requested = True
    zone.controller_target_temp = 32.0
    zone.last_switch_at = time.monotonic()
    bridge._tick_external(zone)
    assert jobs == []
    zone.last_switch_at -= 601
    bridge._tick_external(zone)
    assert jobs == [16.0]


def test_sensor_timeout_bypasses_hold_and_requests_idle():
    bridge, zone, jobs = make_bridge()
    zone.external_temp = 19.0
    zone.external_received_at = time.monotonic() - 901
    zone.heat_requested = True
    zone.controller_target_temp = 32.0
    zone.last_switch_at = time.monotonic()
    bridge._tick_external(zone)
    assert jobs == [16.0]


def test_normal_target_is_half_degree_logical_setpoint(tmp_path, monkeypatch):
    from term_bridge import bridge as bridge_module
    monkeypatch.setattr(bridge_module, "THERMOSTAT_TARGETS_PATH", str(tmp_path / "targets.json"))
    bridge, zone, jobs = make_bridge()
    zone.external_temp = 20.0
    zone.external_received_at = time.monotonic()
    bridge._handle_set_target(zone.unique_id, "22.6")
    assert zone.target_temp == 22.5
    assert jobs == [32.0]
    assert bridge.virtual_targets[zone.unique_id] == 22.5
    assert zone.controller_target_temp == 16.0


def test_initial_sensor_grace_does_not_force_idle():
    bridge, zone, jobs = make_bridge()
    zone.controller_target_temp = 32.0
    zone.heat_requested = True
    zone.external_mapped_at = time.monotonic()
    bridge._tick_external(zone)
    assert jobs == []
    assert zone.pending_target is None


def test_missing_first_sensor_expires_after_grace():
    bridge, zone, jobs = make_bridge()
    zone.controller_target_temp = 32.0
    zone.heat_requested = True
    zone.external_mapped_at = time.monotonic() - 901
    bridge._tick_external(zone)
    assert jobs == [16.0]


def test_stale_sensor_supersedes_pending_heat():
    bridge, zone, jobs = make_bridge()
    zone.pending_target = 32.0
    zone.external_temp = 20.0
    zone.external_received_at = time.monotonic() - 901
    zone.external_first_reading = True
    bridge._tick_external(zone)
    assert jobs == [16.0]
    assert zone.pending_target == 16.0
    assert zone.external_generation == 1


def test_mapping_removed_cancels_old_pending_heat():
    from types import SimpleNamespace
    bridge, zone, jobs = make_bridge()
    zone.pending_target = 32.0
    zone.controller_target_temp = 16.0
    old_generation = zone.external_generation
    bridge._on_message(None, None, SimpleNamespace(
        topic=f"{bridge.options.base_topic}/external_map/{zone.unique_id}",
        payload=b"",
    ))
    assert zone.external_topic is None
    assert zone.target_temp == 16.0
    assert zone.pending_target is None
    assert zone.external_generation > old_generation


def test_existing_heating_zone_mapping_retains_heating_state():
    from types import SimpleNamespace
    bridge, zone, jobs = make_bridge()
    bridge.external_by_zone.clear()
    bridge.external_by_topic.clear()
    zone.external_topic = None
    zone.controller_target_temp = 32.0
    zone.heat_requested = False
    bridge._on_message(None, None, SimpleNamespace(
        topic=f"{bridge.options.base_topic}/external_map/{zone.unique_id}",
        payload=b"sensor.room_101",
    ))
    assert zone.heat_requested is True
    assert zone.target_temp is not None
