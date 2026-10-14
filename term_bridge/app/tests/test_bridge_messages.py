from term_bridge import bridge as bridge_module
from term_bridge.bridge import TERMBridge
from term_bridge.config import Controller, Options, TempRange


def make_bridge(*, registry_path: str | None = None) -> TERMBridge:
    options = Options(
        controllers=(Controller(name="usb0", dev="/dev/ttyUSB0", baud=4800, expected_regs=1),),
        temp_range=TempRange(),
        mqtt_client_id="term_bridge_test",
        discovery_registry_path=registry_path,
        naming_migration_marker_path=None,
    )
    bridge = TERMBridge(options)
    bridge.published = []  # type: ignore[attr-defined]

    def fake_publish(topic, payload="", qos=0, retain=False):
        bridge.published.append((topic, payload, retain))

    bridge.mqtt.publish = fake_publish  # type: ignore[method-assign]
    return bridge


REGS_LINES = [
    "0 | Room A | cur: 21.0 | tgt: 22.0 | EN",
    "1 | Room B | cur: 19.5 | tgt: 18.0 | EN",
]
TEMPS_LINES = ["0: 21.4", "1: 19.9"]


def test_apply_regs_creates_zones_and_publishes_discovery_and_state():
    bridge = make_bridge()
    controller = bridge.controllers[0]

    bridge._apply_regs(controller, REGS_LINES)

    assert set(bridge.zones.keys()) == {f"{controller.key}_0", f"{controller.key}_1"}
    zone_a = bridge.zones[f"{controller.key}_0"]
    assert zone_a.zone_name == "Room A"
    assert zone_a.target_temp == 22.0
    assert zone_a.discovered is True

    discovery_topics = [topic for topic, _, _ in bridge.published if "/config" in topic]
    assert any(f"term_bridge_{controller.key}_0" in topic for topic in discovery_topics)


def test_apply_regs_removes_stale_zones_not_present_in_latest_scan():
    bridge = make_bridge()
    controller = bridge.controllers[0]

    bridge._apply_regs(controller, REGS_LINES)
    assert len(bridge.zones) == 2

    bridge._apply_regs(controller, [REGS_LINES[0]])  # zone 1 no longer reported

    assert set(bridge.zones.keys()) == {f"{controller.key}_0"}


def test_apply_temps_updates_current_temp_for_known_zones():
    bridge = make_bridge()
    controller = bridge.controllers[0]
    bridge._apply_regs(controller, REGS_LINES)

    bridge._apply_temps(controller, TEMPS_LINES)

    assert bridge.zones[f"{controller.key}_0"].current_temp == 21.4
    assert bridge.zones[f"{controller.key}_1"].current_temp == 19.9


def test_handle_set_target_snaps_value_and_enqueues_job():
    bridge = make_bridge()
    controller = bridge.controllers[0]
    bridge._apply_regs(controller, REGS_LINES)
    zone_key = f"{controller.key}_0"

    bridge._handle_set_target(zone_key, "23.6")

    assert bridge.zones[zone_key].target_temp == 24.0
    assert bridge.queues[controller.key].pending_set_count() == 1


def test_handle_set_target_ignores_unknown_zone_and_bad_payload():
    bridge = make_bridge()
    controller = bridge.controllers[0]
    bridge._apply_regs(controller, REGS_LINES)

    bridge._handle_set_target("does-not-exist", "20.0")
    bridge._handle_set_target(f"{controller.key}_0", "not-a-number")

    assert bridge.queues[controller.key].pending_set_count() == 0


def test_off_mode_reflected_in_state_payload():
    bridge = make_bridge()
    controller = bridge.controllers[0]
    bridge._apply_regs(controller, REGS_LINES)

    zone_b = bridge.zones[f"{controller.key}_1"]  # target_temp 18.0 <= off threshold
    assert zone_b.is_off_mode(18.0) is True


def test_apply_regs_never_creates_disabled_zones_even_with_valid_temp():
    bridge = make_bridge()
    controller = bridge.controllers[0]

    lines = REGS_LINES + ["2 | Unused Slot | cur: 21.0 | tgt: 18.0 | DIS"]
    bridge._apply_regs(controller, lines)

    assert f"{controller.key}_2" not in bridge.zones
    assert set(bridge.zones.keys()) == {f"{controller.key}_0", f"{controller.key}_1"}


def test_apply_regs_removes_zone_that_becomes_disabled():
    bridge = make_bridge()
    controller = bridge.controllers[0]

    bridge._apply_regs(controller, REGS_LINES)
    assert f"{controller.key}_1" in bridge.zones

    disabled_lines = [REGS_LINES[0], "1 | Room B | cur: 19.5 | tgt: 18.0 | DIS"]
    bridge._apply_regs(controller, disabled_lines)

    assert f"{controller.key}_1" not in bridge.zones


def test_health_payload_reports_connection_queue_and_sync_state():
    bridge = make_bridge()
    controller = bridge.controllers[0]
    bridge.mqtt_connected = True
    bridge.last_successful_sync[controller.key]["temps"] = 1_700_000_000

    payload = bridge.health_payload()
    controller_health = payload["controllers"][controller.key]

    assert payload["status"] == "online"
    assert payload["mqtt_client_id"] == "term_bridge_test"
    assert controller_health["last_successful_sync"]["temps"].startswith("2023-")
    assert controller_health["queue"]["pending_jobs"] == 0


def test_tls_client_uses_ca_client_certificate_and_hostname_validation(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, **kwargs):
            calls["client"] = kwargs

        def tls_set(self, **kwargs):
            calls["tls_set"] = kwargs

        def reconnect_delay_set(self, **kwargs):
            calls["reconnect"] = kwargs

    monkeypatch.setattr(bridge_module.mqtt, "Client", FakeClient)
    options = Options(
        controllers=(Controller(name="main", dev="/dev/ttyUSB0", baud=4800),),
        mqtt_client_id="term_bridge_tls_test",
        mqtt_tls=True,
        mqtt_tls_ca="/config/ca.pem",
        mqtt_tls_cert="/config/client.pem",
        mqtt_tls_key="/config/client.key",
    )

    TERMBridge(options)

    assert calls["client"]["client_id"] == "term_bridge_tls_test"
    assert calls["tls_set"]["ca_certs"] == "/config/ca.pem"
    assert calls["tls_set"]["certfile"] == "/config/client.pem"
    assert calls["tls_set"]["keyfile"] == "/config/client.key"


def test_controller_status_changes_after_sync_success_and_failure():
    bridge = make_bridge()
    controller = bridge.controllers[0]
    bridge.mqtt_connected = True
    callback = bridge._make_completion_callback(controller)

    callback(bridge_module.ControllerJob(kind="temps"), None)
    assert bridge.controller_online[controller.key] is True
    assert bridge.published[-2][0] == bridge.topics.controller_status(controller.key)
    assert bridge.published[-2][1] == "online"

    callback(bridge_module.ControllerJob(kind="regs"), RuntimeError("serial timeout"))
    assert bridge.controller_online[controller.key] is False
    assert bridge.controller_last_error[controller.key] == "serial timeout"
    assert bridge.published[-2][1] == "offline"


def test_mqtt_connect_publishes_controller_discovery_and_current_status():
    bridge = make_bridge()
    controller = bridge.controllers[0]
    bridge.mqtt.subscribe = lambda topic: None  # type: ignore[method-assign]

    bridge._on_connect(bridge.mqtt, None, None, "Success", None)

    published_topics = [topic for topic, _, _ in bridge.published]
    assert bridge.topics.controller_status_discovery(controller.key) in published_topics
    assert bridge.topics.controller_status(controller.key) in published_topics


def test_registry_removes_retained_topics_for_zones_missing_after_restart(tmp_path):
    registry_path = tmp_path / "registry.json"
    bridge = make_bridge(registry_path=str(registry_path))
    controller = bridge.controllers[0]
    stale_id = f"{controller.key}_7"
    bridge.discovery_registry.replace(controller.key, {stale_id})

    bridge._apply_regs(controller, [REGS_LINES[0]])

    cleared = [
        (topic, payload, retain)
        for topic, payload, retain in bridge.published
        if stale_id in topic and payload == ""
    ]
    assert {topic for topic, _, _ in cleared} == {
        bridge.topics.discovery(stale_id),
        bridge.topics.state(stale_id),
        bridge.topics.command(stale_id),
    }
    assert all(retain is True for _, _, retain in cleared)


def test_channel_five_temperature_survives_mapping_without_reading():
    """A retained mapping must not hide a valid controller reading with null."""
    import json
    from types import SimpleNamespace

    bridge = make_bridge()
    controller = bridge.controllers[0]
    unique_id = f"{controller.key}_5"
    # Channel numbers, room names and HA entity IDs are separate identities.
    bridge._apply_temps(controller, [f"{idx}: {22.0 if idx == 5 else 19.0}" for idx in range(64)])
    bridge._apply_regs(controller, ["5 | 08 Koupelna | cur: 21.9 | tgt: 20.0 | EN"])
    zone = bridge.zones[unique_id]
    assert zone.current_temp == 22.0

    def state():
        return [json.loads(payload) for topic, payload, _ in bridge.published
                if topic == bridge.topics.state(unique_id)][-1]

    assert state()["current_temp"] == 22.0
    discovery = bridge.topics.discovery_payload(zone, bridge.temp_range)
    assert discovery["unique_id"] == f"term_bridge_{unique_id}"
    assert discovery["current_temperature_topic"] == f"term_bridge/{unique_id}/state"
    assert discovery["current_temperature_template"] == "{{ value_json.current_temp }}"

    def message(topic, payload):
        bridge._on_message(None, None, SimpleNamespace(topic=topic, payload=payload))

    mapping_topic = f"term_bridge/external_map/{unique_id}"
    message(mapping_topic, b"sensor.koupelna")
    assert zone.external_topic is not None
    assert zone.external_temp is None
    assert state()["current_temp"] == 22.0
    # Controller polling continues while waiting for the first external reading.
    bridge._apply_temps(controller, ["5: 22.1"])
    assert state()["current_temp"] == 22.1
    message(f"term_bridge/external/{unique_id}", b"21.75")
    assert state()["current_temp"] == 21.75
    bridge._apply_temps(controller, ["5: 22.2"])
    assert state()["current_temp"] == 21.75
    message(mapping_topic, b"")
    assert zone.external_topic is None
    assert state()["current_temp"] == 22.2
    assert state()["target_temp"] == zone.controller_target_temp
