from typing import Any


def sample_start(player_id: int = 1006) -> dict[str, Any]:
    return {
        "matchId": "match-test",
        "round": 1,
        "durationRound": 600,
        "map": {
            "gameplay": {
                "roles": {
                    "startNodeId": "S01",
                    "gateNodeId": "S14",
                    "terminalNodeIds": ["S15"],
                }
            }
        },
        "players": [
            {"playerId": player_id, "teamId": "RED", "state": "IDLE", "currentNodeId": "S01"},
            {"playerId": 2001, "teamId": "BLUE", "state": "IDLE", "currentNodeId": "S01"},
        ],
        "nodes": [
            {"nodeId": "S01", "nodeType": "START"},
            {"nodeId": "S02", "nodeType": "NORMAL"},
            {"nodeId": "S14", "nodeType": "GATE"},
            {"nodeId": "S15", "nodeType": "TERMINAL"},
        ],
        "edges": [
            {
                "edgeId": "E01",
                "fromNodeId": "S01",
                "toNodeId": "S02",
                "routeType": "ROAD",
                "distance": 8,
                "bidirectional": True,
            }
        ],
        "resources": [],
        "taskTemplates": [],
    }


def sample_inquire(player_id: int = 1006, round_no: int = 1) -> dict[str, Any]:
    return {
        "matchId": "match-test",
        "round": round_no,
        "phase": "NORMAL",
        "players": [
            {
                "playerId": player_id,
                "teamId": "RED",
                "state": "IDLE",
                "currentNodeId": "S01",
                "verified": False,
                "delivered": False,
                "resources": {},
                "taskScore": 0,
                "totalScore": 0,
            }
        ],
        "nodes": [],
        "edges": [],
        "tasks": [],
        "contests": [],
        "events": [],
        "actionResults": [],
    }

