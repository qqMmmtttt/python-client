from typing import Any

MOVE_BUFF_TYPES = frozenset({"FAST_HORSE", "SHORT_HORSE", "RUSH_SPEED"})
PROTECT_BUFF_TYPES = frozenset({"RUSH_PROTECT"})


def has_buff(raw_player: dict[str, Any], buff_types: frozenset[str]) -> bool:
    for buff in raw_player.get("buffs") or []:
        if str(buff.get("type") or "").upper() in buff_types:
            return True
    return False


def has_move_buff(raw_player: dict[str, Any]) -> bool:
    return has_buff(raw_player, MOVE_BUFF_TYPES)
