"""Durable simulated physical sessions; zero kW never means unplugged."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

from .brain import CONNECTED, DISCONNECTED, normalize


@dataclass
class PlugSession:
    id: str
    authorized: bool = False
    vehicle: str | None = None
    needs_reconciliation: bool = False
    started_at: str | None = None
    last_verified_connected: str | None = None


class Sessions:
    def __init__(self, saved=None):
        self.items = {
            k: PlugSession(**v, needs_reconciliation=True) for k, v in (saved or {}).items()
        }

    def update(self, charger, status, vehicle=None, now=None, reported_at=None):
        now = now or datetime.now(UTC)
        status = normalize(status or "unknown")
        if status in DISCONNECTED:
            self.items.pop(charger, None)
            return None
        if status not in CONNECTED:
            return None  # reserve durable identity but don't expose authorization
        session = self.items.setdefault(
            charger, PlugSession(uuid4().hex, started_at=now.isoformat())
        )
        session.last_verified_connected = (reported_at or now).isoformat()
        if session.needs_reconciliation:
            # We cannot prove that no unplug/replug occurred while HA was offline.
            session.authorized = False
            session.vehicle = None
            session.needs_reconciliation = False
        if vehicle and not session.authorized:
            session.vehicle = vehicle
        return session

    def authorize_guest(self, charger, session_id):
        session = self.items.get(charger)
        if (
            session is None
            or session.id != session_id
            or session.vehicle
            or session.needs_reconciliation
        ):
            raise ValueError("Fresh current unknown session required")
        session.authorized = True

    def persistent(self):
        return {
            k: {a: b for a, b in asdict(v).items() if a != "needs_reconciliation"}
            for k, v in self.items.items()
        }
