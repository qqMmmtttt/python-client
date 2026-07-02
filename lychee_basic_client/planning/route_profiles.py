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
