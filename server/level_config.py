import json
import os
import struct

import missions
from BitBuffer import BitBuffer
from Character import load_characters, save_characters
from WorldEnter import build_enter_world_packet
from bitreader import BitReader
from constants import door, class_119
from globals import used_tokens, pending_world, session_by_token, token_char


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

def handle_open_door(session, data, conn):
    """
    Handle PKTTYPE_OPEN_DOOR (0x2D)
    The client requests to open a door, providing door_id (method_9).
    The server replies with a 0x2E packet pointing to the target level.
    """
    br = BitReader(data[4:])
    try:
        door_id = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] ERROR: Failed to parse 0x2D packet: {e}, raw payload={data.hex()}")
        return

    current_level = session.current_level
    print(f"[{session.addr}] OpenDoor request: doorID={door_id}, current_level={current_level}")

    is_dungeon = LEVEL_CONFIG.get(current_level, (None, None, None, False))[3]
    target_level = DOOR_MAP.get((current_level, door_id))

    # Dungeon fallback if no mapping found
    if target_level is None and is_dungeon:
        target_level = session.entry_level
        if not target_level:
            print(f"[{session.addr}] Error: No entry_level set for door {door_id} in dungeon {current_level}")
            return
    elif door_id == 999:
        target_level = "CraftTown"

    if target_level:
        if target_level not in LEVEL_CONFIG:
            print(f"[{session.addr}] Error: Target level {target_level} not found in LEVEL_CONFIG")
            return

        # Build and send DoorTarget response (0x2E)
        bb = BitBuffer()
        bb.write_method_4(door_id)
        bb.write_method_13(target_level)
        payload = bb.to_bytes()
        resp = struct.pack(">HH", 0x2E, len(payload)) + payload
        conn.sendall(resp)

        print(f"[{session.addr}] Sent DOOR_TARGET: doorID={door_id}, level='{target_level}'")

        # Reset world state for upcoming level transition
        session.world_loaded = False
        session.entities.clear()
    else:
        print(f"[{session.addr}] Error: No target for door {door_id} in level {current_level}")

def handle_level_transfer_request(session, data, conn):
    """
    Handle 0x1D: player activated a door or mission exit to change levels.
    """
    br = BitReader(data[4:])
    try:
        old_token = br.read_method_9()
        level_name = br.read_method_13()
    except Exception as e:
        print(f"[{session.addr}] ERROR: Failed to parse 0x1D packet: {e}, raw payload={data.hex()}")
        return

    # Try to resolve (char, current_level, previous_level) entry
    entry = used_tokens.get(old_token) or pending_world.get(old_token)
    if not entry:
        s = session_by_token.get(old_token)
        if s:
            entry = (
                getattr(s, "current_char_dict", None)
                or {"name": s.current_character},
                s.current_level,
            )
    if not entry:
        print(f"[{session.addr}] ERROR: No character for token {old_token}")
        return

    char, target_level = entry[:2]

    # Fallback if client didn't send level name
    if not level_name:
        level_name = target_level
        print(f"[{session.addr}] WARNING: Empty level_name, using target_level={level_name}")

    # Determine where player came from
    raw = char.get("CurrentLevel")
    if isinstance(raw, dict):
        old_level = raw.get("name", session.current_level or "NewbieRoad")
    else:
        old_level = raw or session.current_level or "NewbieRoad"

    # Clear old entity reference
    if session.clientEntID in session.entities:
        del session.entities[session.clientEntID]
        print(f"[{session.addr}] Removed entity {session.clientEntID} from level {old_level}")

    # --- user_id fix: always use session.user_id ---
    if not session.user_id:
        key = token_char.get(old_token)
        if key:
            uid, _ = key
            session.user_id = uid
            print(f"[{session.addr}] Restored user_id from token: {uid}")
        else:
            print(f"[{session.addr}] ERROR: Could not resolve user_id for token {old_token}")
            return

    session.char_list = load_characters(session.user_id)
    session.current_character = char["name"]
    session.authenticated = True

    # Save previous coordinates
    prev_rec = char.get("CurrentLevel", {})
    prev_x = prev_rec.get("x", 0.0)
    prev_y = prev_rec.get("y", 0.0)
    char["PreviousLevel"] = {"name": old_level, "x": prev_x, "y": prev_y}

    # Resolve special doors & compute spawn coords
    level_name = resolve_special_mission_doors(char, old_level, level_name)
    new_x, new_y, new_has_coord = get_spawn_coordinates(char, old_level, level_name)

    # Persist update
    for i, c in enumerate(session.char_list):
        if c["name"] == char["name"]:
            session.char_list[i] = char
            break
    else:
        session.char_list.append(char)

    save_characters(session.user_id, session.char_list)

    # Generate new transfer token
    new_token = session.ensure_token(char, target_level=level_name, previous_level=old_level)
    pending_world[new_token] = (char, level_name, old_level)

    # Build and send ENTER_WORLD
    try:
        swf_path, map_id, base_id, is_inst = LEVEL_CONFIG[level_name]
    except KeyError:
        print(f"[{session.addr}] ERROR: Level '{level_name}' not found in LEVEL_CONFIG")
        return

    old_swf, _, _, _ = LEVEL_CONFIG.get(old_level, ("", 0, 0, False))
    is_hard = level_name.endswith("Hard")
    pkt_out = build_enter_world_packet(
        transfer_token=new_token,
        old_level_id=0,
        old_swf=old_swf,
        has_old_coord=True,
        old_x=int(round(prev_x)),
        old_y=int(round(prev_y)),
        host="127.0.0.1",
        port=8080,
        new_level_swf=swf_path,
        new_map_lvl=map_id,
        new_base_lvl=base_id,
        new_internal=level_name,
        new_moment="Hard" if is_hard else "",
        new_alter="Hard" if is_hard else "",
        new_is_dungeon=is_inst,
        new_has_coord=new_has_coord,
        new_x=int(round(new_x)),
        new_y=int(round(new_y)),
        char=char,
    )
    conn.sendall(pkt_out)
    print(f"[{session.addr}] Sent ENTER_WORLD with token {new_token} for {level_name} → pos=({new_x},{new_y})")

def handle_request_door_state(session, data, conn):
    """
    Handle packet 0x41: client requests the state of a door.
    Server replies with 0x42 (door state + target).
    """

    missions.load_mission_defs()# make sure mission defs are loaded

    if len(data) < 4:
        return

    payload_length = struct.unpack(">H", data[2:4])[0]
    if len(data) != 4 + payload_length:
        return

    payload = data[4:4 + payload_length]

    try:
        br = BitReader(payload)
        door_id = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [0x41] Failed to parse door request: {e}")
        return

    door_state = door.DOORSTATE_CLOSED
    door_target = ""
    star_rating = None

    door_info = DOOR_MAP.get((session.current_level, door_id))
    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)

    if door_info and isinstance(door_info, str):
        # Determine the mission ID
        if door_info.startswith("mission:"):
            try:
                mission_id = int(door_info.split(":", 1)[1])
            except Exception:
                mission_id = None
        else:
            # Check if this static-looking door corresponds to a dungeon in mission defs
            mission_id = next(
                (m["id"] for m in missions._MISSION_DEFS_BY_ID.values() if m.get("Dungeon") == door_info),
                None
            )

        if char and mission_id is not None:
            # Get saved mission state from the character
            mission_data = char.get("missions", {}).get(str(mission_id), {})
            if mission_data.get("state") == 2:
                door_state = door.DOORSTATE_MISSIONREPEAT
                star_rating = mission_data.get("Tier", 0)
            else:
                door_state = door.DOORSTATE_MISSION
            door_target = door_info
        else:
            # Fallback if no mission or char
            door_state = door.DOORSTATE_STATIC
            door_target = door_info
    else:
        # Fallback for non-string or missing door_info
        door_state = door.DOORSTATE_STATIC
        door_target = ""

    # Build and send the reply
    bb = BitBuffer()
    bb.write_method_4(door_id)
    bb.write_method_91(door_state)
    bb.write_method_13(door_target)
    if door_state == door.DOORSTATE_MISSIONREPEAT and star_rating is not None:
        bb.write_method_6(star_rating, class_119.const_228)

    #print(f"[DEBUG] Door request: level={session.current_level}, id={door_id}, "
          #f"info={door_info}, state={door_state}, target='{door_target}'")

    payload = bb.to_bytes()
    response = struct.pack(">HH", 0x42, len(payload)) + payload

    try:
        conn.sendall(response)
        #print(f"[{session.addr}] [0x41] Door {door_id} → state={door_state}, target='{door_target}'")
    except Exception as e:
        print(f"[{session.addr}] [0x41] Failed to send door state: {e}")