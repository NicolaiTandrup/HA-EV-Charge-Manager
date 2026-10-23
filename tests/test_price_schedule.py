"""Publication times are conditional; 00:01 checks even a complete prior day."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.ev_charge_manager.price_engine import PriceEngine
from custom_components.ev_charge_manager.price_schedule import PriceSchedule

from .test_price_engine import rows


@pytest.fixture
def scheduled(hass):
    entry = MockConfigEntry(domain="ev_charge_manager")
    entry.add_to_hass(hass)
    site = {"id": "home", "timezone": "Europe/Copenhagen"}
    engine = PriceEngine(hass, entry.entry_id)
    updater = SimpleNamespace(
        status={"home": {"status": "READY"}}, refresh=AsyncMock(return_value=False)
    )
    coordinator = SimpleNamespace(
        hass=hass,
        entry=entry,
        sites={"home": SimpleNamespace(site=site)},
        price_engine=engine,
        price_updater=updater,
        async_request_refresh=AsyncMock(),
    )
    return PriceSchedule(coordinator)


@pytest.mark.parametrize(
    "hour,minute,fetch",
    [(13, 5, True), (13, 20, False), (13, 40, False), (23, 59, False), (0, 1, True)],
)
async def test_complete_day_conditional_schedule(scheduled, hour, minute, fetch):
    now = datetime(2026, 10, 23, hour, minute, tzinfo=UTC)
    local = now.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Copenhagen"))
    # Use local requested civil date independent of the UTC hour in this test.
    target = local.date() if (hour, minute) == (0, 1) else local.date() + timedelta(days=1)
    engine = scheduled.coordinator.price_engine
    await engine.async_update("home", rows(target), {"mode": "all_in"}, {}, now - timedelta(days=2))
    scheduled.days = {"home": {str(target): {"status": "READY"}}}
    await scheduled.run(now, hour, minute)
    assert scheduled.coordinator.price_updater.refresh.called is fetch
    scheduled.coordinator.async_request_refresh.assert_not_called()


async def test_partial_day_retry_and_changed_data_replans_once(scheduled):
    now = datetime(2026, 10, 23, 11, 20, tzinfo=UTC)
    scheduled.coordinator.price_updater.status["home"] = {"status": "INCOMPLETE"}
    await scheduled.run(now, 13, 20)
    assert scheduled.days["home"]["2026-10-24"]["status"] == "INCOMPLETE"
    scheduled.coordinator.price_updater.refresh.return_value = True
    await scheduled.run(now + timedelta(minutes=20), 13, 40)
    scheduled.coordinator.async_request_refresh.assert_awaited_once()


async def test_native_timer_and_unload_cancellation(scheduled, freezer):
    freezer.move_to(datetime(2026, 10, 23, 11, 4, 50, tzinfo=UTC))
    scheduled.run = AsyncMock()
    scheduled.listen()
    freezer.move_to(dt_util.utcnow() + timedelta(seconds=11))
    async_fire_time_changed(scheduled.hass)
    await scheduled.hass.async_block_till_done()
    scheduled.run.assert_awaited_once()
    assert scheduled.run.call_args.args[1:] == (13, 5)
    scheduled.stop()
    freezer.move_to(dt_util.utcnow() + timedelta(hours=1))
    async_fire_time_changed(scheduled.hass)
    await scheduled.hass.async_block_till_done()
    assert scheduled.run.await_count == 1


async def test_incomplete_corrected_day_does_not_mix_with_old_complete_table(hass):
    from homeassistant.core import SupportsResponse

    from custom_components.ev_charge_manager.price_update import PriceUpdater

    engine = PriceEngine(hass, "atomic_day")
    day = date(2026, 10, 24)
    data = rows(day)
    now = datetime(2026, 10, 23, 11, 5, tzinfo=UTC)
    await engine.async_update("home", data, {"mode": "all_in"}, {}, now)

    async def partial(call):
        return {
            "DK2": [
                {"start": data[0].start.isoformat(), "end": data[0].end.isoformat(), "price": 5000}
            ]
        }

    hass.services.async_register(
        "nordpool", "get_prices_for_date", partial, supports_response=SupportsResponse.ONLY
    )
    updater = PriceUpdater(hass, engine)
    site = {
        "id": "home",
        "timezone": "Europe/Copenhagen",
        "nordpool_entry": "np",
        "tariff": {"mode": "spot_ex_vat"},
    }
    assert not await updater.refresh(site, now, force=True, dates=[day])
    assert updater.status["home"]["status"] == "INCOMPLETE"
    assert engine.lookup("home", data[0].start, data[0].end)[0].final_price_incl_vat == -0.1


async def test_unchanged_watchdog_does_not_replan_until_regular_tick(hass, freezer):
    from unittest.mock import patch

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .test_manager import model

    freezer.move_to("2026-10-23T12:00:00+00:00")
    config = model(hass)
    # No selected allocation boundary before the next regular tick.
    price_rows = []
    cursor = datetime(2026, 10, 23, 12, tzinfo=UTC)
    for i in range(96):
        price_rows.append(
            {
                "start": cursor.isoformat(),
                "end": (cursor + timedelta(minutes=15)).isoformat(),
                "price": 10 if i < 4 else 1,
            }
        )
        cursor += timedelta(minutes=15)
    hass.states.async_set("sensor.prices", "1", {"slots": price_rows})
    with patch(
        "custom_components.ev_charge_manager.optimizer.plan_site",
        wraps=__import__(
            "custom_components.ev_charge_manager.planner", fromlist=["plan_site"]
        ).plan_site,
    ) as planner:
        entry = MockConfigEntry(domain="ev_charge_manager", data=config)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        calls = planner.call_count
        for seconds in (15, 30, 45):
            freezer.move_to(datetime(2026, 10, 23, 12, tzinfo=UTC) + timedelta(seconds=seconds))
            await entry.runtime_data.async_refresh()
        assert planner.call_count == calls
        # Refresh identical field reports so source TTL/skew isn't the trigger.
        for field, value in {
            "soc": "60",
            "target": "65",
            "cable": "on",
            "tracker": "home",
            "charging": "off",
        }.items():
            hass.states.async_set("sensor.car_" + field, value)
        freezer.move_to("2026-10-23T12:30:00+00:00")
        # Mark every required source fresh at the new tick.
        for field, value in {
            "soc": "60",
            "target": "65",
            "cable": "on",
            "tracker": "home",
            "charging": "off",
        }.items():
            hass.states.async_set("sensor.car_" + field, value)
        hass.states.async_set("sensor.charger", "charging")
        await entry.runtime_data.async_refresh()
        assert planner.call_count > calls
        assert await hass.config_entries.async_unload(entry.entry_id)
