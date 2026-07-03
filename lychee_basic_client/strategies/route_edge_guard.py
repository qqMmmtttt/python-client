from dataclasses import dataclass


ROUTE_EDGE_GUARD_MODE_SQUAD_HOLD = "squad_hold"
ROUTE_EDGE_GUARD_MODE_LEGACY_RESET = "legacy_reset"
ROUTE_EDGE_GUARD_RECOVERY_MODE = ROUTE_EDGE_GUARD_MODE_SQUAD_HOLD

ROUTE_EDGE_GUARD_RESUME_MOVE = "resume_move"
ROUTE_EDGE_GUARD_WAIT_FOR_SQUAD = "wait_for_squad"


@dataclass(frozen=True)
class RouteEdgeGuardPlan:
    kind: str
    target_node_id: str


def plan_route_edge_guard_recovery(
    target_node_id: str,
    *,
    blocked_by_guard: bool,
) -> RouteEdgeGuardPlan:
    if blocked_by_guard:
        return RouteEdgeGuardPlan(ROUTE_EDGE_GUARD_WAIT_FOR_SQUAD, target_node_id)
    return RouteEdgeGuardPlan(ROUTE_EDGE_GUARD_RESUME_MOVE, target_node_id)
