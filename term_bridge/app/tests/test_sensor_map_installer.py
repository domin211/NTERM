"""The companion integration installer must not affect normal bridge operation."""
import json

from install_sensor_map import install


def test_installs_and_is_idempotent(tmp_path):
    source = tmp_path / "bundled"
    destination = tmp_path / "ha" / "custom_components" / "term_bridge_sensor_map"
    source.mkdir()
    for name in ("__init__.py", "config_flow.py", "mapping.py", "strings.json"):
        (source / name).write_text(name)
    (source / "manifest.json").write_text(json.dumps({"domain": "term_bridge_sensor_map"}))
    assert install(source, destination)
    assert (destination / "manifest.json").exists()
    assert install(source, destination)
    assert not list(destination.glob("*.nterm-tmp"))


def test_refuses_to_overwrite_another_integration(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "installed"
    source.mkdir()
    destination.mkdir()
    (destination / "manifest.json").write_text('{"domain":"another_integration"}')
    assert not install(source, destination)
    assert (destination / "manifest.json").read_text() == '{"domain":"another_integration"}'


def test_missing_source_does_not_fail_bridge(tmp_path):
    assert not install(tmp_path / "absent", tmp_path / "destination")


def test_upgrade_preserves_unrelated_files(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    for name in ("__init__.py", "config_flow.py", "strings.json"):
        (source / name).write_text("new")
    (source / "manifest.json").write_text('{"domain":"term_bridge_sensor_map"}')
    (destination / "manifest.json").write_text('{"domain":"term_bridge_sensor_map"}')
    (destination / "custom.py").write_text("preserve")
    (destination / "__init__.py").write_text("old")
    assert install(source, destination)
    assert (destination / "__init__.py").read_text() == "new"
    assert (destination / "custom.py").read_text() == "preserve"


def test_incomplete_bundle_refuses_partial_upgrade(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "installed"
    source.mkdir()
    destination.mkdir()
    for name in ("__init__.py", "config_flow.py", "strings.json"):
        (source / name).write_text("new")
    (source / "manifest.json").write_text('{"domain":"term_bridge_sensor_map"}')
    (destination / "__init__.py").write_text("old")
    assert not install(source, destination)
    assert (destination / "__init__.py").read_text() == "old"
    assert not (destination / "mapping.py").exists()
