"""Enable real Home Assistant custom integration loading."""

import pytest
from homeassistant.helpers.storage import Store

from custom_components.ev_charge_manager.journal import CommandJournalStore

_REAL_WRITE = Store._async_write_data

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def hass_config_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture(autouse=True)
def real_verified_store(monkeypatch):
    # Ordinary Store remains mocked by the plugin; verified ledgers use actual
    # atomic files in each HA fixture's isolated temporary config directory.
    monkeypatch.setattr(CommandJournalStore, "_async_write_data", _REAL_WRITE)


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def config():
    return {
        "vehicles": [
            {
                "id": "a",
                "name": "Vehicle A",
                "device": "va",
                "cable": "binary_sensor.a",
                "tracker": "device_tracker.a",
            },
            {
                "id": "b",
                "name": "Vehicle B",
                "device": "vb",
                "cable": "binary_sensor.b",
                "tracker": "device_tracker.b",
            },
        ],
        "chargers": [
            {
                "id": "one",
                "name": "Charger One",
                "device": "c1",
                "status": "sensor.one",
                "enabled": "switch.one",
                "zone_state": "home",
                "override": "input_boolean.manual",
            },
            {
                "id": "two",
                "name": "Charger Two",
                "device": "c2",
                "status": "sensor.two",
                "enabled": "switch.two",
                "zone_state": "work",
            },
        ],
        "stale_seconds": 900,
    }
