from dataclasses import dataclass
from typing import Any, Optional

from lychee_basic_client.models.state import NodeState, PlayerState


@dataclass(frozen=True)
class EnemyGuard:
    owner_team_id: str
    defense: int


def enemy_guard_at(node: Optional[NodeState], player: Optional[PlayerState]) -> Optional[EnemyGuard]:
    if node is None or player is None:
        return None
    guard = node.guard or {}
    if guard.get("active") is False:
        return None
    owner_team_id = str(guard.get("ownerTeamId") or guard.get("teamId") or "")
    defense = _int_value(guard.get("defense"))
    if not owner_team_id or owner_team_id == player.team_id or defense <= 0:
        return None
    return EnemyGuard(owner_team_id=owner_team_id, defense=defense)


def obstacle_residue_tax_round(node: Optional[NodeState], player: Optional[PlayerState]) -> int:
    if node is None or player is None:
        return 0
    residue = node.raw.get("obstacleResidue") or {}
    if not residue:
        return 0
    cleared_by_team_id = str(residue.get("clearedByTeamId") or "")
    if cleared_by_team_id and cleared_by_team_id == player.team_id:
        return 0
    if _int_value(residue.get("remainRound")) <= 0 and _int_value(residue.get("untilRound")) <= 0:
        return 0
    return _int_value(residue.get("taxRound")) or 6


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
