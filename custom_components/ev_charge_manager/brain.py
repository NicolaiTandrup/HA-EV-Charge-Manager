"""Pure association model. No Home Assistant services or hardware access."""

from dataclasses import dataclass
from datetime import datetime

CONNECTED = {"ready to charge", "awaiting start", "charging", "completed", "complete"}
DISCONNECTED = {"car disconnected", "disconnected"}
UNKNOWN = {"unknown", "unavailable", "not_home", ""}


def normalize(value):
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


@dataclass(frozen=True)
class Reading:
    value: str
    reported_at: datetime


@dataclass
class Session:
    car: str | None = None
    last_car: str | None = None
    disconnected_at: datetime | None = None
    manual: bool = False
    override_armed: bool = True


class Brain:
    """Conservative graph matching; a vehicle can belong to at most one charger."""

    def __init__(self, config):
        self.config = config
        self.sessions = {c["id"]: Session() for c in config["chargers"]}

    def evaluate(self, states, now):
        ttl = self.config.get("stale_seconds", 900)

        def read(entity):
            r = states.get(entity)
            if r is None or not 0 <= (now - r.reported_at).total_seconds() <= ttl:
                return None
            if r.value.lower() in {"unknown", "unavailable", ""}:
                return None
            return r.value

        def source(vehicle, role):
            primary = read(vehicle.get(role))
            return primary if primary is not None else read(vehicle.get(role + "_fallback"))

        vehicles = {v["id"]: v for v in self.config["vehicles"]}
        result = {}
        active = []
        for c in self.config["chargers"]:
            key = c["id"]
            session = self.sessions[key]
            status = read(c["status"])
            status = normalize(status) if status else None
            override = read(c.get("override"))
            if override == "off":
                session.override_armed = True
            if status in DISCONNECTED:
                if session.car:
                    session.last_car = session.car
                    session.disconnected_at = now
                session.car = None
                session.manual = False
                # A still-on read-only helper must not reactivate on the next plug.
                if override == "on":
                    session.override_armed = False
                mode = "disconnected"
            elif status in CONNECTED:
                if override == "on" and session.override_armed:
                    session.manual = True
                active.append(c)
                mode = "pending_match"
            else:
                mode = "unavailable"
            result[key] = {
                "charger": key,
                "car": None,
                "car_name": None,
                "mode": mode,
                "valid": False,
                "fresh": status is not None,
                "updated_at": now.isoformat(),
                "last_associated_vehicle": session.last_car,
            }

        # Retain existing sessions even with unknown GPS; physical disconnect alone
        # ends them. Stale status/cable suppress publication, preserving reservation.
        reserved = {s.car for s in self.sessions.values() if s.car}
        pending = []
        for c in active:
            s = self.sessions[c["id"]]
            row = result[c["id"]]
            if s.car:
                cable = source(vehicles[s.car], "cable")
                if cable in {"on", "off"}:
                    row.update(
                        car=s.car,
                        car_name=vehicles[s.car]["name"],
                        valid=True,
                        mode="manual_until_disconnect" if s.manual else "auto_assigned",
                    )
                else:
                    row.update(mode="stale", fresh=False)
            elif s.manual:
                row["mode"] = "manual_until_disconnect"
            else:
                pending.append(c)

        candidates = {}
        for c in pending:
            candidates[c["id"]] = [
                v["id"]
                for v in vehicles.values()
                if v["id"] not in reserved
                and source(v, "cable") == "on"
                and source(v, "tracker") == c["zone_state"]
            ]
        resolved = unique_matching(candidates)
        for c in pending:
            key = c["id"]
            options = candidates[key]
            # Both ends must be unique. Never let charger iteration order decide.
            if key in resolved:
                car = resolved[key]
                s = self.sessions[key]
                s.car = s.last_car = car
                result[key].update(
                    car=car,
                    car_name=vehicles[car]["name"],
                    valid=True,
                    mode="auto_assigned",
                )
            elif options:
                result[key]["mode"] = "ambiguous"
        return result


def unique_matching(candidates):
    """Resolve a bounded passive bipartite graph only when its full match is unique."""
    graph = {k: set(v) for k, v in candidates.items() if v}
    if not graph or len(graph) > 8:
        return {}
    keys = sorted(graph, key=lambda k: (len(graph[k]), k))
    solutions = []

    def visit(index, assigned, used):
        if len(solutions) >= 2:
            return
        if index == len(keys):
            solutions.append(dict(assigned))
            return
        key = keys[index]
        for vehicle in sorted(graph[key] - used):
            assigned[key] = vehicle
            visit(index + 1, assigned, used | {vehicle})
            assigned.pop(key)

    visit(0, {}, set())
    return solutions[0] if len(solutions) == 1 else {}
