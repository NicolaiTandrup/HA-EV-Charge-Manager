"""Enable real Home Assistant custom integration loading."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


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
