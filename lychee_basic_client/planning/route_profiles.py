FIRST_ROUND_WATER_ROUTE = [
    "S01",
    "S02",
    "S04",
    "S05",
    "S09",
    "S10",
    "S11",
    "S12",
    "S13",
    "S14",
    "S15",
]

FIRST_ROUND_WATER_EDGE_DISTANCES = {
    ("S01", "S02"): 30,
    ("S02", "S04"): 20,
    ("S04", "S05"): 44,
    ("S05", "S09"): 48,
    ("S09", "S10"): 40,
    ("S10", "S11"): 36,
    ("S11", "S12"): 20,
    ("S12", "S13"): 25,
    ("S13", "S14"): 18,
    ("S14", "S15"): 10,
}

FIRST_ROUND_LAND_ROUTE = [
    "S01",
    "S02",
    "S03",
    "S07",
    "S09",
    "S10",
    "S11",
    "S12",
    "S13",
    "S14",
    "S15",
]

FIRST_ROUND_LAND_EDGE_DISTANCES = {
    ("S01", "S02"): 30,
    ("S02", "S03"): 25,
    ("S03", "S07"): 54,
    ("S07", "S09"): 46,
    ("S09", "S10"): 40,
    ("S10", "S11"): 36,
    ("S11", "S12"): 20,
    ("S12", "S13"): 25,
    ("S13", "S14"): 18,
    ("S14", "S15"): 10,
}

FIRST_ROUND_SAFE_ROUTE = FIRST_ROUND_WATER_ROUTE
FIRST_ROUND_EDGE_DISTANCES = FIRST_ROUND_WATER_EDGE_DISTANCES

# 南岭驿（S02）窗口争夺失败后的替代路线：
# S02 → S04（江南码头）→ S07（荆襄大驿）→ S09（洛阳驿）→ S10（武关）→ ... → S15
# 跳过水路主段 S04→S05→S09，改走支路 S04→S07 与官道 S07→S09
ALTERNATE_ROUTE_AFTER_S02_LOSS = [
    "S02",
    "S04",
    "S07",
    "S09",
    "S10",
    "S11",
    "S12",
    "S13",
    "S14",
    "S15",
]
