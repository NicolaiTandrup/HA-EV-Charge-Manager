"""Write-ahead command journal. Recovery observes; it never replays a request."""

import json
from asyncio import Lock
from dataclasses import asdict
from datetime import datetime
from math import isfinite
from pathlib import Path

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .executor import Capability, CommandExecutor, Result


class CommandJournalStore(Store):
    """HA atomic Store writes, verified against disk instead of an in-memory cache.

    Store may swallow write errors or recover corrupt JSON as empty data. Neither
    behavior is acceptable evidence that a command reservation is durable.
    """

    def _read_verified(self):
        try:
            with Path(self.path).open() as stream:
                envelope = json.load(stream)
        except FileNotFoundError:
            return None
        if (
            not isinstance(envelope, dict)
            or type(envelope.get("version")) is not int
            or envelope["version"] != self.version
            or envelope.get("key") != self.key
            or envelope.get("minor_version", 1) != self.minor_version
            or "data" not in envelope
        ):
            raise ValueError("Invalid command journal storage envelope")
        return envelope["data"]

    async def async_load(self):
        # No corrupt-to-empty recovery and no source data in diagnostics/logs.
        return await self.hass.async_add_executor_job(self._read_verified)

    async def async_save(self, data):
        await super().async_save(data)
        if await self.async_load() != data:
            raise HomeAssistantError("Command journal durable write verification failed")


class DurableCommandExecutor(CommandExecutor):
    def __init__(self, hass, *, store, transport=None, **kwargs):
        self.store = store
        self.dispatch = transport
        super().__init__(hass, transport=self._dispatch if transport else None, **kwargs)
        self.journal_lock = Lock()
        self.loaded = False
        self.journal_error = None
        self.recovered = set()
        self.loaded_at = None

    def snapshot(self):
        return {
            "schema_version": 1,
            "requests": self.requests,
            "records": {
                key: {
                    "target": asdict(identity[0]),
                    "session_id": identity[1],
                    "owner": identity[2],
                    "value": identity[3],
                    "attempted_at": attempted.isoformat(),
                    "result": asdict(result),
                }
                for key, (identity, attempted, result) in self.records.items()
            },
        }

    async def async_load(self):
        """Do not install/enable a transport, grant authority or replay anything."""
        self.loaded = False
        try:
            data = await self.store.async_load()
            records, owners, pending, recovered = {}, {}, {}, set()
            requests = 0
            if data is not None:
                if (
                    not isinstance(data, dict)
                    or type(data.get("schema_version")) is not int
                    or data["schema_version"] != 1
                    or type(data.get("requests")) is not int
                    or data["requests"] < 0
                    or not isinstance(data.get("records"), dict)
                    or len(data["records"]) > data["requests"]
                ):
                    raise ValueError("Invalid command journal")
                requests = data["requests"]
                for key, row in data["records"].items():
                    target = Capability(**row["target"])
                    result = Result(**row["result"])
                    attempted = datetime.fromisoformat(row["attempted_at"])
                    value = row["value"]
                    if (
                        not key
                        or not isinstance(key, str)
                        or attempted.tzinfo is None
                        or not row["session_id"]
                        or row["owner"] not in {"brain", "optimizer", "manual"}
                        or result.status not in {"uncertain", "awaiting_observation", "observed"}
                        or (
                            value is not None
                            and (
                                isinstance(value, bool)
                                or not isinstance(value, (int, float))
                                or not isfinite(value)
                            )
                        )
                    ):
                        raise ValueError("Invalid persisted intent")
                    identity = (target, row["session_id"], row["owner"], value)
                    records[key] = (identity, attempted, result)
                    resource = (target.device, row["session_id"])
                    if resource in owners and owners[resource] != row["owner"]:
                        raise ValueError("Conflicting persisted ownership")
                    owners[resource] = row["owner"]
                    if result.status != "observed":
                        if target.device in pending:
                            raise ValueError("Multiple unresolved device commands")
                        pending[target.device] = key
                        recovered.add(key)
            self.records, self.owners, self.pending = records, owners, pending
            self.requests, self.recovered = requests, recovered
            self.loaded_at = dt_util.utcnow()
            self.loaded, self.journal_error = True, None
        except OSError, HomeAssistantError, ValueError, TypeError, KeyError, AttributeError:
            self.journal_error = "Unable to verify command journal"
            # Do not overwrite a corrupt or unreadable journal with an empty one.

    async def _save(self):
        try:
            await self.store.async_save(self.snapshot())
        except OSError, HomeAssistantError, ValueError, TypeError:
            self.journal_error = "Unable to persist command journal"
            raise HomeAssistantError(self.journal_error) from None

    async def _dispatch(self, *args, **kwargs):
        # Base executor has reserved intent, ownership, budget and uncertainty.
        # That reservation must be durable before a transport can be invoked.
        await self._save()
        await self.dispatch(*args, **kwargs)

    async def execute(self, key, target, context, value=None):
        async with self.journal_lock:
            if not self.loaded or self.journal_error:
                return Result("journal_error", self.journal_error or "Journal not loaded")
            if key in self.recovered:
                return Result(
                    "recovery_required", "Explicit read-only session reconciliation required"
                )
            before = self.snapshot()
            result = await super().execute(key, target, context, value)
            if self.journal_error:
                return Result("journal_error", self.journal_error)
            if self.snapshot() != before:
                try:
                    await self._save()
                except HomeAssistantError:
                    return Result("journal_error", self.journal_error)
            return result

    async def reconcile(self, key, context, *, session_verified=False):
        """Explicit verified continuity + post-recovery observation; never dispatch.

        session_verified is an internal test/commissioning input, not a UI grant or
        proof derived from HA startup. Future live wiring must verify a physical
        charger session identifier independently. No public reconciliation service.
        """
        async with self.journal_lock:
            if not self.loaded or self.journal_error:
                return Result("journal_error", self.journal_error or "Journal not loaded")
            if not session_verified or key not in self.records:
                return Result("recovery_required", "Verified physical-session continuity required")
            identity, attempted, result = self.records[key]
            target, session, owner, value = identity
            if (context.session_id, context.owner) != (session, owner):
                return Result("unsafe", "Persisted session/owner mismatch")
            entity = er.async_get(self.hass).async_get(target.registry_id)
            state = self.hass.states.get(entity.entity_id) if entity else None
            if not state or state.last_reported <= max(attempted, self.loaded_at):
                return Result("recovery_required", "New post-recovery report required")
            previous_transport = self.transport

            async def forbidden(*args, **kwargs):
                raise AssertionError("Reconciliation must never dispatch")

            self.transport = forbidden
            try:
                result = await super().execute(key, target, context, value)
            finally:
                self.transport = previous_transport
            if result.status == "observed":
                self.recovered.discard(key)
                try:
                    await self._save()
                except HomeAssistantError:
                    return Result("journal_error", self.journal_error)
            return result

    def diagnostics(self):
        return {
            "transport_enabled": self.dispatch is not None,
            "journal_loaded": self.loaded,
            "journal_error": self.journal_error,
            "attempted_requests": self.requests,
            "unresolved_requests": len(self.pending),
            "recovery_required": len(self.recovered),
        }
