import os
import struct

import missions
from BitBuffer import BitBuffer
from Character import load_characters, save_characters
from WorldEnter import build_enter_world_packet
from bitreader import BitReader
from constants import door, class_119, Entity, _load_json
from globals import send_admin_chat, handle_entity_destroy_server, all_sessions, GS


# witness the spaghetti code  down below :)

def resolve_special_mission_doors(session, char, current_level, target_level):
    missions = char.get("missions", {})

    def get_state(mid):
        m = missions.get(str(mid))
        return m.get("state", 0) if m else 0

    msg = "Cemetery Hill files are missing. You cannot enter this level."

    if target_level == "CemeteryHill":
        send_admin_chat(msg, targets=session)
        return "BridgeTown"

    if target_level == "CemeteryHillHard":
        send_admin_chat(msg, targets=session)
        return "BridgeTownHard"

    if target_level == "CraftTown":
        # Mission 5: "I claim this keep"
        if get_state(5) != 2:
            return "CraftTownTutorial"

    if current_level == "SwampRoadNorth" and target_level == "SwampRoadConnectionMission":
        if get_state(23) == 2:
            return "SwampRoadConnection"

    if current_level == "BridgeTown" and target_level == "SwampRoadConnectionMission":
        if get_state(23) == 2:
            return "SwampRoadConnection"

    if current_level == "BridgeTown" and target_level == "AC_Mission1":
        if get_state(92) == 2:
            return "Castle"

    if current_level == "BridgeTownHard" and target_level == "AC_Mission1Hard":
        if get_state(199) == 2:
            return "CastleHard"

    if current_level == "ShazariDesert" and target_level == "JC_Mission1":
        if get_state(223) == 2:
            return "JadeCity"

    if current_level == "ShazariDesertHard" and target_level == "JC_Mission1Hard":
        if get_state(199) == 2:
            return "JadeCityHard"

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

def get_spawn_coordinates(char: dict, current_level: str, target_level: str) -> tuple[int, int, bool]:
    # Special transition overrides
    coords = SPECIAL_SPAWN_MAP.get((current_level, target_level))
    if coords:
        return int(coords[0]), int(coords[1]), True

    # Dungeons -> let client use default spawn
    if is_dungeon_level(target_level):
        return 0, 0, False

    # Saved re-entry into same normal zone
    curr = char.get("CurrentLevel", {})
    if curr.get("name") == target_level and "x" in curr and "y" in curr:
        return int(curr["x"]), int(curr["y"]), True

    # Returning to previous normal zone
    prev = char.get("PreviousLevel", {})
    if prev.get("name") == target_level and "x" in prev and "y" in prev:
        return int(prev["x"]), int(prev["y"]), True

    # Static spawn for normal zones
    sp = SPAWN_POINTS.get(target_level, {"x": 0.0, "y": 0.0})
    return int(sp["x"]), int(sp["y"]), True

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

_raw_level_config = _load_json(os.path.join(DATA_DIR, "level_config.json"), {})
_door_list        = _load_json(os.path.join(DATA_DIR, "door_map.json"), [])

DOOR_MAP = {tuple(k): v for k, v in _door_list if isinstance(k, list) and len(k) == 2}

LEVEL_CONFIG = {
    name: (p[0], int(p[1]), int(p[2]), p[3].lower() == "true")
    for name, spec in _raw_level_config.items()
    if (p := spec.split()) and len(p) >= 4
}

def is_dungeon_level(level_name: str) -> bool:
    if not level_name:
        return False
    return LEVEL_CONFIG.get(level_name, ("", 0, 0, False))[3]

def is_save_allowed_level(level_name: str) -> bool:
    """
    True for normal zones + CraftTown (home)
    False for dungeons
    """
    if not level_name:
        return False
    if level_name == "CraftTown":
        return True
    return not is_dungeon_level(level_name)

def update_saved_levels_on_transfer(char: dict, old_level: str, new_level: str,new_x: float, new_y: float) -> None:
    """
    Update char["CurrentLevel"] and char["PreviousLevel"] when changing levels.

    Rules:
      - Never save dungeon levels.
      - CraftTown is a special hub:
          CurrentLevel  = CraftTown
          PreviousLevel = last non-dungeon zone
      - Normal zone:
          PreviousLevel = previous safe CurrentLevel
          CurrentLevel  = new zone
    """

    if not new_level or not is_save_allowed_level(new_level):
        # New level is a dungeon (and not CraftTown) do not change saves.
        return

    curr = char.get("CurrentLevel") or {}
    prev = char.get("PreviousLevel") or {}

    curr_name = curr.get("name")
    prev_name = prev.get("name")

    # Helper to copy a record safely
    def copy_level_rec(src: dict) -> dict:
        if not src:
            return {}
        return {
            "name": src.get("name"),
            "x": src.get("x", 0),
            "y": src.get("y", 0),
        }

    # --- CraftTown special case (home) ---
    if new_level == "CraftTown":
        # Pick the last safe zone we were "coming from"
        # Prefer CurrentLevel if it’s a safe non-CraftTown
        safe_from = None
        if curr_name and is_save_allowed_level(curr_name) and curr_name != "CraftTown":
            safe_from = curr
        elif prev_name and is_save_allowed_level(prev_name) and prev_name != "CraftTown":
            safe_from = prev

        if safe_from:
            char["PreviousLevel"] = copy_level_rec(safe_from)

        char["CurrentLevel"] = {
            "name": "CraftTown",
            "x": int(round(new_x)),
            "y": int(round(new_y)),
        }
        return

    # --- Normal overworld / town zone (non-dungeon) ---
    # Shift old safe CurrentLevel into PreviousLevel
    if curr_name and is_save_allowed_level(curr_name) and curr_name != new_level:
        char["PreviousLevel"] = copy_level_rec(curr)

    # Set new CurrentLevel
    char["CurrentLevel"] = {
        "name": new_level,
        "x": int(round(new_x)),
        "y": int(round(new_y)),
    }

def handle_open_door(session, data, conn):
    br = BitReader(data[4:])
    door_id = br.read_method_9()

    current_level = session.current_level
    #print(f"[{session.addr}] OpenDoor request: doorID={door_id}, current_level={current_level}")

    # --- Resolve base mapping ---
    target_level = DOOR_MAP.get((current_level, door_id))

    # --- Fallback: dungeon doors use entry_level if no mapping found ---
    is_dungeon = LEVEL_CONFIG.get(current_level, (None, None, None, False))[3]
    if target_level is None and is_dungeon:
        target_level = session.entry_level
        if not target_level:
            print(f"[{session.addr}] Error: No entry_level for door {door_id} in dungeon {current_level}")
            return

    # --- Special case: 999 always returns to CraftTown ---
    if door_id == 999:
        target_level = "CraftTown"

    bb = BitBuffer()
    bb.write_method_4(door_id)
    bb.write_method_13(target_level)

    payload = bb.to_bytes()
    resp = struct.pack(">HH", 0x2E, len(payload)) + payload
    conn.sendall(resp)

    #print(f"[{session.addr}] Sent DOOR_TARGET: doorID={door_id}, level='{target_level}'")


def handle_level_transfer_request(session, data, conn):
    """
    Handle 0x1D: client says "I am ready to transfer".
    We resolve the target level, save CurrentLevel/PreviousLevel for
    non-dungeon zones (with CraftTown special handling), then send ENTER_WORLD.
    """

    br = BitReader(data[4:])
    old_token = br.read_method_9()
    requested_level_name = br.read_method_13()

    # Resolve character + default target level from token tables
    entry = GS.used_tokens.get(old_token) or GS.pending_world.get(old_token)
    if not entry:
        s = GS.session_by_token.get(old_token)
        if s:
            entry = (
                getattr(s, "current_char_dict", None) or {"name": s.current_character},
                s.current_level,
            )

    if not entry:
        print(f"[{session.addr}] ERROR: No character for token {old_token}")
        return

    char, default_target_level = entry[:2]

    # Sanitize requested level: treat empty or "None" as missing
    if not requested_level_name or requested_level_name == "None":
        target_level = default_target_level
        print(
            f"[{session.addr}] ERROR: Empty/None level_name in 0x1D, "
            f"using target_level={target_level}"
        )
    else:
        target_level = requested_level_name

    # Determine old_level (where we are coming from logically)
    old_level_rec = char.get("CurrentLevel")
    if isinstance(old_level_rec, dict):
        old_level = old_level_rec.get("name") or session.current_level or "NewbieRoad"
    else:
        old_level = old_level_rec or session.current_level or "NewbieRoad"

    # Capture previous level coords *before* entity removal
    ent = session.entities.get(session.clientEntID, {})
    old_x = ent.get("pos_x")
    old_y = ent.get("pos_y")
    has_old_coord = (old_x is not None and old_y is not None)

    # Remove old player entity if present
    if session.clientEntID in session.entities:
        del session.entities[session.clientEntID]
        print(f"[{session.addr}] Removed entity {session.clientEntID} from level {old_level}")
        handle_entity_destroy_server(session, session.clientEntID, all_sessions)
    # Prepare for upcoming level transition
    session.player_spawned = False

    # Ensure we know user_id
    if not session.user_id:
        token_info = GS.token_char.get(old_token)
        if not token_info:
            print(f"[{session.addr}] ERROR: Could not resolve user_id for token {old_token}")
            return
        session.user_id = token_info[0]

    # Reload latest characters, ensure we're pointing to the right one
    session.char_list = load_characters(session.user_id)
    session.current_character = char["name"]
    session.authenticated = True

    # Resolve mission/special door overrides
    target_level = resolve_special_mission_doors(session, char, old_level, target_level)

    # Compute spawn coordinates for the NEW level (but don't spawn yet)
    new_x, new_y, new_has_coord = get_spawn_coordinates(char, old_level, target_level)

    # --- SAVE LOGIC: update CurrentLevel / PreviousLevel for non-dungeons ---
    update_saved_levels_on_transfer(
        char=char,
        old_level=old_level,
        new_level=target_level,
        new_x=new_x,
        new_y=new_y,
    )

    # Persist character list
    save_characters(session.user_id, session.char_list)

    # Create a fresh transfer token for the new world
    new_token = session.ensure_token(char, target_level=target_level, previous_level=old_level)
    GS.pending_world[new_token] = (char, target_level, old_level)

    # Build and send ENTER_WORLD packet
    if target_level not in LEVEL_CONFIG:
        print(f"[{session.addr}] ERROR: Level '{target_level}' not found in LEVEL_CONFIG")
        return

    new_swf, map_id, base_id, is_instanced = LEVEL_CONFIG[target_level]
    old_swf = LEVEL_CONFIG.get(old_level, ("", 0, 0, False))[0]

    is_hard = target_level.endswith("Hard")

    # Safely coerce old coords only if we actually have them
    if has_old_coord and isinstance(old_x, (int, float)) and isinstance(old_y, (int, float)):
        safe_old_x = int(old_x)
        safe_old_y = int(old_y)
    else:
        safe_old_x = 0
        safe_old_y = 0
        has_old_coord = False

    pkt_out = build_enter_world_packet(
        transfer_token=new_token,
        old_level_id=0,
        old_swf=old_swf,
        has_old_coord=has_old_coord,
        old_x=safe_old_x,
        old_y=safe_old_y,
        host="127.0.0.1",
        port=8080,
        new_level_swf=new_swf,
        new_map_lvl=map_id,
        new_base_lvl=base_id,
        new_internal=target_level,
        new_moment="Hard" if is_hard else "",
        new_alter="Hard" if is_hard else "",
        new_is_dungeon=is_instanced,
        new_has_coord=new_has_coord,
        new_x=int(round(new_x)),
        new_y=int(round(new_y)),
        char=char,
    )

    conn.sendall(pkt_out)
    #print(f"[{session.addr}] Sent ENTER_WORLD with token {new_token} "f"for {target_level} → pos=({new_x},{new_y})")

def send_door_state(conn, door_id, door_state, door_target, star_rating=None):
    bb = BitBuffer()
    bb.write_method_4(door_id)
    bb.write_method_91(door_state)
    bb.write_method_13(door_target or "")

    # Only mission-repeat doors send star/tier rating
    if door_state == door.DOORSTATE_MISSIONREPEAT and star_rating is not None:
        bb.write_method_6(star_rating, class_119.const_228)

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x42, len(payload)) + payload
    conn.sendall(pkt)

def handle_request_door_state(session, data, conn):
    br = BitReader(data[4:])
    door_id = br.read_method_9()

    entry = DOOR_MAP.get((session.current_level, door_id))
    char = session.current_char_dict

    #Unknown door
    if not entry:
        send_door_state(conn, door_id, door.DOORSTATE_STATIC, "")
        return

    # Default values
    door_state = door.DOORSTATE_STATIC
    door_target = ""
    star_rating = None

    # Mission door: "mission:ID"
    if isinstance(entry, str) and entry.startswith("mission:"):
        mission_id = int(entry.split(":")[1])
        m = char.get("missions", {}).get(str(mission_id), {})
        state = m.get("state", 0)

        if state == 2:  # completed
            door_state = door.DOORSTATE_MISSIONREPEAT
            star_rating = m.get("Tier", 0)
        else:
            door_state = door.DOORSTATE_MISSION

        door_target = entry

    # Level / Dungeon door
    elif isinstance(entry, str):
        target_level = entry

        if is_dungeon_level(target_level):
            min_lvl = LEVEL_CONFIG[target_level][1]
            player_lvl = char.get("level", 1)

            if player_lvl < min_lvl:
                door_state = door.DOORSTATE_LOCKED

            else:
                completed = False
                star = 0

                for mid, m in char.get("missions", {}).items():
                    mdef = missions._MISSION_DEFS_BY_ID.get(int(mid))
                    if mdef and mdef.get("Dungeon") == target_level:
                        if m.get("state") == 2:
                            completed = True
                            star = m.get("Tier", 0)
                        break

                if completed:
                    door_state = door.DOORSTATE_MISSIONREPEAT
                    star_rating = star  # send the tier here
                else:
                    door_state = door.DOORSTATE_MISSION

            door_target = target_level

        else:
            # Normal overworld door → static
            door_state = door.DOORSTATE_STATIC
            door_target = target_level

    send_door_state(conn, door_id, door_state, door_target, star_rating)


def handle_entity_incremental_update(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload)
    entity_id = br.read_method_4()
    is_self = (entity_id == session.clientEntID)

    if is_self and not session.player_spawned:
        return

    delta_x = br.read_method_45()
    delta_y = br.read_method_45()
    delta_vx = br.read_method_45()

    STATE_BITS = Entity.const_316
    ent_state = br.read_method_6(STATE_BITS)

    flags = {
        'b_left':      bool(br.read_method_15()),
        'b_running':   bool(br.read_method_15()),
        'b_jumping':   bool(br.read_method_15()),
        'b_dropping':  bool(br.read_method_15()),
        'b_backpedal': bool(br.read_method_15()),
    }

    is_airborne = bool(br.read_method_15())
    velocity_y = br.read_method_24() if is_airborne else 0

    # --- calculate new position ---
    ent = session.entities.get(entity_id)
    if not ent:
        return

    old_x = ent.get("pos_x")
    old_y = ent.get("pos_y")
    if old_x is None or old_y is None:
        return

    new_x = old_x + delta_x
    new_y = old_y + delta_y

    ent.update({
        "pos_x": new_x,
        "pos_y": new_y,
        "velocity_x": ent.get("velocity_x", 0) + delta_vx,
        "velocity_y": velocity_y,
        "ent_state": ent_state,
        **flags
    })

    session.entities[entity_id] = ent

    # Only update saved coords if player is in a non-dungeon level or CraftTown
    if is_self:
        curr_level = session.current_level
        is_dungeon = LEVEL_CONFIG.get(curr_level, ("", 0, 0, False))[3]

        if curr_level == "CraftTown" or not is_dungeon:
            # Update only coords, never PreviousLevel here
            for char in session.char_list:
                if char["name"] == session.current_character:
                    if "CurrentLevel" not in char:
                        char["CurrentLevel"] = {"name": curr_level, "x": new_x, "y": new_y}
                    else:
                        char["CurrentLevel"]["x"] = new_x
                        char["CurrentLevel"]["y"] = new_y
                    break

    for other in all_sessions:
        if other is not session and other.player_spawned and other.current_level == session.current_level:
            other.conn.sendall(data)