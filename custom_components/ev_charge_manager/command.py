"""Simulation-only command ownership. Deliberately has no live transport."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Intent:
    key: str
    session_id: str
    owner: str
    action: str
    value: float | None = None


class CommandManager:
    def __init__(self, budget=100):
        self.budget = budget
        self.estimated_requests = 0
        self.intents = {}
        self.owners = {}
        self.trace = []

    def propose(self, intent, *, current_session, fresh, authorized, guest=False):
        reason = "simulated"
        if intent.action not in {"start", "stop", "limit", "probe"} or intent.owner not in {
            "brain",
            "optimizer",
            "manual",
        }:
            reason = "unsupported"
        elif intent.value is not None and (
            not isfinite(intent.value) or not 0 <= intent.value <= 100
        ):
            reason = "invalid_value"
        elif intent.action == "limit" and intent.value is None:
            reason = "invalid_value"
        elif not fresh or not authorized or intent.session_id != current_session:
            reason = "unsafe_session"
        elif guest and intent.owner != "manual":
            reason = "guest_protected"
        elif self.owners.get(current_session, intent.owner) != intent.owner:
            reason = "ownership_conflict"
        elif intent.key in self.intents:
            reason = "duplicate" if self.intents[intent.key] == intent else "idempotency_conflict"
        elif self.estimated_requests >= self.budget:
            reason = "budget_exhausted"
        if reason == "simulated":
            self.estimated_requests += 1
            self.intents[intent.key] = intent
            self.owners[current_session] = intent.owner
        self.trace = [*self.trace[-49:], {"action": intent.action, "result": reason}]
        return reason
