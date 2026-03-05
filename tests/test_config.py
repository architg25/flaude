"""Tests for config loading, saving, and migration."""

import yaml

import flaude.config as config_mod
from flaude.config import load_config, migrate_notifications_config, save_config


# -- load_config --


def test_load_valid_yaml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump({"theme": "dark", "refresh": 2}), encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_file)

    result = load_config()
    assert result == {"theme": "dark", "refresh": 2}


def test_load_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "nope.yaml")
    assert load_config() == {}


def test_load_corrupt_yaml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("{{{{not: valid: yaml: [", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_file)

    assert load_config() == {}


def test_load_empty_file(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_file)

    assert load_config() == {}


# -- save_config --


def test_save_writes_valid_yaml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_file)

    save_config({"theme": "light", "count": 42})

    loaded = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert loaded == {"theme": "light", "count": 42}


def test_save_uses_tmp_file(tmp_path, monkeypatch):
    """After save, the .tmp file should not remain (it gets renamed)."""
    cfg_file = tmp_path / "config.yaml"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_file)

    save_config({"x": 1})

    assert cfg_file.exists()
    assert not cfg_file.with_suffix(".yaml.tmp").exists()


def test_save_creates_missing_directory(tmp_path, monkeypatch):
    cfg_file = tmp_path / "nested" / "dir" / "config.yaml"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_file)

    save_config({"key": "val"})

    assert cfg_file.exists()
    loaded = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert loaded == {"key": "val"}


# -- migrate_notifications_config --


def test_migrate_flat_to_nested():
    flat = {
        "notifications": {
            "enabled": True,
            "terminal_bell": False,
            "macos_alert": True,
            "system_sound": True,
            "long_turn_minutes": 3,
        }
    }

    result = migrate_notifications_config(flat)
    notif = result["notifications"]

    assert notif["enabled"] is True
    assert isinstance(notif["long_turn_completion"], dict)
    assert notif["long_turn_completion"]["terminal_bell"] is False
    assert notif["long_turn_completion"]["macos_alert"] is True
    assert notif["long_turn_completion"]["system_sound"] is True
    assert notif["long_turn_completion"]["long_turn_minutes"] == 3
    # waiting_on_input gets defaults
    assert notif["waiting_on_input"]["enabled"] is False
    assert notif["waiting_on_input"]["delay_seconds"] == 10


def test_migrate_already_migrated_is_noop():
    already = {
        "notifications": {
            "enabled": True,
            "long_turn_completion": {
                "enabled": True,
                "terminal_bell": True,
                "macos_alert": False,
                "system_sound": False,
                "long_turn_minutes": 5,
            },
            "waiting_on_input": {
                "enabled": False,
                "terminal_bell": True,
                "macos_alert": False,
                "system_sound": False,
                "delay_seconds": 10,
            },
        }
    }

    result = migrate_notifications_config(already)
    assert result["notifications"] == already["notifications"]


def test_migrate_empty_config():
    result = migrate_notifications_config({})
    notif = result["notifications"]

    assert notif["enabled"] is False
    assert notif["long_turn_completion"]["enabled"] is True
    assert notif["long_turn_completion"]["terminal_bell"] is True
    assert notif["waiting_on_input"]["enabled"] is False
