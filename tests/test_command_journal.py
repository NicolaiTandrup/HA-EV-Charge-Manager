"""Crash/restart regressions using HA's real durable Store and mock transport."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.storage import Store

from custom_components.ev_charge_manager.executor import capabilities
from custom_components.ev_charge_manager.journal import CommandJournalStore, DurableCommandExecutor

from .test_command_executor import context, setup_target

# Capture before the plugin patches Store I/O, then explicitly exercise real
# atomic file writes under the HA test instance's temporary configuration.
_REAL_WRITE = Store._async_write_data


@pytest.fixture(autouse=True)
def physical_journal_store(monkeypatch, hass, tmp_path):
    monkeypatch.setattr(hass.config, "config_dir", str(tmp_path))
    monkeypatch.setattr(CommandJournalStore, "_async_write_data", _REAL_WRITE)


async def test_prepare_is_durable_before_dispatch_and_restart_never_replays(hass):
    target = capabilities(hass, setup_target(hass))["start"]
    store = CommandJournalStore(hass, 1, "test.command_journal")
    snapshots = []

    async def dispatch(*args, **kwargs):
        snapshots.append(await store.async_load())

    executor = DurableCommandExecutor(hass, store=store, transport=dispatch)
    await executor.async_load()
    assert (await executor.execute("one", target, context())).status == "awaiting_observation"
    assert snapshots[0]["records"]["one"]["result"]["status"] == "uncertain"
    transport = AsyncMock()
    restored = DurableCommandExecutor(
        hass, store=CommandJournalStore(hass, 1, "test.command_journal"), transport=transport
    )
    await restored.async_load()
    assert restored.requests == 1
    assert (await restored.execute("one", target, context())).status == "recovery_required"
    assert (await restored.execute("another", target, context())).status == "resource_uncertain"
    transport.assert_not_called()
    # A cached report/new HA startup alone is not session continuity evidence.
    hass.states.async_set("switch.charge", "on")
    assert (await restored.reconcile("one", context())).status == "recovery_required"
    assert (await restored.reconcile("one", context(), session_verified=True)).status == "observed"
    transport.assert_not_called()
    disabled = DurableCommandExecutor(
        hass, store=CommandJournalStore(hass, 1, "test.command_journal")
    )
    await disabled.async_load()
    assert disabled.transport is None
    assert not disabled.pending


async def test_failed_prepare_storage_prevents_dispatch_and_corruption_blocks(hass):
    target = capabilities(hass, setup_target(hass))["start"]
    store = AsyncMock()
    store.async_load.return_value = None
    store.async_save.side_effect = OSError("disk full")
    transport = AsyncMock()
    executor = DurableCommandExecutor(hass, store=store, transport=transport)
    await executor.async_load()
    assert (await executor.execute("one", target, context())).status == "journal_error"
    transport.assert_not_called()
    store.async_load.return_value = {"schema_version": 42}
    await executor.async_load()
    assert (await executor.execute("two", target, context())).status == "journal_error"
    transport.assert_not_called()


async def test_crash_after_reservation_and_failed_result_save_never_replay(hass):
    import asyncio
    from copy import deepcopy

    target = capabilities(hass, setup_target(hass))["start"]
    store = AsyncMock()
    store.async_load.return_value = None
    committed = None

    async def save(data):
        nonlocal committed
        committed = deepcopy(data)

    store.async_save.side_effect = save

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    executor = DurableCommandExecutor(hass, store=store, transport=cancelled)
    await executor.async_load()
    with pytest.raises(asyncio.CancelledError):
        await executor.execute("crash", target, context())
    assert committed["records"]["crash"]["result"]["status"] == "uncertain"
    store.async_load.return_value = committed
    resumed = DurableCommandExecutor(hass, store=store, transport=AsyncMock())
    await resumed.async_load()
    assert (await resumed.execute("crash", target, context())).status == "recovery_required"
    resumed.dispatch.assert_not_called()


async def test_failed_completion_save_leaves_durable_uncertainty(hass):
    from copy import deepcopy

    target = capabilities(hass, setup_target(hass))["start"]
    store = AsyncMock()
    store.async_load.return_value = None
    committed = None

    async def save(data):
        nonlocal committed
        if committed is not None:
            raise OSError("completion unavailable")
        committed = deepcopy(data)

    store.async_save.side_effect = save
    transport = AsyncMock()
    executor = DurableCommandExecutor(hass, store=store, transport=transport)
    await executor.async_load()
    assert (await executor.execute("one", target, context())).status == "journal_error"
    assert transport.await_count == 1
    assert committed["records"]["one"]["result"]["status"] == "uncertain"
    assert (await executor.execute("two", target, context())).status == "journal_error"
    assert transport.await_count == 1


async def test_native_lifecycle_loads_journal_without_enabling_transport(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .test_manager import model

    entry = MockConfigEntry(domain="ev_charge_manager", data=model(hass))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    assert c.executor.loaded and c.executor.transport is None
    assert c.executor.diagnostics()["transport_enabled"] is False
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_actual_ha_swallowed_write_error_and_corrupt_json_fail_closed(hass):
    from pathlib import Path
    from unittest.mock import patch

    from homeassistant.util.file import WriteError

    target = capabilities(hass, setup_target(hass))["start"]
    store = CommandJournalStore(hass, 1, "test.strict_journal")
    transport = AsyncMock()
    executor = DurableCommandExecutor(hass, store=store, transport=transport)
    await executor.async_load()
    with patch.object(store, "_async_write_data", side_effect=WriteError("disk full")):
        assert (await executor.execute("one", target, context())).status == "journal_error"
    transport.assert_not_called()
    path = Path(store.path)
    await hass.async_add_executor_job(path.parent.mkdir, 0o700, True, True)
    await hass.async_add_executor_job(path.write_text, "{corrupt")
    restored = DurableCommandExecutor(hass, store=store, transport=transport)
    await restored.async_load()
    assert (await restored.execute("two", target, context())).status == "journal_error"
    assert await hass.async_add_executor_job(path.read_text) == "{corrupt"
    transport.assert_not_called()
