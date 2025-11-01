import json
import os
# --- Adjust target_level based on the two special mission doors ---
def resolve_special_mission_doors(char: dict, current_level: str, target_level: str) -> str:
    missions = char.get("Missions", {})
    # Case 1: SwampRoadNorth -> SwampRoadConnectionMission (Mission 23)
    if current_level == "SwampRoadNorth" and target_level == "SwampRoadConnectionMission":
        state = missions.get("23", {}).get("state", 0)
        if state == 2:
            return "SwampRoadConnection"
    # Case 2: BridgeTown -> AC_Mission1 (Mission 92)
    if current_level == "BridgeTown" and target_level == "AC_Mission1":
        state = missions.get("92", {}).get("state", 0)
        if state == 2:
            return "Castle"
    # default: no change
    return target_level

SPECIAL_SPAWN_MAP = {
    ("SwampRoadNorth", "NewbieRoad"): (20298.00, 639.00),
    ("SwampRoadNorthHard", "NewbieRoadHard"): (20298.00, 639.00),
    ("SwampRoadConnection", "SwampRoadNorth"): (193, 511),
    ("SwampRoadConnectionHard", "SwampRoadNorthHard"): (193, 511),
    ("EmeraldGlades", "OldMineMountain"): (18552, 4021),
    ("EmeraldGladesHard", "OldMineMountainHard"): (18552, 4021),
    ("SwampRoadNorth", "SwampRoadConnection"): (325.00, 368.00),
    ("SwampRoadNorthHard", "SwampRoadConnectionHard"): (325.00, 368.00),
    ("BridgeTown", "SwampRoadConnection"): (10533.00, 461.00),
    ("BridgeTownHard", "SwampRoadConnectionHard"): (10533.00, 461.00),
    ("OldMineMountain", "BridgeTown"): (16986, -296.01),
    ("OldMineMountainHard", "BridgeTownHard"): (16986, -296.01),
    ("BridgeTown", "BridgeTownHard"): (11439, 2198.99),
    ("BridgeTownHard", "BridgeTown"): (11439, 2198.99),
    ("Castle", "BridgeTown"): (10566, 492.99),
    ("CastleHard", "BridgeTownHard"): (10566, 492.99),
    ("ShazariDesert", "ShazariDesertHard"): (14851.25, 638.4691666666666),
    ("ShazariDesertHard", "ShazariDesert"): (14851.25, 638.4691666666666),
    ("JadeCity", "ShazariDesert"): (25857.25, 1298.4691666666668),
    ("JadeCityHard", "ShazariDesertHard"): (25857.25, 1298.4691666666668),
}

def get_spawn_coordinates(char: dict, current_level: str, target_level: str) -> tuple[float, float, bool]:
    # 1. Handle special transitions first
    if coords := SPECIAL_SPAWN_MAP.get((current_level, target_level)):
        x, y = coords
        return int(round(x)), int(round(y)), True

    # 2. Detect dungeon flag
    is_dungeon = LEVEL_CONFIG.get(target_level, (None, None, None, False))[3]
    # skip dungeon spawns except CraftTown
    if is_dungeon and target_level != "CraftTown":
        return 0, 0, False

    # 3. Default spawn point for the target level
    spawn = SPAWN_POINTS.get(target_level, {"x": 0.0, "y": 0.0})

    # 4. Use coordinates from current or previous save entries if available
    current_level_data = char.get("CurrentLevel", {})
    prev_level_data = char.get("PreviousLevel", {})

    if (target_level == current_level_data.get("name")) and "x" in current_level_data and "y" in current_level_data:
        return int(round(current_level_data["x"])), int(round(current_level_data["y"])), True
    elif prev_level_data.get("name") == target_level and "x" in prev_level_data and "y" in prev_level_data:
        return int(round(prev_level_data["x"])), int(round(prev_level_data["y"])), True

    # 5. Fallback to static spawn point
    return int(round(spawn["x"])), int(round(spawn["y"])), True

SPAWN_POINTS = {
    "CraftTown":{"x": 360, "y": 1458.99},
    "--------WOLFS END------------": "",
    "NewbieRoad": {"x": 1421.25, "y": 826.615},
    "NewbieRoadHard": {"x": 1421.25, "y": 826.615},
    "--------BLACKROSE MIRE------------": "",
    "SwampRoadNorth": {"x": 4360.5, "y": 595.615},
    "SwampRoadNorthHard": {"x": 4360.5, "y": 595.615},
    "--------FELBRIDGE------------": "",
    "BridgeTown": {"x": 3944, "y": 838.99},
    "BridgeTownHard": {"x": 3944, "y": 838.99},
    "--------CEMETERY HILL------------": "",
    "CemeteryHill": {"x": 00, "y": 00},#missing files Unknown spawn coordinates
    "CemeteryHillHard": {"x": 00, "y": 00},
    "--------STORMSHARD------------": "",
    "OldMineMountain": {"x": 189.25, "y": 1335.99},
    "OldMineMountainHard": {"x": 189.25, "y": 1335.99},
    "--------EMERALD GLADES-----------": "",
    "EmeraldGlades": {"x": -1433.75, "y": -1883.6236363636363},
    "EmeraldGladesHard": {"x": -1433.75, "y": -1883.6236363636363},
    "--------DEEPGARD CASTLE------------": "",
    "Castle": {"x": -1280, "y": -1941.01},
    "CastleHard": {"x": -1280, "y": -1941.01},
    "--------SHAZARI DESERT------------": "",
    "ShazariDesert": {"x": 618.25, "y": 647.4691666666666},
    "ShazariDesertHard": {"x": 618.25, "y": 647.4691666666666},
    "--------VALHAVEN------------": "",
    "JadeCity": {"x": 10430.5, "y": 1058.99},
    "JadeCityHard": {"x": 10430.5, "y": 1058.99},
}

DATA_DIR = "data"
def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[level_config] {os.path.basename(path)} load failed: {e}")
        return default
# --- Load base definitions ---
_raw_level_config = _load_json(os.path.join(DATA_DIR, "level_config.json"), {})
_door_list = _load_json(os.path.join(DATA_DIR, "door_map.json"), [])
DOOR_MAP = {tuple(k): v for k, v in _door_list if isinstance(k, list) and len(k) == 2}
# --- Build LEVEL_CONFIG from _raw_level_config ---
LEVEL_CONFIG = {
    name: (p[0], int(p[1]), int(p[2]), p[3].lower() == "true")
    for name, spec in _raw_level_config.items()
    if (p := spec.split()) and len(p) >= 4 and p[0]
}
#print(f"[level_config] Loaded {len(LEVEL_CONFIG)} levels, {len(DOOR_MAP)} doors")