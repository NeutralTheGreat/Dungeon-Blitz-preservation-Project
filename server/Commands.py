import copy
import hashlib
import json, struct
import os
import pprint
import random
import secrets
import time
import missions

from Character import save_characters, build_paperdoll_packet, load_characters, get_inventory_gears, \
    build_level_gears_packet, build_login_character_list_bitpacked, load_class_template
from WorldEnter import build_enter_world_packet, Player_Data_Packet
from accounts import build_popup_packet, is_character_name_taken, _SAVES_DIR, load_accounts, get_or_create_user_id
from bitreader import BitReader
from constants import GearType, EntType, class_64, class_1, DyeType, class_118, method_277, \
    class_111, class_1_const_254, class_8, class_3, \
    get_ability_info, load_building_data, find_building_data, class_66, LinkUpdater, PowerType, Entity, Game, class_13, \
    index_to_node_id, door, class_119
from BitBuffer import BitBuffer
from constants import get_dye_color
from entity import Send_Entity_Data, load_npc_data_for_level
from globals import level_npcs, pending_world, used_tokens, session_by_token, extended_sent_map, current_characters, \
    _level_add, SECRET, build_start_skit_packet, send_premium_purchase, send_consumable_update, _send_error
from level_config import DOOR_MAP, LEVEL_CONFIG, get_spawn_coordinates, resolve_special_mission_doors
from scheduler import scheduler, _on_research_done_for, schedule_building_upgrade, _on_building_done_for, \
    schedule_forge, _on_talent_done_for, schedule_Talent_point_research
from missions import _MISSION_DEFS_BY_ID

SAVE_PATH_TEMPLATE = "saves/{user_id}.json"

#############################################

def handle_login_version(session, data, conn):
    """
    Handle PKTTYPE_LOGIN_VERSION (0x11) — client sends game version.
    Respond with PKTTYPE_LOGIN_CHALLENGE (0x12) challenge string.
    """
    try:
        br = BitReader(data[4:], debug=True)
        client_version = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [0x11] Failed to parse login version: {e}, raw={data.hex()}")
        return
    if client_version != 100:
        print(f"[{session.addr}] ⚠️ Unsupported client version: {client_version}")
    else:
        print(f"[{session.addr}] ✅ Client version OK: {client_version}")
    sid = secrets.randbelow(1 << 16)
    sid_bytes = sid.to_bytes(2, "big")
    digest = hashlib.md5(sid_bytes + SECRET).hexdigest()[:12]
    sid_hex = f"{sid:04x}"
    challenge_str = sid_hex + digest  # 16 hex characters
    session.challenge_str = challenge_str
    utf_bytes = challenge_str.encode("utf-8")
    payload = struct.pack(">H", len(utf_bytes)) + utf_bytes
    response = struct.pack(">HH", 0x12, len(payload)) + payload
    conn.sendall(response)
    print(f"[{session.addr}] → Sent 0x12 login challenge sid={sid_hex} hash={digest}")

def handle_login_create(session, data, conn):
    """
    Handle PKTTYPE_LOGIN_CREATE (0x13)
    Client sends platform IDs + email + password + legacy key.
    Server responds with PKTTYPE_LOGIN_CHARACTER_LIST (0x15).
    """
    payload = data[4:]
    try:
        br = BitReader(payload, debug=True)
        client_facebook_id = br.read_method_26()
        client_kongregate_id = br.read_method_26()
        email = br.read_method_26().strip().lower()
        password = br.read_method_26()
        legacy_auth_key = br.read_method_26()
    except Exception as e:
        print(f"[{session.addr}] [0x13] Failed to parse login-create: {e}, raw={data.hex()}")
        return
    session.user_id = get_or_create_user_id(email)
    session.authenticated = True
    session.char_list = load_characters(session.user_id)
    packet = build_login_character_list_bitpacked(session.char_list)
    conn.sendall(packet)
    print(f"[{session.addr}] [0x13] Login/Create OK for {email} → {len(session.char_list)} characters")

def handle_login_authenticate(session, data, conn):
    br = BitReader(data[4:], debug=True)
    try:
        client_facebook_id = br.read_method_26()
        client_kongregate_id = br.read_method_26()
        email = br.read_method_26().strip().lower()
        encrypted_password = br.read_method_26()
        legacy_auth_key = br.read_method_26()
    except Exception as e:
        print(f"[{session.addr}] [0x14] Error parsing packet: {e}, raw={data.hex()}")
        return
    accounts = load_accounts()
    user_id = accounts.get(email)
    if not user_id:
        conn.sendall(build_popup_packet("Account not found", disconnect=True))
        print(f"[{session.addr}] [0x14] Login failed — account not found for {email}")
        return
    session.user_id = user_id
    save_path = os.path.join(_SAVES_DIR, f"{user_id}.json")
    try:
        with open(save_path, "r", encoding="utf-8") as f:
            session.player_data = json.load(f)
    except FileNotFoundError:
        print(f"[{session.addr}] [0x14] Missing save for user {user_id}, creating blank save.")
        session.player_data = {"email": email, "characters": []}
    session.char_list = session.player_data.get("characters", [])
    session.authenticated = True
    packet = build_login_character_list_bitpacked(session.char_list)
    conn.sendall(packet)
    print(f"[{session.addr}] [0x14] Login success for {email} → user_id={user_id}, {len(session.char_list)} chars")

def handle_login_character_create(session, data, conn):
    br = BitReader(data[4:])
    try:
        name = br.read_method_26()
        class_name = br.read_method_26()
        gender = br.read_method_26()
        head = br.read_method_26()
        hair = br.read_method_26()
        mouth = br.read_method_26()
        face = br.read_method_26()
        hair_color = br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND)
        skin_color = br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND)
        shirt_color = br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND)
        pant_color = br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND)
    except Exception as e:
        print(f"[{session.addr}] [0x17] Failed to parse create-char: {e}, raw={data.hex()}")
        return

    if is_character_name_taken(name):
        conn.sendall(build_popup_packet(
            "Character name is unavailable. Please choose a new name.",
            disconnect=False))
        print(f"[{session.addr}] [0x17] Name taken: {name}")
        return

    base_template = load_class_template(class_name)
    new_char = copy.deepcopy(base_template)
    new_char.update({
        "name": name,
        "class": class_name,
        "gender": gender,
        "headSet": head,
        "hairSet": hair,
        "mouthSet": mouth,
        "faceSet": face,
        "hairColor": hair_color,
        "skinColor": skin_color,
        "shirtColor": shirt_color,
        "pantColor": pant_color,
    })
    new_char["user_id"] = session.user_id

    session.char_list.append(new_char)
    save_characters(session.user_id, session.char_list)

    current_level = new_char["CurrentLevel"]["name"]
    prev_level = new_char["PreviousLevel"]["name"]

    tk = session.ensure_token(new_char, target_level=current_level, previous_level=prev_level)
    session.clientEntID = tk
    session_by_token[tk] = session

    _level_add(current_level, session)

    level_config = LEVEL_CONFIG.get(current_level, ("LevelsNR.swf/a_Level_NewbieRoad", 1, 1, False))
    pkt_out = build_enter_world_packet(
        transfer_token=tk,
        old_level_id=0,
        old_swf="",
        has_old_coord=False,
        old_x=0,
        old_y=0,
        host="127.0.0.1",
        port=8080,
        new_level_swf=level_config[0],
        new_map_lvl=level_config[1],
        new_base_lvl=level_config[2],
        new_internal=current_level,
        new_moment="",
        new_alter="",
        new_is_dungeon=level_config[3],
        new_has_coord=False,
        new_x=0,
        new_y=0,
        char=new_char,
    )

    conn.sendall(pkt_out)
    pending_world[tk] = (new_char, current_level, prev_level)
    print(f"[{session.addr}] [0x17] Character '{name}' created → entering {current_level} (tk={tk})")

def handle_character_select(session, data, conn):
    """
    Handle PKTTYPE_LOGIN_CHARACTER_SELECT (0x16)
    The client sends the selected character name via method_26.
    The server responds by preparing level entry and sending the enter world packet.
    """
    br = BitReader(data[4:])
    try:
        name = br.read_method_26()
    except Exception as e:
        print(f"[{session.addr}] [0x16] Error reading character name: {e}, raw={data.hex()}")
        return
    for c in session.char_list:
        if c["name"] == name:
            session.current_character = name
            current_level = c.get("CurrentLevel", {}).get("name", "CraftTown")
            session.current_level = current_level
            c["user_id"] = session.user_id

            # Default previous level if missing
            prev_name = c.get("PreviousLevel", {}).get("name", "NewbieRoad")

            # Issue transfer token
            tk = session.ensure_token(c, target_level=current_level, previous_level=prev_name)
            session.clientEntID = tk
            session_by_token[tk] = session

            # Register in level
            _level_add(current_level, session)

            # Fetch level configuration
            level_config = LEVEL_CONFIG.get(current_level, ("LevelsNR.swf/a_Level_NewbieRoad", 1, 1, False))

            # Determine hard mode flags
            is_hard = current_level.endswith("Hard")
            new_moment = "Hard" if is_hard else ""
            new_alter = "Hard" if is_hard else ""

            # Build and send enter world packet
            pkt_out = build_enter_world_packet(
                transfer_token=tk,
                old_level_id=0,
                old_swf="",
                has_old_coord=False,
                old_x=0,
                old_y=0,
                host="127.0.0.1",
                port=8080,
                new_level_swf=level_config[0],
                new_map_lvl=level_config[1],
                new_base_lvl=level_config[2],
                new_internal=current_level,
                new_moment=new_moment,
                new_alter=new_alter,
                new_is_dungeon=level_config[3],
                new_has_coord=False,
                new_x=0,
                new_y=0,
                char=c,
            )
            conn.sendall(pkt_out)

            # Track pending world transfer
            pending_world[tk] = (c, current_level, prev_name)

            # Reload + save updated characters
            session.char_list = load_characters(session.user_id)
            for i, char in enumerate(session.char_list):
                if char["name"] == name:
                    session.char_list[i] = c
                    break
            save_characters(session.user_id, session.char_list)

            print(f"[{session.addr}] [0x16] Transfer begin: {name}, tk={tk}, level={current_level}")
            break

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

def handle_request_armory_gears(session, data, conn):
    payload = data
    br = BitReader(payload[4:], debug=False)
    try:
        var_2744 = br.read_method_9()
        print(f"[0xF4] Client sent var_2744={var_2744}, raw={payload.hex()}")

        if session.current_character:
            char = next((c for c in session.char_list if c["name"] == session.current_character), None)
            if char:
                gears_list = get_inventory_gears(char)
                packet = build_level_gears_packet(gears_list)
                conn.sendall(packet)
                print(f"[0xF4] Sent 0xF5 Armory gear list ({len(gears_list)} items)")
    except Exception as e:
        print(f"[0xF4] Error parsing: {e}, raw={payload.hex()}")

def handle_gameserver_login(session, data, conn):
    """
    Handle PKTTYPE_GAMESERVER_LOGIN (0x1F)
    Sent by the client after level transfer to finalize connection and spawn entities.
    """
    token = int.from_bytes(data[4:], 'big')
    # Resolve entry (used_tokens or pending_world)
    entry = used_tokens.get(token) or pending_world.get(token)
    # If entry missing, attempt to resolve by session token (support reconnects)
    if entry is None:
        if len(pending_world) == 1:
            token, entry = next(iter(pending_world.items()))
        else:
            s = session_by_token.get(token)
            if s:
                entry = (
                    getattr(s, "current_char_dict", None)
                    or {"name": s.current_character, "user_id": s.user_id},
                    s.current_level,
                )

    if not entry:
        print(f"[{session.addr}] Error: No entry found for token {token}, pending_world size={len(pending_world)}")
        return

    # entry may be (char, target_level) or (char, target_level, previous_level)
    if len(entry) == 2:
        char, target_level = entry
        previous_level = session.current_level or char.get("PreviousLevel", {}).get("name", "NewbieRoad")
    else:
        char, target_level, previous_level = entry
        if isinstance(previous_level, dict):
            previous_level = previous_level.get("name", "NewbieRoad")

    if char is None:
        print(f"[{session.addr}] Error: Character is None for token {token}")
        return

    # Dungeon entry tracking
    is_dungeon = LEVEL_CONFIG.get(target_level, (None, None, None, False))[3]
    if is_dungeon:
        session.entry_level = previous_level or char.get("PreviousLevel", "NewbieRoad")
    else:
        session.entry_level = None

    # Finalize user/session data
    session.user_id = char.get("user_id")
    if not session.user_id:
        print(f"[{session.addr}] Error: session.user_id is None for token {token}")
        return

    # Persist character data
    session.char_list = load_characters(session.user_id)
    if session.char_list:
        for i, c in enumerate(session.char_list):
            if c["name"] == char["name"]:
                session.char_list[i] = char
                break
        else:
            session.char_list.append(char)
    else:
        session.char_list = [char]
    save_characters(session.user_id, session.char_list)
    print(f"[{session.addr}] Saved character {char['name']}: "
          f"CurrentLevel={char.get('CurrentLevel')}, PreviousLevel={char.get('PreviousLevel')}")

    # Finalize transfer
    pending_world.pop(token, None)
    session.current_level = target_level
    session.current_character = char["name"]
    session.current_char_dict = char
    current_characters[session.user_id] = session.current_character
    session.authenticated = True

    # Register persistent token mapping
    used_tokens[token] = (char, target_level, session.current_level or char.get("PreviousLevel", "NewbieRoad"))

    # Compute spawn coords for Player_Data_Packet
    new_x, new_y, new_has_coord = get_spawn_coordinates(char, previous_level, target_level)

    # Send Player_Data_Packet (welcome)
    user_id = session.user_id
    send_ext = not extended_sent_map.get(user_id, {}).get("sent", False)
    welcome = Player_Data_Packet(
        char,
        transfer_token=token,
        target_level=target_level,
        new_x=int(round(new_x)),
        new_y=int(round(new_y)),
        new_has_coord=new_has_coord,
        send_extended=send_ext,
    )
    extended_sent_map[user_id] = {"sent": True, "last_seen": time.time()}
    conn.sendall(welcome)
    session.clientEntID = token
    print(f"[{session.addr}] Welcome: {char['name']} (token {token}) "
          f"on level {session.current_level}, pos=({new_x},{new_y})")

    # Spawn NPCs for the finalized level
    npcs = ensure_level_npcs(session.current_level)
    for npc in npcs.values():
        try:
            payload = Send_Entity_Data(npc)
            conn.sendall(struct.pack(">HH", 0x0F, len(payload)) + payload)
            session.entities[npc["id"]] = npc
        except Exception as e:
            print(f"[{session.addr}] Error sending NPC {npc['id']} to {session.current_level}: {e}")

    print(f"[{session.addr}] NPCs synced for level {session.current_level}")



def handle_level_transfer_request(session, data, conn):
    """
    Handle PKTTYPE_LEVEL_TRANSFER_REQUEST (0x1D)
    Sent when the player activates a door or mission exit to change levels.
    This function keeps the original logic intact but isolates it for clarity.
    """
    br = BitReader(data[4:])
    try:
        _old_token = br.read_method_9()
        level_name = br.read_method_13()
    except Exception as e:
        print(f"[{session.addr}] ERROR: Failed to parse 0x1D packet: {e}, raw payload={data.hex()}")
        return

    # Resolve character/target from token (no pop)
    entry = used_tokens.get(_old_token) or pending_world.get(_old_token)
    if not entry:
        s = session_by_token.get(_old_token)
        if s:
            entry = (
                getattr(s, "current_char_dict", None)
                or {"name": s.current_character, "user_id": s.user_id},
                s.current_level,
            )
    if not entry:
        print(f"[{session.addr}] ERROR: No character for token {_old_token}")
        return

    char, target_level = entry[:2]

    # If client sent empty level_name, use the server's target
    if not level_name:
        level_name = target_level
        print(f"[{session.addr}] WARNING: Empty level_name, using target_level={level_name}")

    # Determine where the player came from
    raw = char.get("CurrentLevel")
    if isinstance(raw, dict):
        old_level = raw.get("name", session.current_level or "NewbieRoad")
    else:
        old_level = raw or session.current_level or "NewbieRoad"

    # Clear entity from old level for this session (visual removal)
    if session.clientEntID in session.entities:
        del session.entities[session.clientEntID]
        print(f"[{session.addr}] Removed entity {session.clientEntID} from level {old_level}")

    # Ensure valid user id and load chars
    session.user_id = char.get("user_id")
    if not session.user_id:
        print(f"[{session.addr}] ERROR: char['user_id'] missing for {char['name']}")
        return
    session.char_list = load_characters(session.user_id)
    session.current_character = char["name"]
    session.authenticated = True

    # Save previous coordinates into char
    prev_rec = char.get("CurrentLevel", {})
    prev_x = prev_rec.get("x", 0.0)
    prev_y = prev_rec.get("y", 0.0)
    char["PreviousLevel"] = {"name": old_level, "x": prev_x, "y": prev_y}

    # If you have special mission door resolver, apply it BEFORE spawn coords
    level_name = resolve_special_mission_doors(char, old_level, level_name)

    # Determine spawn coords (get_spawn_coordinates may return (0,0,False))
    new_x, new_y, new_has_coord = get_spawn_coordinates(char, old_level, level_name)

    # Persist updated character
    for i, c in enumerate(session.char_list):
        if c["name"] == char["name"]:
            session.char_list[i] = char
            break
    else:
        session.char_list.append(char)
    save_characters(session.user_id, session.char_list)
    print(f"[{session.addr}] Saved character {char['name']}: "
          f"CurrentLevel={char['CurrentLevel']}, PreviousLevel={char['PreviousLevel']}")

    # Issue (or reuse) transfer token but DO NOT mark session.current_level here
    new_token = session.ensure_token(char, target_level=level_name, previous_level=old_level)
    pending_world[new_token] = (char, level_name, old_level)

    # Build ENTER_WORLD packet safely
    try:
        swf_path, map_id, base_id, is_inst = LEVEL_CONFIG[level_name]
    except KeyError:
        print(f"[{session.addr}] ERROR: Level '{level_name}' not found in LEVEL_CONFIG")
        return

    old_swf, _, _, old_is_inst = LEVEL_CONFIG.get(old_level, ("", 0, 0, False))
    old_has_coord = ("x" in prev_rec and "y" in prev_rec)
    is_hard = level_name.endswith("Hard")
    new_moment = "Hard" if is_hard else ""
    new_alter = "Hard" if is_hard else ""

    pkt_out = build_enter_world_packet(
        transfer_token=new_token,
        old_level_id=0,
        old_swf=old_swf,
        has_old_coord=old_has_coord,
        old_x=int(round(prev_x)),
        old_y=int(round(prev_y)),
        host="127.0.0.1",
        port=8080,
        new_level_swf=swf_path,
        new_map_lvl=map_id,
        new_base_lvl=base_id,
        new_internal=level_name,
        new_moment=new_moment,
        new_alter=new_alter,
        new_is_dungeon=is_inst,
        new_has_coord=new_has_coord,
        new_x=int(round(new_x)),
        new_y=int(round(new_y)),
        char=char,
    )
    conn.sendall(pkt_out)
    print(f"[{session.addr}] Sent ENTER_WORLD with token {new_token} "
          f"for level {level_name}, pos=({new_x},{new_y})")

def ensure_level_npcs(level_name):
    """
    Ensure NPCs for this level are loaded/spawned once.
    Returns the dict of NPCs for this level.
    """
    if level_name not in level_npcs:
        try:
            npcs = load_npc_data_for_level(level_name)
            npc_map = {}
            for npc in npcs:
                npc_map[npc["id"]] = npc
            level_npcs[level_name] = npc_map
            print(f"[LEVEL] Spawned {len(npc_map)} NPCs for {level_name}")
        except Exception as e:
            print(f"[LEVEL] Error loading NPCs for {level_name}: {e}")
            level_npcs[level_name] = {}
    return level_npcs[level_name]




#TODO...
def handle_talk_to_npc(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload)

    try:
        npc_id = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [PKT0x7A] Failed to parse NPC ID: {e}")
        return

    # Look up in session.entities (where NPCs are inserted on spawn)
    npc = session.entities.get(npc_id)
    if not npc:
        print(f"[{session.addr}] [PKT0x7A] Unknown NPC id={npc_id}")
        return

    npc_name = npc.get("name", f"NPC_{npc_id}")
    print(f"[{session.addr}] [PKT0x7A] Talked to NPC {npc_id} ({npc_name})")

    # Build and send the skit packet to the interacting client only
    skit_packet = build_start_skit_packet(npc_id, dialogue_id=0, mission_id=0)
    session.conn.sendall(skit_packet)

"""def handle_talk_to_npc(session, data, all_sessions):

    #Handles client packet 0x7A (talk-to-NPC request).
    #Reads the NPC ID, determines what dialogue/skit should play based on
    #current missions and NPC role, then sends the start-skit packet
    #back to the interacting client only.

    payload = data[4:]
    br = BitReader(payload)

    try:
        npc_id = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [PKT0x7A] Failed to parse NPC ID: {e}")
        return

    npc = session.entities.get(npc_id)
    if not npc:
        print(f"[{session.addr}] [PKT0x7A] Unknown NPC id={npc_id}")
        return

    npc_name = npc.get("name", f"NPC_{npc_id}")

    # Default values: generic dialogue (no mission involvement)
    dialogue_id = 0
    mission_id = 0

    # Get player's mission state
    char_data = getattr(session, "current_char_dict", None) or {}
    player_missions = char_data.get("missions", {})

    # Try to match a mission relevant to this NPC
    for mid_str, mdata in player_missions.items():
        try:
            mid = int(mid_str)
        except (ValueError, TypeError):
            continue

        mextra = get_mission_extra(mid)
        if not mextra:
            continue

        contact_name = (mextra.get("ContactName") or "").strip()
        return_name = (mextra.get("ReturnName") or "").strip()
        state = mdata.get("state", 2)

        if npc_name == contact_name:
            if state == 0:
                dialogue_id = 2  # OfferText
                mission_id = 0  # not yet acquired — do not send mission ID
            elif state == 1:
                dialogue_id = 3  # ActiveText
                mission_id = mid
            elif state == 2:
                dialogue_id = 5  # PraiseText
                mission_id = mid

        elif npc_name == return_name or state == 2:
            if state == 1:
                dialogue_id = 4
            elif state == 2:
                dialogue_id = 5
            mission_id = mid
            break
    # Build and send the start skit packet only to this client
    pkt = build_start_skit_packet(npc_id, dialogue_id, mission_id)
    session.conn.sendall(pkt)
    print(
        f"[{session.addr}] [PKT0x7A] Talked to NPC ID: {npc_id} ({npc_name}) → "
        f"sent skit (dialogue_id={dialogue_id}, mission_id={mission_id})"
    )
"""

#TODO...
def handle_collect_hatched_egg(conn, char):
      pass

REWARD_TYPES = ['gear', 'item', 'gold', 'chest', 'xp', 'potion']
GEARTYPE_BITS = GearType.GEARTYPE_BITSTOSEND  # e.g. 5

def build_loot_drop_packet(entity_id: int, x: int, y: int,
                           reward_type: str, value1: int=0, value2: int=0) -> bytes:
    """
    Packet 0x32: one bit per reward in order:
      [gear, item, gold, chest, xp, potion]
    """
    bb = BitBuffer(debug=True)

    # 1) Entity ID
    bb.write_method_4(entity_id)

    # 2) X,Y (signed)
    bb.write_signed_method_45(x)
    bb.write_signed_method_45(y)

    # 3) no-offset flag = 0
    bb.write_method_11(1, 1)

    # 4) six-type flags + payload
    for rt in REWARD_TYPES:
        bit = 1 if rt == reward_type else 0
        bb.write_method_11(bit, 1)
        if bit:
            if rt == 'gear':
                bb.write_method_6(value1, GEARTYPE_BITS)
                bb.write_method_6(value2, GEARTYPE_BITS)
            else:
                bb.write_method_4(value1)
            break

    payload = bb.to_bytes()
    header  = struct.pack('>HH', 0x32, len(payload))
    return header + payload


def handle_grant_reward(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        grantor_id    = br.read_method_9()
        target_id     = br.read_method_9()

        flag_showXP   = bool(br.read_method_15())
        xp_rate       = br.read_float()

        flag_showGold = bool(br.read_method_15())
        gold_rate     = br.read_float()

        flag_showHeal = bool(br.read_method_15())
        flag_showMana = bool(br.read_method_15())

        code_xpType   = br.read_method_9()
        code_goldType = br.read_method_9()
        code_manaType = br.read_method_9()
        code_healType = br.read_method_9()

        # **NOW** read the drop coordinates:
        drop_x = br.read_method_24()   # signed 24-bit
        drop_y = br.read_method_24()   # signed 24-bit

        has_extra     = bool(br.read_method_15())
        extra_id      = br.read_method_9() if has_extra else None

    except Exception as e:
        print("…parsing error…")
        # …
        return

    # log for sanity:
    #print(f"[PKT2A] grantor={grantor_id} target={target_id} coords=({drop_x},{drop_y}) "
          #f"XP?{flag_showXP}@{xp_rate} Gold?{flag_showGold}@{gold_rate} Extra?{extra_id}")

    # now build loot_drops using the true drop_x, drop_y:
    loot_drops = []
    if flag_showXP:
        loot_drops.append(('xp', code_xpType, int(xp_rate)))
    if flag_showGold:
        loot_drops.append(('gold', code_goldType, int(gold_rate)))
    if flag_showHeal:
        loot_drops.append(('healing', code_healType, 0))
    if flag_showMana:
        loot_drops.append(('mana', code_manaType, 0))
    if extra_id:
        # the client expects two fixed‐width values for gear:
        loot_drops.append(('gear', extra_id, extra_id))

    # broadcast one 0x32 per drop:
    for rtype, v1, v2 in loot_drops:
        pkt = build_loot_drop_packet(
            entity_id=target_id,
            x=drop_x,
            y=drop_y,
            reward_type=rtype,
            value1=v1,
            value2=v2
        )
        for other in all_sessions:
            if other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(pkt)
                #print(f"[PKT2A] → DROP {rtype} @({drop_x},{drop_y}) to {other.addr}")


def handle_change_max_speed(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    # Parse entity ID and speed modifier
    try:
        entity_id = br.read_method_4()
        speed_mod_int = br.read_method_4()
    except Exception as e:
        #print(f"[{session.addr}] [PKT0x8A] Error parsing packet: {e}")
        return

    # Find the entity
    entity = session.entities.get(entity_id)
    if not entity:
        #print(f"[{session.addr}] [PKT0x8A] Entity {entity_id} not found")
        return

    # Update the entity's behaviorSpeedMod
    entity['behaviorSpeedMod'] = speed_mod_int * LinkUpdater.VELOCITY_DEFLATE
    #print(f"[{session.addr}] [PKT0x8A] Updated entity {entity_id} behaviorSpeedMod to {entity['behaviorSpeedMod']}")

    # Build the broadcast packet
    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_4(speed_mod_int)  # Send the original integer value
    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0x8A, len(payload)) + payload

    # Broadcast to all clients in the same level
    for other_session in all_sessions:
        if other_session.world_loaded and other_session.current_level == session.current_level:
            other_session.conn.sendall(packet)


def handle_lockbox_reward(session):
    CAT_BITS = 3
    ID_BITS = 6
    PACK_ID = 1
    reward_map = {
        0: ("MountLockbox01L01", True),  # Mount
        1: ("Lockbox01L01", True),  # Pet
        # 2: ("GenericBrown", True),  # Egg
        # 3: ("CommonBrown", True),  # Egg
        # 4: ("OrdinaryBrown", True),  # Egg
        # 5: ("PlainBrown", True),  # Egg
        6: ("RarePetFood", True),  # Consumable
        7: ("PetFood", True),  # Consumable
        # 8: ("Lockbox01Gear", True),  # Gear (will crash if invalid)
        9: ("TripleFind", True),  # Charm
        10: ("DoubleFind1", True),  # Charm
        11: ("DoubleFind2", True),  # Charm
        12: ("DoubleFind3", True),  # Charm
        13: ("MajorLegendaryCatalyst", True),  # Consumable
        14: ("MajorRareCatalyst", True),  # Consumable
        15: ("MinorRareCatalyst", True),  # Consumable
        16: (None, False),  # Gold (3 000 000)
        17: (None, False),  # Gold (1 500 000)
        18: (None, False),  # Gold (750 000)
        19: ("DyePack01Legendary", True),  # Dye‐pack
    }

    idx, (name, needs_str) = random.choice(list(reward_map.items()))
    bb = BitBuffer()
    bb.write_method_6(PACK_ID, CAT_BITS)
    bb.write_method_6(idx, ID_BITS)
    bb.write_method_6(1 if needs_str else 0, 1)
    if needs_str:
        bb.write_method_13(name)

    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0x108, len(payload)) + payload
    session.conn.sendall(packet)

    print(f"Lockbox reward: idx={idx}, name={name}, needs_str={needs_str}")

def send_talent_tree_packet(session, entity_id):
    """
    Sends the talent tree for the player's current MasterClass.
    Uses the new 27-slot array structure.
    """
    mc = None
    nodes = [None] * class_118.NUM_TALENT_SLOTS

    for char in session.char_list:
        if char.get("name") == session.current_character:
            mc = char.get("MasterClass", 1)
            tree = char.get("TalentTree", {}).get(str(mc), {})
            nodes = tree.get("nodes", [None] * class_118.NUM_TALENT_SLOTS)
            break
    else:
        return  # no matching character

    session.player_data["characters"] = session.char_list

    # Build the packet
    bb = BitBuffer()
    bb.write_method_4(entity_id)

    for i, slot in enumerate(nodes):
        slot = slot or {"filled": False, "points": 0, "nodeID": i + 1}

        if slot.get("filled", False):
            bb.write_method_6(1, 1)  # has this node
            node_id = slot.get("nodeID", i + 1)
            bb.write_method_6(node_id, class_118.const_127)  # send nodeIdx (1-based)
            width = method_277(i)
            bb.write_method_6(slot["points"] - 1, width)  # points minus one
        else:
            bb.write_method_6(0, 1)  # no node present

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0xC1, len(payload)) + payload
    session.conn.sendall(pkt)
    print(f"[Reply 0xC1] TalentTree for class {mc}, total slots: {len(nodes)}")



def handle_masterclass_packet(session, raw_data):
    payload = raw_data[4:]
    br = BitReader(payload)
    entity_id       = br.read_method_4()
    master_class_id = br.read_method_6(Game.const_209)
    print(f"[MasterClass] Player {session.user_id} → classID={master_class_id}")

    for char in session.char_list:
        if char.get("name") == session.current_character:
            char["MasterClass"] = master_class_id
            break
    else:
        return

    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)

    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_6(master_class_id, Game.const_209)
    resp = struct.pack(">HH", 0xC3, len(bb.to_bytes())) + bb.to_bytes()
    session.conn.sendall(resp)
    print(f"[Reply 0xC3] entity={entity_id}, class={master_class_id}")

    send_talent_tree_packet(session, entity_id)

def handle_clear_talent_research(session, data):
    """
    Handle 0xDF: client cleared the current talent research.
    Payload: [ header(4) ] (no body)
    """
    # 1) Locate the character
    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xDF] no character found")
        return

    # 2) Cancel any pending scheduler
    tr = char.get("talentResearch", {})
    sched_id = tr.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
            print(f"[{session.addr}] [0xDF] canceled scheduled research id={sched_id}")
        except Exception as e:
            print(f"[{session.addr}] [0xDF] failed to cancel schedule: {e}")

    # 3) Clear the research state
    char["talentResearch"] = {
        "classIndex": None,
        "ReadyTime":  0,
        "done":       False,
    }

    # 4) Persist and mirror session
    save_characters(session.user_id, session.char_list)
    mem = next((c for c in session.char_list
                if c.get("name") == session.current_character), None)
    if mem:
        mem["talentResearch"] = char["talentResearch"].copy()

    print(f"[{session.addr}] [0xDF] talentResearch cleared for {session.current_character}")

def handle_gear_packet(session, raw_data):
    payload = raw_data[4:]
    br = BitReader(payload)

    entity_id  = br.read_method_4()
    prefix     = br.read_method_20(3)
    nbits      = 2 * (prefix + 1)
    slot1      = br.read_method_20(nbits)
    gear_id    = br.read_method_6(GearType.GEARTYPE_BITSTOSEND)
    slot       = slot1 - 1

    print(f"[Gear] entity={entity_id}, slot={slot}, gear={gear_id}")
    # 1) Locate and update the character in session.char_list
    for char in session.char_list:
        if char.get("name") != session.current_character:
            continue

        inv = char.setdefault("inventoryGears", [])
        eq  = char.setdefault("equippedGears", [])

        # Ensure equipped list has enough slots
        while len(eq) < 6:
            eq.append({"gearID": 0, "tier": 0, "runes": [0, 0, 0], "colors": [0, 0]})

        # 1) Try to find gear in inventory
        for item in inv:
            if item.get("gearID") == gear_id:
                gear_data = item.copy()
                break
        else:
            # fallback default if not found (client will still fail visually, but we'll keep server consistent)
            gear_data = {
                "gearID": gear_id,
                "tier": 0,
                "runes": [0, 0, 0],
                "colors": [0, 0]
            }

        # 2) Set gear in equipped slot
        eq[slot] = gear_data

        # 3) Ensure gear also exists in inventory (add if missing)
        if not any(g.get("gearID") == gear_id for g in inv):
            inv.append(gear_data.copy())  # keep dye/rune info consistent

        break
    # 2) Sync into session.player_data if still used
    session.player_data["characters"] = session.char_list

    # 3) Persist via helper
    save_characters(session.user_id, session.char_list)
    print(f"[Save] slot {slot} updated with gear {gear_id}, inventory count = {len(inv)}")



def handle_equip_rune(session, raw_data):
    payload = raw_data[4:]
    br = BitReader(payload)
    entity_id = br.read_method_4()
    gear_id    = br.read_method_6(GearType.GEARTYPE_BITSTOSEND)
    gear_tier  = br.read_method_6(GearType.const_176)
    rune_id    = br.read_method_6(class_64.const_101)
    rune_slot  = br.read_method_6(class_1.const_765)
    print(f"[Rune] entity={entity_id}, gear={gear_id}, tier={gear_tier}, rune_id={rune_id}, rune_slot={rune_slot}")

    for char in session.char_list:
        if char.get("name") != session.current_character:
            continue

        eq     = char.setdefault("equippedGears", [])
        inv    = char.setdefault("inventoryGears", [])
        charms = char.setdefault("charms", [])

        # Ensure correct slot count
        desired_slots = EntType.MAX_SLOTS - 1
        while len(eq) < desired_slots:
            eq.append({
                "gearID": 0,
                "tier": 0,
                "runes": [0, 0, 0],
                "colors": [0, 0]
            })
        if len(eq) > desired_slots:
            eq[:] = eq[:desired_slots]

        gear_found = False
        for slot in range(len(eq)):
            if eq[slot]["gearID"] == gear_id and eq[slot]["tier"] == gear_tier:
                idx = rune_slot - 1
                if 1 <= rune_slot <= 3:
                    old_rune = eq[slot]["runes"][idx]

                    if rune_id == 96:
                        # 1) Clear the rune slot
                        eq[slot]["runes"][idx] = 0

                        # 2) Return old_rune to charms
                        if old_rune and old_rune != 96:
                            for charm in charms:
                                if charm["charmID"] == old_rune:
                                    charm["count"] += 1
                                    break
                            else:
                                charms.append({"charmID": old_rune, "count": 1})

                        # 3) Decrement remover (ID 96) count
                        for charm in charms:
                            if charm["charmID"] == 96:
                                charm["count"] -= 1
                                if charm["count"] <= 0:
                                    charms.remove(charm)
                                break
                        else:
                            print("[Warning] No rune‑removers found to consume")

                    else:
                        # Equip new rune → set slot & decrement its count
                        eq[slot]["runes"][idx] = rune_id
                        for charm in charms:
                            if charm["charmID"] == rune_id:
                                charm["count"] -= 1
                                if charm["count"] <= 0:
                                    charms.remove(charm)
                                break
                        else:
                            print(f"[Warning] Equipped rune {rune_id} not in charms")

                    gear_found = True

                    # Sync inventoryGears
                    for item in inv:
                        if item["gearID"] == gear_id and item["tier"] == gear_tier:
                            item["runes"][idx] = eq[slot]["runes"][idx]
                            break
                    else:
                        inv.append(eq[slot].copy())
                break

        if not gear_found:
            print(f"[Warning] Gear {gear_id} (tier {gear_tier}) not found for {session.current_character}")
            return

        break
    else:
        print(f"[Warning] Character {session.current_character} not found")
        return

    # Save updated data
    # 2) Sync session.player_data and persist
    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)
    print(f"[Save] Rune {rune_id} applied to slot {rune_slot} for gear {gear_id} (tier {gear_tier})")

    # Echo response to client
    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)
    bb.write_method_6(gear_tier, GearType.const_176)
    bb.write_method_6(rune_id, class_64.const_101)
    bb.write_method_6(rune_slot, class_1.const_765)
    resp = struct.pack(
        ">HH", 0xB0, len(bb.to_bytes())) + bb.to_bytes()
    session.conn.sendall(resp)
    print(
        f"[Reply 0xB0] Echoed rune update: entity={entity_id}, gear={gear_id}, tier={gear_tier}, rune={rune_id}, slot={rune_slot}")

def send_look_update_packet(session, entity_id, head, hair, mouth, face, gender, hair_color, skin_color):
    """
    Send the look update packet (const_941) to a client session.

    Args:
        session: The client session object with a connection (session.conn).
        entity_id: The ID of the entity being updated (uint).
        head: Head appearance string.
        hair: Hair appearance string.
        mouth: Mouth appearance string.
        face: Face appearance string.
        gender: Gender string.
        hair_color: Hair color value (24-bit uint).
        skin_color: Skin color value (24-bit uint).
    """
    # Create a BitBuffer to build the payload
    bb = BitBuffer()

    # Write data according to the packet structure
    bb.write_method_4(entity_id)  # Entity ID (variable-length uint)
    bb.write_method_13(head)  # Head string
    bb.write_method_13(hair)  # Hair string
    bb.write_method_13(mouth)  # Mouth string
    bb.write_method_13(face)  # Face string
    bb.write_method_13(gender)  # Gender string
    bb.write_method_6(hair_color, EntType.CHAR_COLOR_BITSTOSEND)  # Shirt color (24 bits)
    bb.write_method_6(skin_color, EntType.CHAR_COLOR_BITSTOSEND)  # Pant color (24 bits)

    payload = bb.to_bytes()
    packet_type = 0x8F

    # Send packet: header (type, length) + payload
    session.conn.sendall(struct.pack(">HH", packet_type, len(payload)) + payload)

    # Optional logging for debugging
    print(f"[LookUpdate] Sent packet 0x{packet_type:02X} for entity {entity_id}")

def handle_change_look(session, raw_data, all_sessions):
    """
    Handle the look change request from the client (packet 0x8E).
    Updates live entity, saved character data, persists, and broadcasts.
    """
    # ─── (1) Parse incoming packet ────────────────────────────────────────────────
    payload = raw_data[4:]  # skip type+length
    br = BitReader(payload)

    head       = br.read_method_26()
    hair       = br.read_method_26()
    mouth      = br.read_method_26()
    face       = br.read_method_26()
    gender     = br.read_method_26()
    hair_color = br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND)
    skin_color = br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND)

    entity_id = session.clientEntID

    # ─── (2) In-memory entity update ─────────────────────────────────────────────
    if entity_id in session.entities:
        ent = session.entities[entity_id]
        ent.update({
            "headSet": head,
            "hairSet": hair,
            "mouthSet": mouth,
            "faceSet": face,
            "gender": gender,
            "hairColor": hair_color,
            "skinColor": skin_color,
        })

    # ─── (3) Update per-character saved data ────────────────────────────────────
    updated = False
    for char in session.char_list:
        if char.get("name") == session.current_character:
            char.update({
                "headSet": head,
                "hairSet": hair,
                "mouthSet": mouth,
                "faceSet": face,
                "gender": gender,
                "hairColor": hair_color,
                "skinColor": skin_color,
            })
            updated = True
            break

    if not updated:
        print(f"[Look] ERROR: character {session.current_character} not found in char_list")
        return

    # ─── (4) Persist to disk ─────────────────────────────────────────────────────
    save_characters(session.user_id, session.char_list)
    print(f"[Save] Look updated for {session.current_character}")

    # ─── (5) Send update back to requester ──────────────────────────────────────
    send_look_update_packet(
        session,
        entity_id,
        head, hair, mouth, face,
        gender, hair_color, skin_color
    )

    # ─── (6) Broadcast to nearby clients ────────────────────────────────────────
    for other in all_sessions:
        if (other is not session and
            other.world_loaded and
            other.current_level == session.current_level):
            send_look_update_packet(
                other,
                entity_id,
                head, hair, mouth, face,
                gender, hair_color, skin_color
            )



def handle_create_gearset(session, raw_data):
    """
    Packet 0xC7: client wants to create a new gear-set slot.
    Payload is a single uint: the new slot index.
    """
    payload = raw_data[4:]
    br = BitReader(payload)
    slot_idx = br.read_method_20(GearType.const_348)
    print(f"[GearSet] Creating new slot #{slot_idx} for {session.current_character}")

    # update in-memory save
    pd = session.player_data
    chars = pd.get("characters", [])
    for char in chars:
        if char.get("name") != session.current_character:
            continue
        gs = char.setdefault("gearSets", [])
        # Insert a new gearset object with name and slots
        gearset = {
            "name": f"GearSet {slot_idx + 1}",
            "slots": [0] * (EntType.MAX_SLOTS - 1)  # 6 slots
        }
        if slot_idx < len(gs):
            gs[slot_idx] = gearset
        else:
            gs.append(gearset)
        break
    else:
        print(f"[WARNING] Character not found for create_gearset")
        return

    # persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(pd, f, indent=2)
    print(f"[Save] Created gearset slot {slot_idx} in {save_path}")

    # echo back so the client will show the "Enter name" popup
    session.conn.sendall(raw_data)

def handle_name_gearset(session, raw_data):
    """
    Packet 0xC8: client sends the chosen name for a gear-set.
    Payload is (slot_idx:3 bits, name:String with 16-bit length).
    """
    payload = raw_data[4:]
    print(f"[Debug] Payload: {payload.hex()}")
    br = BitReader(payload)
    slot_idx = br.read_method_20(3)
    print(f"[Debug] slot_idx: {slot_idx}, bit_index: {br.bit_index}")
    length = br.read_method_20(16)
    print(f"[Debug] String length: {length}")
    if length > br.remaining_bits() // 8:
        print(f"[Error] Invalid string length: {length}, remaining bytes: {br.remaining_bits() // 8}")
        return
    result_bytes = bytearray()
    for _ in range(length):
        result_bytes.append(br.read_method_20(8))
    try:
        name = result_bytes.decode('utf-8')
    except UnicodeDecodeError:
        name = result_bytes.decode('latin1')
    print(f"[GearSet] Naming slot #{slot_idx} → {name} for {session.current_character}")

    # Update in-memory save
    pd = session.player_data
    chars = pd.get("characters", [])
    for char in chars:
        if char.get("name") != session.current_character:
            continue
        gs = char.setdefault("gearSets", [])
        if slot_idx < len(gs):
            gs[slot_idx]["name"] = name
        else:
            print(f"[Error] Gearset slot {slot_idx} does not exist")
            return
        break
    else:
        print(f"[WARNING] Character not found for name_gearset")
        return

    # Persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(pd, f, indent=2)
    print(f"[Save] Renamed gearset slot {slot_idx} to “{name}” in {save_path}")

    # Echo back to client
    session.conn.sendall(raw_data)

def handle_apply_gearset(session, raw_data):
    """
    Packet 0xC6: client assigns currently equipped gears to a gearset slot.
    Payload is a single uint: the gearset slot index (3 bits).
    """
    payload = raw_data[4:]
    br = BitReader(payload)
    slot_idx = br.read_method_20(GearType.const_348)
    print(f"[GearSet] Assigning equipped gears to gearset #{slot_idx} for {session.current_character}")

    # Update in-memory save
    pd = session.player_data
    chars = pd.get("characters", [])
    for char in chars:
        if char.get("name") != session.current_character:
            continue
        gs = char.get("gearSets", [])
        if slot_idx >= len(gs):
            print(f"[Error] Gearset slot {slot_idx} does not exist")
            return
        eq = char.get("equippedGears", [])
        if len(eq) != EntType.MAX_SLOTS - 1:
            print(f"[Warning] equippedGears has {len(eq)} slots, expected {EntType.MAX_SLOTS - 1}")
            return
        # Copy gear IDs from equippedGears to gearSets[slot_idx]["slots"]
        gear_ids = [item.get("gearID", 0) for item in eq]
        gs[slot_idx]["slots"] = gear_ids
        print(f"[Debug] Assigned gear IDs to gearset #{slot_idx}: {gear_ids}")
        break
    else:
        print(f"[WARNING] Character not found for apply_gearset")
        return

    # Persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(pd, f, indent=2)
    print(f"[Save] Assigned equipped gears to gearset slot {slot_idx} in {save_path}")

    # Echo back to client
    session.conn.sendall(raw_data)

def handle_update_equipment(session, raw_data):
    """
    Packet 0x30: client updates equipped gears for a gearset.
    Payload is (entity_id, followed by 6 slots: 1-bit changed flag, optional gear_id).
    """
    payload = raw_data[4:]
    print(f"[Debug] Payload: {payload.hex()}")
    br = BitReader(payload)
    entity_id = br.read_method_4()
    print(f"[Equipment] Updating for entity={entity_id}, character={session.current_character}")

    # Update in-memory save
    pd = session.player_data
    chars = pd.get("characters", [])
    for char in chars:
        if char.get("name") != session.current_character:
            continue
        eq = char.setdefault("equippedGears", [])
        inv = char.setdefault("inventoryGears", [])
        # Ensure equippedGears has 6 slots
        while len(eq) < EntType.MAX_SLOTS - 1:
            eq.append({"gearID": 0, "tier": 0, "runes": [0, 0, 0], "colors": [0, 0]})
        if len(eq) > EntType.MAX_SLOTS - 1:
            eq[:] = eq[:EntType.MAX_SLOTS - 1]
        # Process 6 slots
        updates = {}
        for slot in range(EntType.MAX_SLOTS - 1):
            if br.remaining_bits() < 1:
                print(f"[Error] Not enough bits to read slot {slot} changed flag")
                return
            changed = br.read_method_20(1)
            if changed:
                if br.remaining_bits() < GearType.GEARTYPE_BITSTOSEND:
                    print(f"[Error] Not enough bits to read gear ID for slot {slot}")
                    return
                gear_id = br.read_method_6(GearType.GEARTYPE_BITSTOSEND)
                updates[slot] = gear_id
        # Apply updates
        for slot, gear_id in updates.items():
            for item in inv:
                if item.get("gearID") == gear_id:
                    eq[slot] = item.copy()
                    break
            else:
                print(f"[Warning] Gear ID {gear_id} not found in inventory for slot {slot}")
                eq[slot] = {"gearID": 0, "tier": 0, "runes": [0, 0, 0], "colors": [0, 0]}
        print(f"[Equipment] Updated slots: {updates}")
        break
    else:
        print(f"[WARNING] Character not found for update_equipment")
        return

    # Persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(pd, f, indent=2)
    print(f"[Save] Updated equippedGears for {session.current_character} in {save_path}")

    # Echo back to client
    session.conn.sendall(raw_data)

def magic_forge_packet(session, data):
    payload = data[4:]
    br = BitReader(payload)
    idols_to_spend = br.read_method_9()
    print(f"[{session.addr}] Speed‑up request: spend {idols_to_spend} idols")

    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c.get("name") == session.current_character), None)
    if char is None:
        print(f"[{session.addr}] Character {session.current_character} not found")
        return

    mf        = char.setdefault("magicForge", {})
    available = char.get("mammothIdols", 0)

    # ONLY check hasSession (i.e. an upgrade in progress), not status==1
    if mf.get("hasSession") and available >= idols_to_spend:
        # 1) Deduct idols
        char["mammothIdols"] = available - idols_to_spend

        # 2) Cancel the scheduled completion, if any
        sched_id = mf.get("schedule_id")
        if sched_id is not None:
            try:
                scheduler.cancel(sched_id)
                print(f"[{session.addr}] Canceled scheduled forge completion (id={sched_id})")
            except Exception as e:
                print(f"[{session.addr}] Failed to cancel scheduler id={sched_id}: {e}")
        mf.pop("schedule_id", None)

        # 3) Mark forge as completed via speed‑up
        mf["status"]   = class_111.const_264  # completed via speed‑up
        mf["duration"] = 0
        mf["hasSession"] = False

        # 4) Persist save
        save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(session.player_data, f, indent=2)

        # 5) Build & send the 0xCD “forge update” response
        bb = BitBuffer()
        bb.write_method_6(mf.get("primary", 0), class_1_const_254)
        bb.write_method_91(mf.get("var_2675", 0))
        bb.write_method_91(mf.get("var_2316", 0))
        bb.write_method_11(0, 1)  # no secondary/usedlist

        resp_payload = bb.to_bytes()
        resp = struct.pack(">HH", 0xCD, len(resp_payload)) + resp_payload
        session.conn.sendall(resp)
        print(f"[{session.addr}] Sent 0xCD forge‑update (speed‑up applied)")

    else:
        print(f"[{session.addr}] Speed‑up denied: hasSession={mf.get('hasSession')}, idols={available}")

#TODO... for every collect the forge should gain level XP
def collect_forge_charm(session, data):
    """
    Handle 0xD0 "collect charm" from client:
    - Grant the player the charm they just forged (computed full ID)
    - Clear out the forge session
    - Persist save
    - Reply with an empty 0xD0 ack
    """
    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c.get("name") == session.current_character), None)
    if char is None:
        print(f"[{session.addr}] Character {session.current_character} not found")
        return

    mf = char.get("magicForge", {})
    if not mf.get("hasSession", False):
        print(f"[{session.addr}] No active forge session to collect")
        return

    # Compute full charm ID
    primary = mf.get("primary", 0)
    secondary = mf.get("secondary", 0)
    var_8 = mf.get("var_8", 0)
    charm_id = (primary & 0x1FF) | ((secondary & 0x1F) << 9) | ((var_8 & 0x3) << 14)

    if primary <= 0:
        print(f"[{session.addr}] Invalid primary ID: {primary}")
    else:
        charms = char.setdefault("charms", [])
        for entry in charms:
            if entry.get("charmID") == charm_id:
                entry["count"] = entry.get("count", 0) + 1
                break
        else:
            charms.append({"charmID": charm_id, "count": 1})
        print(f"[{session.addr}] Granted charmID={charm_id}. New charms: {char['charms']}")

    # Clear forge session
    mf.update({
        "hasSession": False,
        "primary": 0,
        "secondary": 0,
        "status": 0,
        "duration": 0,
        "var_8": 0,
        "usedlist": 0,
        "var_2675": 0,
        "var_2316": 0,
        "var_2434": False
    })

    # Save file
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)
    print(f"[{session.addr}] Forge session cleared and saved")

    # Reply with 0xD0 ACK
    resp = struct.pack(">HH", 0xD0, 0)
    session.conn.sendall(resp)
    print(f"[{session.addr}] Sent 0xD0 collect-ack")
#TODO... implement the proper system to calculate the runnes  for each craft and the timers
def start_forge_packet(session, data):
    """
    Handle 0xB1: client clicked Craft on the Magic Forge.
    Also deducts materials and consumables from the character’s save,
    updates the session.char_list, and persists the result.
    """
    payload = data[4:]
    br = BitReader(payload)

    # 1) Read primary gem ID
    primary = br.read_method_20(class_1_const_254)
    print(f"[{session.addr}] Forge start: primary gemID={primary}")

    # 2) Read materials list
    materials_used = {}
    while br.read_method_15():  # method_15(true)
        mat_id = br.read_method_20(class_8.const_658)
        count = br.read_method_20(class_8.const_731)
        materials_used[mat_id] = count
    print(f"[{session.addr}] Forge materials: {materials_used}")

    # 3) Read consumable flags (4 total)
    consumable_flags = [br.read_method_15() for _ in range(4)]
    print(f"[{session.addr}] Forge consumables flags: {consumable_flags}")

    # 4) Locate the character dict in session.char_list
    char = next((c for c in session.char_list
                 if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] ERROR: character not found for forge start")
        return

    # 5) Deduct materials
    mats = char.setdefault("materials", [])
    for mat_id, used in materials_used.items():
        for entry in mats:
            if entry["materialID"] == mat_id:
                entry["count"] = max(0, entry["count"] - used)
                break
        else:
            mats.append({"materialID": mat_id, "count": 0})

    # 6) Deduct consumables
    consumable_ids = [
        class_3.var_1415,
        class_3.var_2082,
        class_3.var_1374,
        class_3.var_1462
    ]
    cons = char.setdefault("consumables", [])
    for flag, cid in zip(consumable_flags, consumable_ids):
        if flag:
            for entry in cons:
                if entry["consumableID"] == cid:
                    entry["count"] = max(0, entry["count"] - 1)
                    break
            else:
                cons.append({"consumableID": cid, "count": 0})

    # 7) Decide if the result has a secondary buff
    import random, time
    has_secondary = random.random() < 0.25  # 25%
    secondary    = random.randint(1, 9) if has_secondary else 0
    var_8        = 1 if has_secondary else 0

    # 8) Start the forge session on the character
    mf = char.setdefault("magicForge", {})
    mf.update({
        "hasSession": True,
        "primary": primary,
        "secondary": secondary,
        "status": class_111.const_286,  # in-progress
        "duration": 60000,              # ms
        "_start_time": time.time(),     # timestamp
        "var_8": var_8,
        "usedlist": 0,
        "var_2675": 0,
        "var_2316": 0,
        "var_2434": True
    })

    # 9) Sync and persist initial in‑progress state
    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)
    print(f"[{session.addr}] Forge session started and saved")

    # 10) Schedule completion callback
    now = int(time.time())
    # duration is in ms
    run_at = now + (mf["duration"] // 1000)
    schedule_forge(session.user_id,
                   session.current_character,
                   run_at,
                   primary,
                   secondary)
    print(f"[{session.addr}] Forge completion scheduled at {run_at}")


def cancel_forge_packet(session, data):
    """
    Handle 0xE1: client clicked Cancel on the Magic Forge.
    Clears the session so the UI resets.
    """
    print(f"[{session.addr}] Cancel‑forge request received")

    # 1) Find the character in the save
    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c["name"] == session.current_character), None)
    if char is None:
        print(f"[{session.addr}] ERROR: character not found for cancel forge")
        return

    # 2) Clear the forge session (no gem, no secondary, no timer)
    mf = char.setdefault("magicForge", {})
    mf["hasSession"] = False
    mf["status"]     = 0
    mf["duration"]   = 0
    mf["primary"]    = 0
    mf["secondary"]  = 0
    mf["var_8"]      = 0
    mf["usedlist"]   = 0
    mf["var_2675"]   = 0
    mf["var_2316"]   = 0
    mf["var_2434"]   = False

    # 3) Persist the change
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)
    print(f"[{session.addr}] Forge session canceled and save updated")

def allocate_talent_points(session, data):
    """
    Handle 0xD3: client sent new craftTalentPoints.
    Packet payload is one method_9-packed integer containing
    five 4-bit values: [p0, p1, p2, p3, p4].
    """
    payload = data[4:]
    br = BitReader(payload)
    packed = br.read_method_9()
    # Unpack five 4‑bit fields: index i at bits (i*4 .. i*4+3)
    points = [(packed >> (i * 4)) & 0xF for i in range(5)]
    print(f"[{session.addr}] Allocate talent points: {points}")

    # Update save
    chars = session.player_data.setdefault("characters", [])
    char = next((c for c in chars if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] ERROR: character not found for talent allocation")
        return

    char["craftTalentPoints"] = points

    # Persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)
    print(f"[{session.addr}] Saved new craftTalentPoints for {char['name']}")

def use_forge_xp_consumable(session, data):
    """
    Handle 0x110: player used a forge‑XP consumable.
    Deduct one consumable and award forge XP (capped at 159,948).
    """
    payload = data[4:]
    br = BitReader(payload)

    # Read consumableID
    cid = br.read_method_20(class_3.const_69)
    print(f"[{session.addr}] Forge XP consumable used: consumableID={cid}")

    # Get character
    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] ERROR: character not found")
        return

    # Deduct from inventory
    cons = char.setdefault("consumables", [])
    for entry in cons:
        if entry["consumableID"] == cid:
            entry["count"] = max(0, entry["count"] - 1)
            break
    else:
        print(f"[{session.addr}] Warning: consumable {cid} not in inventory")

    # Award XP (capped)
    xp_gain = 4000
    current_xp = char.get("craftXP", 0)
    max_xp = 159_948
    new_xp = min(current_xp + xp_gain, max_xp)
    char["craftXP"] = new_xp

    print(f"[{session.addr}] Forge XP +{xp_gain} (capped), total now = {char['craftXP']}")

    # Save file
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)
    print(f"[{session.addr}] Save updated with capped forge XP")

def handle_private_message(session, data, all_sessions):
    payload = data[4:]
    try:
        br = BitReader(payload)
        recipient_name = br.read_method_13()
        message = br.read_method_13()
        print(f"[{session.addr}] [PKT46] Private message from {session.current_character} to {recipient_name}: {message}")

        # Find recipient session
        recipient_session = next(
            (s for s in all_sessions
             if s.current_character
             and s.current_character.lower() == recipient_name.lower()
             and s.authenticated),
            None
        )

        # For recipient (0x47): senderName + message
        bb_recipient = BitBuffer()
        bb_recipient.write_method_13(session.current_character)  # Sender's name
        bb_recipient.write_method_13(message)
        payload_out_recipient = bb_recipient.to_bytes()
        pkt_recipient = struct.pack(">HH", 0x47, len(payload_out_recipient)) + payload_out_recipient

        # For sender (0x48): recipientName + message
        bb_sender = BitBuffer()
        bb_sender.write_method_13(recipient_name)  # Recipient's name
        bb_sender.write_method_13(message)
        payload_out_sender = bb_sender.to_bytes()
        pkt_sender = struct.pack(">HH", 0x48, len(payload_out_sender)) + payload_out_sender

        if recipient_session:
            # Send to recipient
            recipient_session.conn.sendall(pkt_recipient)
            print(
                f"[{session.addr}] [PKT47] Sent private message to {recipient_session.addr} ({recipient_session.current_character})")

            # Send confirmation to sender
            session.conn.sendall(pkt_sender)
            print(
                f"[{session.addr}] [PKT48] Sent private message confirmation to sender {session.addr} ({session.current_character})")

        else:
            print(f"[{session.addr}] [PKT46] Recipient {recipient_name} not found")
            err = f"Player {recipient_name} not found".encode("utf-8")
            pl = struct.pack(">H", len(err)) + err
            session.conn.sendall(struct.pack(">HH", 0x44, len(pl)) + pl)

    except Exception as e:
        print(f"[{session.addr}] [PKT46] Parse error: {e}, raw payload = {payload.hex()}")




def Client_Crash_Reports(session, data):
    """
    Read a CLIENT ERROR (0x7C) packet and log it.
    No response is sent back.
    """
    # unpack the two‐byte packet ID and two‐byte length
    _, length = struct.unpack_from(">HH", data, 0)
    # extract exactly `length` bytes of payload
    payload = data[4:4 + length]
    try:
        msg = payload.decode("utf-8", errors="replace")
    except Exception:
        msg = repr(payload)
    print(f"[{session.addr}] CLIENT ERROR (0x7C): {msg}")


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



def Start_Skill_Research(session, data, conn):
    br = BitReader(data[4:], debug=True)
    try:
        ability_id = br.read_method_20(7)
        rank       = br.read_method_20(4)
        used_idols = bool(br.read_method_15())

        print(f"[{session.addr}] [0xBE] Skill upgrade request: "
              f"abilityID={ability_id}, rank={rank}, idols={used_idols}")

        char = next((c for c in session.char_list
                     if c.get("name") == session.current_character), None)
        if not char:
            return

        # --- Lookup by ID + Rank ---
        ability_data = get_ability_info(ability_id, rank)
        if not ability_data:
            print(f"[{session.addr}] [0xBE] Invalid ability/rank ({ability_id}, {rank})")
            return

        gold_cost    = int(ability_data["GoldCost"])
        idol_cost    = int(ability_data["IdolCost"])
        upgrade_time = int(ability_data["UpgradeTime"])

        # --- Deduct currency ---
        if used_idols:
            char["mammothIdols"] = char.get("mammothIdols", 0) - idol_cost
            send_premium_purchase(session, "SkillResearch", idol_cost)
            print(f"[{session.addr}] Deducted {idol_cost} idols for skill upgrade")
        else:
            char["gold"] = char.get("gold", 0) - gold_cost
            print(f"[{session.addr}] Deducted {gold_cost} gold for skill upgrade")

        # --- Save research state ---
        ready_ts = int(time.time()) + upgrade_time
        sched_id = scheduler.schedule(
            run_at=ready_ts,
            callback=lambda uid=session.user_id, cname=char["name"]:
                _on_research_done_for(uid, cname)
        )

        char["SkillResearch"] = {
            "abilityID": ability_id,
            "ReadyTime": ready_ts,
            "done": False,
        }
        save_characters(session.user_id, session.char_list)

        print(f"[{session.addr}] [0xBE] Research scheduled: ready at {ready_ts}, id={sched_id}")

    except Exception as e:
        print(f"[{session.addr}] [0xBE] Error: {e}")


def handle_research_claim(session):
    """
    Handle packet 0xD1: player claims completed skill research.
    """
    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] No character found to complete research")
        return

    research = char.get("SkillResearch")
    if not research or not research.get("done"):
        print(f"[{session.addr}] No completed research to claim")
        return

    ability_id = research["abilityID"]

    # Find or add ability
    learned = char.setdefault("learnedAbilities", [])
    for ab in learned:
        if ab["abilityID"] == ability_id:
            ab["rank"] += 1
            break
    else:
        learned.append({"abilityID": ability_id, "rank": 1})

    print(f"[{session.addr}] Claimed research: abilityID={ability_id}")

    char["SkillResearch"] = {
        "abilityID": 0,
        "ReadyTime": 0,
        "done": True
    }

    save_characters(session.user_id, session.char_list)

def Skill_Research_Cancell_Request(session):
    """
    Handle 0xDD: cancel skill research.
    Clears research state and cancels any pending scheduler.
    """
    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xDD] Cannot cancel research: no character found")
        return

    research = char.get("SkillResearch")
    if not research or research.get("done"):
        print(f"[{session.addr}] [0xDD] No active research to cancel")
        return

    ability_id = research.get("abilityID")

    # Cancel any scheduled completion task
    sched_id = research.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
            print(f"[{session.addr}] [0xDD] Cancelled scheduled research id={sched_id}")
        except Exception as e:
            print(f"[{session.addr}] [0xDD] Failed to cancel scheduler: {e}")

    # Clear research state
    char["SkillResearch"] = {
        "abilityID": 0,
        "ReadyTime": 0,
        "done": True
    }

    save_characters(session.user_id, session.char_list)
    print(f"[{session.addr}] [0xDD] Research cancelled for abilityID={ability_id}")



def Skill_SpeedUp(session, data):
    """
    Handles skill research speed-up request (0xDE).
    Deducts idols, completes research immediately,
    and sends 0xBF + idol update (0xB5).
    """
    br = BitReader(data[4:])
    idol_cost = br.read_method_9()

    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xDE] Cannot speed up: no character found")
        return

    research = char.get("SkillResearch")
    if not research or research.get("done"):
        print(f"[{session.addr}] [0xDE] No active research to speed up")
        return

    if idol_cost > 0:
        char["mammothIdols"] = char.get("mammothIdols", 0) - idol_cost
        send_premium_purchase(session, "SkillSpeedup", idol_cost)
        print(f"[{session.addr}] [0xDE] Deducted {idol_cost} idols for skill speed-up")

    # Complete instantly
    research["ReadyTime"] = 0
    research["done"] = True
    save_characters(session.user_id, session.char_list)

    # Mirror in-memory
    mem_char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if mem_char:
        mem_char["mammothIdols"] = char["mammothIdols"]
        mem_char["SkillResearch"] = research.copy()

    # Send completion packet 0xBF
    try:
        bb = BitBuffer()
        bb.write_method_6(research["abilityID"], 7)
        payload = bb.to_bytes()
        session.conn.sendall(struct.pack(">HH", 0xBF, len(payload)) + payload)
        print(f"[{session.addr}] [0xDE] Sent 0xBF complete for abilityID={research['abilityID']}")
    except Exception as e:
        print(f"[{session.addr}] [0xDE] Failed to send 0xBF: {e}")



def handle_building_upgrade(session, data):
    """
    Handle 0xD7: client requested a building upgrade.
    Payload = [ header(4) | buildingID(5) | rank(5) | isInstant(1) ]
    """
    load_building_data()

    try:
        # --- 1) Parse incoming packet ---
        payload = data[4:]
        br = BitReader(payload, debug=True)

        building_id = br.read_method_20(5)
        client_rank = br.read_method_20(5)
        used_idols  = bool(br.read_method_15())  # client flag, we just treat as "paid with idols"

        print(f"[{session.addr}] [0xD7] Upgrade request: "
              f"buildingID={building_id}, rank={client_rank}, idols={used_idols}")

        # --- 2) Locate character ---
        char = next(c for c in session.char_list
                    if c["name"] == session.current_character)

        mf = char.setdefault("magicForge", {})
        stats_dict = mf.setdefault("stats_by_building", {})
        current_rank = stats_dict.get(str(building_id), 0)

        # Sanity: requested rank must be exactly +1
        if client_rank != current_rank + 1:
            print(f"[{session.addr}] [0xD7] invalid rank upgrade "
                  f"(current={current_rank}, requested={client_rank})")
            return

        # --- 3) Look up building data ---
        bdata        = find_building_data(building_id, client_rank)
        gold_cost    = int(bdata["GoldCost"])
        idol_cost    = int(bdata.get("IdolCost", 0))
        upgrade_time = int(bdata["UpgradeTime"])

        # --- 4) Handle currency ---
        if used_idols:
            if char.get("mammothIdols", 0) < idol_cost:
                print(f"[{session.addr}] [0xD7] not enough idols "
                      f"({char.get('mammothIdols')} < {idol_cost})")
                return
            char["mammothIdols"] -= idol_cost
            send_premium_purchase(session, "BuildingUpgrade", idol_cost)
            print(f"[{session.addr}] Deducted {idol_cost} idols for upgrade")
        else:
            if char.get("gold", 0) < gold_cost:
                print(f"[{session.addr}] [0xD7] not enough gold "
                      f"({char.get('gold')} < {gold_cost})")
                return
            char["gold"] -= gold_cost
            print(f"[{session.addr}] Deducted {gold_cost} gold for upgrade")

        # --- 5) Compute finish time ---
        now = int(time.time())
        ready_time = now + upgrade_time

        # --- 6) Persist pending upgrade ---
        char["buildingUpgrade"] = {
            "buildingID": building_id,
            "rank": client_rank,
            "ReadyTime": ready_time,
            "done": False
        }
        save_characters(session.user_id, session.char_list)

        # --- 7) Schedule completion ---
        schedule_building_upgrade(
            session.user_id,
            session.current_character,
            ready_time
        )

    except Exception as e:
        print(f"[{session.addr}] [0xD7] Error: {e}")



def handle_speedup_request(session, data):
    """
    Handle 0xDC: client clicked 'Speed-up' for building upgrade.
    Payload: [header(4) | idolCost(method_9)].
    """
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        idol_cost = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [0xDC] parse error: {e}")
        return

    print(f"[{session.addr}] [0xDC] Speed-up requested: cost={idol_cost}")

    # --- Locate character ---
    char = next((c for c in session.char_list
                 if c["name"] == session.current_character), None)
    if not char:
        return

    # --- Deduct idols and notify client ---
    if idol_cost > 0:
        char["mammothIdols"] = char.get("mammothIdols", 0) - idol_cost
        send_premium_purchase(session, "BuildingSpeedup", idol_cost)
        print(f"[{session.addr}] Deducted {idol_cost} idols for speed-up")

    # --- Grab pending upgrade ---
    bu = char.get("buildingUpgrade", {})
    building_id = bu.get("buildingID")
    new_rank    = bu.get("rank")
    if not building_id or new_rank is None:
        print(f"[{session.addr}] [0xDC] no active building upgrade")
        save_characters(session.user_id, session.char_list)
        return

    # --- Cancel scheduler (if any) ---
    bu.pop("schedule_id", None)  # we don’t track IDs, just clean
    # (scheduled task will auto-skip if buildingID==0)

    # --- Apply upgrade immediately ---
    stats_dict = char.setdefault("magicForge", {}).setdefault("stats_by_building", {})
    stats_dict[str(building_id)] = new_rank

    # --- Clear pending upgrade ---
    char["buildingUpgrade"] = {
        "buildingID": 0,
        "rank": 0,
        "ReadyTime": 0,
        "done": False,
    }

    save_characters(session.user_id, session.char_list)

    # --- Mirror in session ---
    mem_char = next((c for c in session.char_list
                     if c.get("name") == session.current_character), None)
    if mem_char:
        mem_char["mammothIdols"] = char["mammothIdols"]
        mem_char.setdefault("magicForge", {})["stats_by_building"] = stats_dict.copy()
        mem_char["buildingUpgrade"] = char["buildingUpgrade"].copy()

    # --- Notify client (0xD8) ---
    try:
        bb = BitBuffer()
        bb.write_method_6(building_id, 5)   # class_9.const_129
        bb.write_method_6(new_rank, 5)      # class_9.const_28
        bb.write_method_15(True)            # complete flag
        payload = bb.to_bytes()
        session.conn.sendall(struct.pack(">HH", 0xD8, len(payload)) + payload)
        print(f"[{session.addr}] [0xDC] completed upgrade ID={building_id}, rank={new_rank}")
    except Exception as e:
        print(f"[{session.addr}] [0xDC] failed to send 0xD8: {e}")




def handle_cancel_upgrade(session, data):
    """
    Handle 0xDB: client canceled an ongoing building upgrade.
    Just clears buildingUpgrade; scheduled task will auto-skip.
    """
    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        return

    bu = char.get("buildingUpgrade", {})
    building_id = bu.get("buildingID", 0)

    # Reset upgrade state (cancel)
    char["buildingUpgrade"] = {
        "buildingID": 0,
        "rank": 0,
        "ReadyTime": 0,
        "done": False,
    }
    save_characters(session.user_id, session.char_list)

    print(f"[{session.addr}] [0xDB] building upgrade canceled for buildingID={building_id}")

    mem = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if mem:
        mem["buildingUpgrade"] = char["buildingUpgrade"].copy()




def handle_building_claim(session, data):
    """
    Handle 0xD9: client acknowledged a completed building upgrade.
    Usually sent after 0xD8 completion has been processed.
    """
    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xD9] no character found")
        return

    bu = char.get("buildingUpgrade", {})
    building_id = bu.get("buildingID", 0)
    rank        = bu.get("rank", 0)

    # Clear upgrade state just in case it wasn’t cleared already
    char["buildingUpgrade"] = {
        "buildingID": 0,
        "rank": 0,
        "ReadyTime": 0,
        "done": False,
    }
    save_characters(session.user_id, session.char_list)

    # Mirror to in-memory session
    mem = next((c for c in session.char_list
                if c.get("name") == session.current_character), None)
    if mem:
        mem["buildingUpgrade"] = char["buildingUpgrade"].copy()

    print(f"[{session.addr}] [0xD9] building upgrade claim ack "
          f"(buildingID={building_id}, rank={rank})")



def handle_train_talent_point(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        class_index = br.read_method_20(2)
        # client doesn’t actually send an instant flag — discard
        br.read_method_15()
    except Exception as e:
        print(f"[{session.addr}] [PKT0xD4] parse error: {e}")
        return

    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        return

    pts = char.setdefault("talentPoints", {})
    current_points = pts.get(str(class_index), 0)

    # Duration and costs
    duration_idx = current_points + 1
    duration = class_66.RESEARCH_DURATIONS[duration_idx]
    gold_cost = class_66.RESEARCH_COSTS[duration_idx]
    idol_cost = class_66.IDOL_COST[duration_idx]

    now = int(time.time())

    if char.get("gold", 0) >= gold_cost:
        # Gold path = timed research
        char["gold"] -= gold_cost
        ready_ts = now + duration
        char["talentResearch"] = {
            "classIndex": class_index,
            "ReadyTime": ready_ts,
            "done": False
        }
        print(f"[{session.addr}] Deducted {gold_cost} gold for research → ready in {duration}s")
        save_characters(session.user_id, session.char_list)
        schedule_Talent_point_research(session.user_id, session.current_character, ready_ts)

    else:
        # Idol path = instant research
        if char.get("mammothIdols", 0) < idol_cost:
            print(f"[{session.addr}] Insufficient idols: {char.get('mammothIdols')} < {idol_cost}")
            return
        char["mammothIdols"] -= idol_cost
        char["talentResearch"] = {
            "classIndex": class_index,
            "ReadyTime": now,  # instant
            "done": False
        }
        print(f"[{session.addr}] Deducted {idol_cost} idols for instant research")
        save_characters(session.user_id, session.char_list)
        send_premium_purchase(session, "TalentResearch", idol_cost)
        _on_talent_done_for(session.user_id, session.current_character)



def handle_talent_speedup(session, data):
    """
    Handle 0xE0: client clicked Speed-up on talent research.
    Client sends the idol cost (0 if free).
    """
    # 1) Parse idol cost
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        idol_cost = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [0xE0] parse error: {e}")
        return

    print(f"[{session.addr}] [0xE0] Talent speed-up requested: cost={idol_cost}")

    # 2) Locate character
    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xE0] no character found")
        return

    tr = char.get("talentResearch", {})
    class_idx = tr.get("classIndex")

    # 3) Deduct idols if cost > 0
    if idol_cost > 0:
        char["mammothIdols"] = char.get("mammothIdols", 0) - idol_cost
        send_premium_purchase(session, "TalentSpeedup", idol_cost)
        print(f"[{session.addr}] [0xE0] Deducted {idol_cost} idols")

    # 4) Cancel scheduler if one exists
    sched_id = tr.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
            print(f"[{session.addr}] canceled scheduled research id={sched_id}")
        except Exception:
            pass

    # 5) Mark research complete immediately
    tr["ReadyTime"] = 0
    tr["done"] = True
    char["talentResearch"] = tr

    # 6) Persist & mirror in memory
    save_characters(session.user_id, session.char_list)
    mem = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if mem:
        mem["mammothIdols"] = char["mammothIdols"]
        mem["talentResearch"] = tr.copy()

    # 7) Send the 0xD5 “complete” notification
    try:
        bb = BitBuffer()
        bb.write_method_6(class_idx, class_66.const_571)  # classIndex
        bb.write_method_6(1, 1)                           # status=complete
        payload = bb.to_bytes()
        session.conn.sendall(struct.pack(">HH", 0xD5, len(payload)) + payload)
        print(f"[{session.addr}] [0xE0] sent 0xD5 to mark research complete")
    except Exception as e:
        print(f"[{session.addr}] [0xE0] failed to send 0xD5: {e}")




def handle_talent_claim(session, data):
    """
    Handle 0xD6: client claiming a completed talent research.
    Client sends this with an empty payload after upgrading is done.
    Server should persist the talent point and clear talentResearch.
    """
    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xD6] no character found")
        return

    tr = char.get("talentResearch", {})
    class_idx = tr.get("classIndex")

    # Award the point (server-side persistence)
    pts = char.setdefault("talentPoints", {})
    pts[str(class_idx)] = pts.get(str(class_idx), 0) + 1

    # Clear research state
    char["talentResearch"] = {
        "classIndex": None,
        "ReadyTime": 0,
        "done": False,
    }

    # Persist save
    save_characters(session.user_id, session.char_list)

    # Mirror to in-memory session
    mem_char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if mem_char:
        mem_char.setdefault("talentPoints", {})[str(class_idx)] = pts[str(class_idx)]
        mem_char["talentResearch"] = char["talentResearch"].copy()

    print(f"[{session.addr}] [0xD6] Awarded talent point for classIndex={class_idx}")



def handle_hp_increase_notice(session, data):
       pass

def handle_char_regen(session, data):
      pass


def handle_volume_enter(session, data):
     pass

def handle_change_offset_y(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        ent_id = br.read_method_9()
        offset_y = br.read_method_706()

        print(f"[PKT125] ent_id={ent_id}, offset_y={offset_y}")

        entity = session.get_entity(ent_id)
        if entity:
            entity.target_offset_y = offset_y
        else:
            print(f"[PKT125] Unknown entity ID: {ent_id}")

    except Exception as e:
        print(f"[{session.addr}] [PKT125] Error parsing packet: {e}")

def handle_request_respawn(session, data, all_sessions):
    br = BitReader(data[4:], debug=False)
    try:
        use_potion = bool(br.read_method_15())
    except:
        return

    # 3) Deduct a potion server-side and update client inventory
    if use_potion:
        for char in session.char_list:
            if char['name'] == session.current_character:
                for item in char.get('consumables', []):
                    if item.get('consumableID') == 9:
                        if item['count'] > 0:
                            item['count'] -= 1
                            new_count = item['count']
                            print(f"[{session.addr}] [PKT77] Used potion, new count={new_count}")
                            # 3a) Persist save
                            save_characters(session.user_id, session.char_list)
                            # 3b) Inform client of new count
                            send_consumable_update(session.conn, 9, new_count)
                        # if count was zero, we silently proceed (client will handle empty)
                        break
                break

    # 4) Send RESPAWN_COMPLETE (0x80)
    #TODO....
    # compute actual spawn location
    spawn_pos = 0
    bb = BitBuffer()
    bb.write_signed_method_45(spawn_pos)
    bb.write_method_11(1 if use_potion else 0, 1)
    body = bb.to_bytes()
    session.conn.sendall(struct.pack(">HH", 0x80, len(body)) + body)

    # 5) Immediately restore health via CHAR_REGEN (0x78)
    heal_amount = 10000
    bb2 = BitBuffer()
    bb2.write_method_9(session.clientEntID or 0)
    bb2.write_method_24(heal_amount)
    body2 = bb2.to_bytes()
    session.conn.sendall(struct.pack(">HH", 0x78, len(body2)) + body2)

    print(f"[{session.addr}] [PKT77] Respawned at {spawn_pos}, potion_used={use_potion}")




#handled
#############################################



def handle_apply_dyes(session, payload, all_sessions):
    br = BitReader(payload)
    try:
        entity_id = br.read_method_4()
        dyes_by_slot = {}
        for slot in range(1, EntType.MAX_SLOTS):
            if br.read_method_20(1):
                d1 = br.read_method_20(DyeType.BITS)
                d2 = br.read_method_20(DyeType.BITS)
                dyes_by_slot[slot - 1] = (d1, d2)

        pay_with_idols = bool(br.read_method_20(1))

        primary_dye = br.read_method_20(DyeType.BITS) if br.read_method_20(1) else None
        secondary_dye = br.read_method_20(DyeType.BITS) if br.read_method_20(1) else None
    except Exception as e:
        print(f"[Dyes] ERROR parsing dye packet: {e}")
        return

    print(f"[Dyes] entity={entity_id}, dyes_by_slot={dyes_by_slot}, "
          f"pay_with_idols={pay_with_idols}, shirt={primary_dye}, pants={secondary_dye}")

    # ─── Work directly with the current character ───
    char = session.current_char_dict
    if not char:
        print(f"[Dyes] ERROR: current_char_dict is None for {session.addr}")
        return

    eq = char.setdefault("equippedGears", [])
    inv = char.setdefault("inventoryGears", [])

    # Cost tables
    level = int(char.get("level", char.get("mExpLevel", 1)) or 1)
    g_idx = min(max(level, 0), len(Entity.Dye_Gold_Cost) - 1)
    i_idx = min(max(level, 0), len(Entity.Dye_Idols_Cost) - 1)
    per_gold = Entity.Dye_Gold_Cost[g_idx]
    per_idol = Entity.Dye_Idols_Cost[i_idx]

    # Detect gear dye changes
    current_dyes_by_slot = {idx: tuple(gear.get("colors", [0, 0])) for idx, gear in enumerate(eq)}

    slots_changed = 0
    individual_dyes_changed = 0
    for slot, (new_d1, new_d2) in dyes_by_slot.items():
        if slot >= len(eq):
            continue
        gear = eq[slot]
        if not gear or gear.get("gearID", 0) == 0:
            continue
        old_d1, old_d2 = current_dyes_by_slot.get(slot, (0, 0))
        changed = 0
        if new_d1 != old_d1:
            individual_dyes_changed += 1
            changed = 1
        if new_d2 != old_d2:
            individual_dyes_changed += 1
            changed = 1
        slots_changed += changed

    charge_units = individual_dyes_changed
    gold_cost = per_gold * charge_units
    idol_cost = per_idol * charge_units

    print(f"[Dyes] Level={level}, per-dye={per_gold}g/{per_idol}i  units={charge_units}  "
          f"total_gold={gold_cost}  total_idols={idol_cost}")
    print(f"[Dyes] Bal before: gold={char.get('gold',0)} idols={char.get('mammothIdols',0)}")

    # --- Shirt/pants are always free ---
    shirt_changed = False
    pants_changed = False
    if primary_dye is not None:
        c = get_dye_color(primary_dye)
        if c is not None and c != char.get("shirtColor"):
            char["shirtColor"] = c
            shirt_changed = True
    if secondary_dye is not None:
        c = get_dye_color(secondary_dye)
        if c is not None and c != char.get("pantColor"):
            char["pantColor"] = c
            pants_changed = True

    # No changes at all?
    if charge_units == 0 and not shirt_changed and not pants_changed:
        print("[Dyes] No changes detected — nothing to charge")
        send_dye_sync_packet(session, entity_id, dyes_by_slot,
                             char.get("shirtColor"), char.get("pantColor"))
        return

    # Charge if needed
    if charge_units > 0:
        if pay_with_idols:
            if char.get("mammothIdols", 0) < idol_cost:
                print(f"[Dyes] ERROR: Not enough idols")
                return
            char["mammothIdols"] -= idol_cost
            print(f"[Dyes] Charged {idol_cost} idols")
            send_premium_purchase(session, "Dye", idol_cost)
        else:
            if char.get("gold", 0) < gold_cost:
                print(f"[Dyes] ERROR: Not enough gold")
                return
            char["gold"] -= gold_cost
            print(f"[Dyes] Charged {gold_cost} gold")

    # Apply dyes to equipment
    for slot, (d1, d2) in dyes_by_slot.items():
        if slot < len(eq):
            eq_slot = eq[slot]
            if not eq_slot or eq_slot.get("gearID", 0) == 0:
                continue
            eq_slot["colors"] = [d1, d2]
            gear_id = eq_slot.get("gearID")
            for g in inv:
                if g.get("gearID") == gear_id:
                    g["colors"] = [d1, d2]
                    break
            else:
                inv.append(eq_slot.copy())

    # Persist
    save_characters(session.user_id, session.char_list)
    session.player_data["characters"] = session.char_list

    print(f"[Save] Dyes saved. New balances: gold={char.get('gold',0)} idols={char.get('mammothIdols',0)}")

    # Sync to self + broadcast
    for target in [session] + [
        o for o in all_sessions
        if o is not session and o.world_loaded and o.current_level == session.current_level
    ]:
        send_dye_sync_packet(
            target,
            entity_id,
            dyes_by_slot,
            char.get("shirtColor"),
            char.get("pantColor"),
        )

def send_dye_sync_packet(session, entity_id, dyes_by_slot, shirt_color=None, pant_color=None):
        bb = BitBuffer()
        bb.write_method_4(entity_id)

        eq = []
        for char in session.player_data.get("characters", []):
            if char.get("name") == session.current_character:
                eq = char.get("equippedGears", [])
                break

        for slot in range(1, EntType.MAX_SLOTS):
            gear = eq[slot - 1] if slot - 1 < len(eq) else None
            if gear and "colors" in gear:
                d1, d2 = gear["colors"]
                bb.write_method_6(1, 1)  # has dye pair
                bb.write_method_6(d1, DyeType.BITS)
                bb.write_method_6(d2, DyeType.BITS)
            else:
                bb.write_method_6(0, 1)  # no dye pair

        # Write shirt color
        if shirt_color is not None:
            bb.write_method_6(1, 1)
            bb.write_method_6(shirt_color, EntType.CHAR_COLOR_BITSTOSEND)
        else:
            bb.write_method_6(0, 1)

        # Write pant color
        if pant_color is not None:
            bb.write_method_6(1, 1)
            bb.write_method_6(pant_color, EntType.CHAR_COLOR_BITSTOSEND)
        else:
            bb.write_method_6(0, 1)

        payload = bb.to_bytes()
        pkt = struct.pack(">HH", 0x111, len(payload)) + payload
        session.conn.sendall(pkt)
        print(f"[Sync] Sent dye update (0x111) to client for entity {entity_id}")

def PaperDoll_Request(session, data, conn):
    """
    Handles paperdoll request (0x19). Reads character name,
    finds the character in session.char_list, and sends back
    a 0x1A response with their paperdoll or empty if not found.
    """
    name = BitReader(data[4:]).read_method_26()
    #print(f"[{session.addr}] [PKT0x19] Request for paperdoll: {name}")

    for c in session.char_list:
        if c["name"] == name:
            pd = build_paperdoll_packet(c)
            conn.sendall(struct.pack(">HH", 0x1A, len(pd)) + pd)
            #print(f"[{session.addr}] [PKT0x19] Found and sent paperdoll for '{name}'")
            break
    else:
        # Character not found, send empty packet
        conn.sendall(struct.pack(">HH", 0x1A, 0))
        #print(f"[{session.addr}] [PKT0x19] Character '{name}' not found. Sent empty paperdoll.")

def handle_pet_info_packet(session, data, all_sessions):
    """
    Handle packet type 0xB3 (SendPetInfoToServer).
    Updates the active pet (equippedPetID) and the restingPets list in the save file.
    """




    payload = data[4:]  # Skip header (0x00b3 + length)
    reader = BitReader(payload, debug=True)

    try:
        pets = []
        for _ in range(4):  # 1 active + 3 resting
            pet_type_id = reader.read_method_6(7)  # 7-bit pet type ID
            value = reader.read_method_4()         # Variable-length value
            pets.append((pet_type_id, value))

        active_pet_type, active_pet_value = pets[0]
        resting_pets_data = [
            {"typeID": pets[1][0]},
            {"typeID": pets[2][0]},
            {"typeID": pets[3][0]}
        ]

        # Log for debug
        print(f"[{session.addr}] [PKT0xB3] Active pet: type={active_pet_type}, value={active_pet_value}")
        for i, pet in enumerate(resting_pets_data, 1):
            print(f"[{session.addr}] [PKT0xB3] Resting pet {i}: type={pet['typeID']}, value={pets[i][1]}")

        # --- Update save file ---
        for char in session.char_list:
            if char.get("name") != session.current_character:
                continue

            # Update equippedPetID
            char["equippedPetID"] = active_pet_type

            # Update restingPets list
            char["restingPets"] = resting_pets_data

            # Persist changes
            save_characters(session.user_id, session.char_list)
            print(f"[Save] Updated pets for {session.current_character} → activePetID={active_pet_type}, resting={resting_pets_data}")
            break
        else:
            print(f"[{session.addr}] [PKT0xB3] ERROR: character {session.current_character} not found")

    except Exception as e:
        print(f"[{session.addr}] [PKT0xB3] Error parsing packet: {e}")
        for line in reader.get_debug_log():
            print(line)

def handle_mount_equip_packet(session, data, all_sessions):
    """
    Handle packet type 0xB2 for equipping a mount on an entity.
    Parses the payload to extract Entity ID and Mount ID, prints them,
    and updates the character's equipped mount.
    """

    payload = data[4:]
    reader = BitReader(payload, debug=True)

    try:
        # Read Entity ID (method_4)
        entity_id = reader.read_method_4()
        # Read Mount ID (7 bits, as per class_20.const_297)
        mount_id = reader.read_method_6(7)

        print(f"[{session.addr}] [PKT0xB2] Entity ID: {entity_id}, Mount ID: {mount_id}")

        # Validate and update character's equipped mount
        for char in session.char_list:
            if char.get("name") == session.current_character:
                # Check if the mount is owned
                owned_mounts = char.get("mounts", [])
                if mount_id not in owned_mounts and mount_id != 0:  # 0 might mean unequip
                    print(f"[{session.addr}] [PKT0xB2] Invalid mount ID {mount_id} for {session.current_character}")
                    return
                # Update equipped mount
                char["equippedMount"] = mount_id
                session.player_data["characters"] = session.char_list
                save_characters(session.user_id, session.char_list)
                print(f"[{session.addr}] [PKT0xB2] Equipped mount ID {mount_id} for {session.current_character}")
                break
        else:
            print(f"[{session.addr}] [WARNING] Character {session.current_character} not found for PKT0xB2")

        # Broadcast to other sessions (optional, based on game design)
        for other in all_sessions:
            if other is not session and other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(data)
                print(f"[{session.addr}] [PKT0xB2] Broadcasted mount update to {other.addr}")

    except Exception as e:
        print(f"[{session.addr}] [PKT0xB2] Error parsing packet: {e}")
        for line in reader.get_debug_log():
            print(line)


def handle_emote_begin(session, data, all_sessions):
    """
    Packet 0x7E: an entity starts an emote.
    Client sends:
      method_9(entityID) -> var-int via write_method_4
      method_26(emoteString)
    Other clients read:
      method_4() for ID, method_13() for the string.
    """



    # 1) Parse the emote packet
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        entity_id = br.read_method_4()
        emote     = br.read_method_13()
    except Exception as e:
        print(f"[{session.addr}] [PKT7E] Parse error: {e}, raw={payload.hex()}")
        return

    print(f"[{session.addr}] [PKT7E] Entity {entity_id} began emote \"{emote}\"")

    # 2) Broadcast unchanged packet to all other clients in the same level
    for other in all_sessions:
        if (other is not session
            and other.world_loaded
            and other.current_level == session.current_level):
            try:
                other.conn.sendall(data)
            except Exception as e:
                print(f"[{session.addr}] [PKT7E] Error forwarding to {other.addr}: {e}")

def handle_entity_destroy(session, data, all_sessions):
    """
    Packet 0x0D: an entity is destroyed/removed.
    Client sends: method_9(entityID)
    We'll parse, remove from our map, and broadcast to peers.
    """


    # 2) Parse payload
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        # Client uses method_9 to write the ID:
        entity_id = br.read_method_9()
        # No boolean is actually written by the client, so we don't consume extra bits.
    except Exception as e:
        print(f"[{session.addr}] [PKT0D] Parse error: {e}, raw={payload.hex()}")
        return

    #print(f"[{session.addr}] [PKT0D] Entity destroy for ID {entity_id}")

    # 3) Remove from this session's entity map
    if entity_id in session.entities:
        del session.entities[entity_id]
        #print(f"[{session.addr}] [PKT0D] Removed entity {entity_id} from server map")

    # If this was the player, clear clientEntID
    if session.clientEntID == entity_id:
        session.clientEntID = None

    # 4) Broadcast to peers
    for other in all_sessions:
        if (other is not session
            and other.world_loaded
            and other.current_level == session.current_level):
            try:
                other.conn.sendall(data)
                print(f"[{session.addr}] [PKT0D] Broadcasted destroy to {other.addr}")
            except Exception as e:
                print(f"[{session.addr}] [PKT0D] Error sending to {other.addr}: {e}")

def PKTTYPE_BUFF_TICK_DOT(session, data, all_sessions):


    # 1) Strip off 0x79 + length, feed to BitReader
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:

        target_id     = br.read_method_9()
        source_id     = br.read_method_9()
        power_type_id = br.read_method_9()
        amount        = br.read_method_24()
    except Exception as e:
        print(f"[{session.addr}] [PKT79] Parse error: {e}, raw={payload.hex()}")
        return

    print(f"[{session.addr}] [PKT79] Buff tick: target={target_id}, "
          f"source={source_id}, power={power_type_id}, amount={amount}")

    # 2) Rebroadcast the exact same bytes to peers
    for other in all_sessions:
        if (other is not session
            and other.world_loaded
            and other.current_level == session.current_level):
            try:
                other.conn.sendall(data)
            except Exception as e:
                print(f"[{session.addr}] [PKT79] Forward error to {other.addr}: {e}")


def handle_respawn_ack(session, data, all_sessions):

    br = BitReader(data[4:], debug=False)
    try:
        entity_id = br.read_method_9()
        spawn_pos = br.read_method_24()
        used_potion = bool(br.read_method_15())
    except Exception as e:
        print(f"[{session.addr}] [PKT82] Parse error: {e}")
        return

    # Update server state: mark entity alive at spawn_pos
    ent = session.entities.get(entity_id)
    if ent is not None:
        ent['pos_x'] = spawn_pos
        ent['pos_y'] = 0    # or default
        ent['is_alive'] = True
        print(f"[{session.addr}] [PKT82] Entity {entity_id} respawned at {spawn_pos}, potion={used_potion}")

        # Optionally broadcast to peers: raw 0x82 or a custom update
        for other in all_sessions:
            if other is not session and other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(data)
    else:
        print(f"[{session.addr}] [PKT82] Unknown entity {entity_id}")

def handle_group_invite(session, data, all_sessions):
    """
    Packet 0x65: /invite <player>
    Only the invitee gets the 0x58 invite packet.
    No confirmation packet is sent back to the inviter.
    """


    # 1) Parse invitee name
    payload = data[4:]
    try:
        br = BitReader(payload, debug=False)
        invitee_name = br.read_method_13()
    except Exception as e:
        print(f"[{session.addr}] [PKT65] Parse error: {e}, raw={payload.hex()}")
        return

    print(f"[{session.addr}] [PKT65] Group invite from {session.current_character} to {invitee_name}")


    # 2) Find the invitee’s session
    invitee = next((
        s for s in all_sessions
        if s.authenticated
           and s.current_character
           and s.current_character.lower() == invitee_name.lower()
    ), None)

    if not invitee:
        _send_error(session.conn, f"Player {invitee_name} not found")
        print(f"[{session.addr}] [PKT65] Invitee {invitee_name} not found")
        return

    # 3) Ensure inviter has a group_id
    if not getattr(session, 'group_id', None):
        session.group_id = secrets.randbits(16)
        session.group_members = [session]
        print(f"[{session.addr}] [PKT65] Created group {session.group_id}")

    # 4) Reject if invitee already in a group
    if getattr(invitee, 'group_id', None):
        _send_error(session.conn, f"{invitee_name} is already in a group")
        print(f"[{session.addr}] [PKT65] {invitee_name} already in group {invitee.group_id}")
        return

    # 5) Send the invite (0x58) to the invitee only
    bb = BitBuffer()
    inviter_id   = session.clientEntID or 0
    inviter_name = session.current_character
    invite_text  = f"{inviter_name} has invited you to join a party"

    bb.write_method_9(inviter_id)
    bb.write_method_26(inviter_name)
    bb.write_method_26(invite_text)
    body = bb.to_bytes()
    invite_packet = struct.pack(">HH", 0x58, len(body)) + body
    invitee.conn.sendall(invite_packet)
    print(f"[{session.addr}] [PKT65] Sent 0x58 invite to {invitee.current_character}")


def handle_public_chat(session, data, all_sessions):
    """
    Packet 0x2C: global (level-wide) chat.
    Client sends: method_9(entity_id), method_26(message)
    Server rebroadcasts same format.
    """


    # 1) Parse incoming packet
    payload = data[4:]
    try:
        br = BitReader(payload, debug=False)
        entity_id = br.read_method_9()    # client used method_9
        message   = br.read_method_13()   # readMethod13 pairs with writer method_26

    except Exception as e:
        print(f"[{session.addr}] [PKT2C] Error parsing chat: {e}, raw={payload.hex()}")
        return

    print(f"[{session.addr}] [PKT2C] Chat from {entity_id} ({session.current_character}): {message}")

    # 2) Build the rebroadcast packet
    bb = BitBuffer()
    bb.write_method_9(entity_id)
    bb.write_method_26(message)
    body = bb.to_bytes()
    header = struct.pack(">HH", 0x2C, len(body))
    packet = header + body

    # 3) Send to everyone else in the same level
    for other in all_sessions:
        if other is session:
            continue
        if not other.world_loaded or other.current_level != session.current_level:
            continue
        try:
            other.conn.sendall(packet)
            print(f"[{session.addr}] [PKT2C] → \"{message}\" to {other.addr} ({other.current_character})")
        except Exception as e:
            print(f"[{session.addr}] [PKT2C] Error sending to {other.addr}: {e}")

def handle_remove_buff(session, data, all_sessions):
    """
    Packet 0x0C: “remove buff” — client telling server to remove a buff.
    Mirrors AS3 method_1837:
      method_9(entity.id),
      method_9(buffTypeID),
      method_9(param2)
    """


    # 1) Strip header
    payload = data[4:]
    br = BitReader(payload, debug=False)

    try:
        # 2) Read all three var‐ints
        entity_id   = br.read_method_9()  # param1.id
        buff_type   = br.read_method_9()  # param2
        instance_id = br.read_method_9()  # param3

        # 3) Log parsed values
        props = {
            'entity_id':   entity_id,
            'buff_type':   buff_type,
            'instance_id': instance_id,
        }
        #print(f"[{session.addr}] [PKT0C] Parsed remove-buff:")
        #pprint.pprint(props, indent=4)

        # 4) Broadcast unchanged packet to peers
        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)
                print(f"[{session.addr}] [PKT0C] Broadcasted to {other.addr}")

    except Exception as e:
        print(f"[{session.addr}] [PKT0C] Error parsing remove-buff: {e}, raw={payload.hex()}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)

def handle_add_buff(session, data, all_sessions):
    """
    Packet 0x0B: “add buff” — applies a buff/debuff with optional numeric modifiers.
    Mirrors AS3 method_1262:
      method_9(entity.id),
      method_9(param2),
      method_9(param3),
      method_9(param5),
      method_9(param4),
      method_9(param6),
      method_15(vector!=null),
      [vector length + (powerNodeTypeID, modCount, modValues...)]
    """


    # 1) Strip header
    payload = data[4:]
    br = BitReader(payload, debug=False)

    try:
        # 2) Read the six uints (all via method_9)
        entity_id  = br.read_method_9()
        param2     = br.read_method_9()
        param3     = br.read_method_9()
        param5     = br.read_method_9()   # note: client writes param5 _before_ param4
        param4     = br.read_method_9()
        param6     = br.read_method_9()

        # 3) Optional Vector.<class_140>
        has_vector = bool(br.read_method_15())
        vector     = []
        if has_vector:
            length = br.read_method_9()
            for _ in range(length):
                power_node_type_id = br.read_method_9()
                mod_count          = br.read_method_9()
                mods               = [br.read_method_560() for _ in range(mod_count)]
                vector.append({
                    'power_node_type_id': power_node_type_id,
                    'mod_values':         mods
                })

        # 4) Log parsed values
        props = {
            'entity_id': entity_id,
            'param2':     param2,
            'param3':     param3,
            'param4':     param4,
            'param5':     param5,
            'param6':     param6,
            'vector':     vector if has_vector else None
        }
        #print(f"[{session.addr}] [PKT0B] Parsed add-buff:")
        #pprint.pprint(props, indent=4)

        # 5) Broadcast unchanged packet to peers
        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)

    except Exception as e:
        print(f"[{session.addr}] [PKT0B] Error parsing add-buff: {e}, raw={payload.hex()}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)


def handle_projectile_explode(session, data, all_sessions):
    """
    Packet 0x0E: “projectile explode” event.
    Mirrors AS3 WriteProjectileExplode:
      method_9(entity.id),
      method_9(remoteMissileID),
      method_24(param3), method_24(param4),
      method_15(flag)
    """


    # 1) Strip packet header
    payload = data[4:]
    br = BitReader(payload, debug=False)

    try:
        # 2) Read projectile owner entity ID and the missile’s remote ID
        entity_id       = br.read_method_9()
        remote_missile  = br.read_method_9()

        # 3) Read explosion position (24-bit var‐int)
        x = br.read_method_24()
        y = br.read_method_24()

        # 4) Read the final flag (e.g. “spawn splatter”)
        flag = bool(br.read_method_15())

        # 5) Log for verification
        props = {
            'entity_id':      entity_id,
            'remote_missile': remote_missile,
            'x':              x,
            'y':              y,
            'flag':           flag,
        }
        #print(f"[{session.addr}] [PKT0E] Parsed projectile-explode:")
        #pprint.pprint(props, indent=4)

        # 6) Broadcast raw packet to peers
        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)

    except Exception as e:
        print(f"[{session.addr}] [PKT0E] Error parsing projectile explode: {e}, raw={payload.hex()}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)


def handle_power_hit(session, data, all_sessions):
    """
    Packet 0x0A: “power hit” event — source hit target, with optional extra params.
    Mirrors AS3 method_1092 exactly.
    """


    # 1) Strip packet header
    payload = data[4:]
    br = BitReader(payload, debug=False)

    try:
        # 2) Read IDs (both written with method_9 in AS3)
        target_id = br.read_method_9()   # param3.id in client
        source_id = br.read_method_9()   # param1.id in client

        # 3) Read damage/effect value as 24-bit
        value     = br.read_method_24()  # param4

        # 4) Read powerID (var-int)
        power_id  = br.read_method_9()   # param2.powerID

        # 5) Optional param5 (var-int)
        has_p5    = bool(br.read_method_15())
        param5    = br.read_method_9() if has_p5 else 0

        # 6) Optional param6 (var-int)
        has_p6    = bool(br.read_method_15())
        param6    = br.read_method_9() if has_p6 else 0

        # 7) Final boolean flag (crit? or similar)
        param7    = bool(br.read_method_15())

        # 8) Log what we got
        props = {
            'target_id': target_id,
            'source_id': source_id,
            'value':      value,
            'power_id':   power_id,
            'param5':     param5 if has_p5 else None,
            'param6':     param6 if has_p6 else None,
            'flag':       param7,
        }
        #print(f"[{session.addr}] [PKT0A] Parsed power-hit:")
        #pprint.pprint(props, indent=4)

        # 9) Broadcast unchanged packet to other clients
        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)

    except Exception as e:
        print(f"[{session.addr}] [PKT0A] Error parsing power-hit: {e}, raw={payload.hex()}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)

def handle_power_cast(session, data, all_sessions):


    payload = data[4:]
    br = BitReader(payload, debug=False)

    try:
        ent_id   = br.read_method_9()
        power_id = br.read_method_9()

        # ← CORRECTED TARGET‐POINT HANDSHAKE
        _ = br.read_method_15()                        # discard hasTargetEntity
        has_target_pos = bool(br.read_method_15())     # var_2846: does this power type support coords?
        target_pt = None
        if has_target_pos:
            target_x = br.read_method_24()
            target_y = br.read_method_24()
            target_pt = (target_x, target_y)

        # projectile
        has_proj = bool(br.read_method_15())
        proj_id  = br.read_method_9() if has_proj else None

        # charged flag
        is_charged = bool(br.read_method_15())

        # melee‐combo / var_674 branch
        has_extra = bool(br.read_method_15())
        secondary_id = tertiary_id = None
        if has_extra:
            is_secondary = bool(br.read_method_15())
            if is_secondary:
                secondary_id = br.read_method_9()
            else:
                tertiary_id = br.read_method_9()

        # cooldown & mana
        has_flags = bool(br.read_method_15())
        cooldown_tick = mana_cost = None
        if has_flags:
            if bool(br.read_method_15()):
                cooldown_tick = br.read_method_9()
            if bool(br.read_method_15()):
                MANA_BITS = PowerType.const_423
                mana_cost = br.read_method_6(MANA_BITS)

        props = {
            #'caster_ent_id': ent_id,
            'power_id':      power_id,
            #'target_pt':     target_pt,
            #'projectile_id': proj_id,
            #'is_charged':    is_charged,
            #'secondary_id':  secondary_id,
            #'tertiary_id':   tertiary_id,
            #'cooldown_tick': cooldown_tick,
            #'mana_cost':     mana_cost,
        }
        #print(f"[{session.addr}] [PKT09] Parsed power-cast:")
        #pprint.pprint(props, indent=4)

        # broadcast to peers
        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)

    except Exception as e:
        print(f"[{session.addr}] [PKT09] Error parsing power-cast: {e}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)

def handle_linkupdater(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        client_time = br.read_method_24()
        is_desync   = bool(br.read_method_15())
        server_time = br.read_method_24()

        # Update our session’s clock‐sync info
        session.client_elapsed  = client_time
        session.server_elapsed  = server_time
        session.clock_desynced  = is_desync
        session.clock_offset_ms = server_time - client_time

        #print(f"[{session.addr}] [PKTA2] Sync: client={client_time}ms "
        #      f"server={server_time}ms desync={is_desync} offset={session.clock_offset_ms}ms")

        #TODO...
        # If the client thinks we’re badly out of sync, we can reply here
        # response = build_clock_correction_packet(...)
        # session.conn.sendall(response)

    except Exception as e:
        print(f"[{session.addr}] [PKTA2] Error parsing link-sync: {e}")

def build_entity_dict(eid, char, props):
    """
    Build a dictionary for Send_Entity_Data packet.
    Works for both joiner (new spawn) and existing entities.
    """
    ent_dict = {
        "id": eid,
        "name": char.get("name", props.get("ent_name", "")) if char else props.get("ent_name", ""),
        "is_player": True if char else bool(props.get("is_player", False)),
        "x": int(props.get("pos_x", 0)),
        "y": int(props.get("pos_y", 0)),
        "v": int(props.get("velocity_x", 0)),
        "team": int(props.get("team", 1)),
    }
    if char:
        ent_dict.update({
            "class": char.get("class", ""),
            "gender": char.get("gender", ""),
            "headSet": char.get("headSet", ""),
            "hairSet": char.get("hairSet", ""),
            "mouthSet": char.get("mouthSet", ""),
            "faceSet": char.get("faceSet", ""),
            "hairColor": char.get("hairColor", 0),
            "skinColor": char.get("skinColor", 0),
            "shirtColor": char.get("shirtColor", 0),
            "pantColor": char.get("pantColor", 0),
            "equippedGears": char.get("equippedGears", []),
            "abilities": char.get("learnedAbilities", []),
            "level": char.get("level", 1),
            "Talent_id": char.get("MasterClass", 0),
            "equippedMount": char.get("equippedMount", 0),
        })

    return ent_dict


def send_existing_entities_to_joiner(joiner, all_sessions):
    """
    Send spawn packets (Send_Entity_Data) ONLY for players in the same level
    to the joining player.
    NPCs are skipped and should be spawned separately by the level loader.
    """
    for other in all_sessions:
        if other is joiner:
            continue
        if not other.world_loaded or other.current_level != joiner.current_level:
            continue

        # Only send the entity that belongs to the player's character
        if other.clientEntID and other.clientEntID in other.entities:
            eprops = other.entities[other.clientEntID]

            char = next((c for c in other.char_list if c.get("name") == other.current_character), None)
            ent_dict = build_entity_dict(other.clientEntID, char, eprops)

            try:
                pkt = Send_Entity_Data(ent_dict)
                framed = struct.pack(">HH", 0x0F, len(pkt)) + pkt
                joiner.conn.sendall(framed)
                print(f"[JOIN] Sent player {ent_dict['name']} (eid={other.clientEntID}) → {joiner.addr}")
            except Exception as ex:
                print(f"[JOIN] Error sending player {ent_dict['name']} to {joiner.addr}: {ex}")

def handle_entity_full_update(session, data, all_sessions):
    """
    Handle a full entity spawn/update (packet type 0x08) from a client.
    - Parses and stores entity info.
    - Marks player entity IDs.
    - Sends 0x0F spawn packets so players see each other.
    - Broadcasts raw 0x08 packets for movement/state sync.
    """
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        # ── Parse fields ──
        entity_id  = br.read_method_9()
        pos_x      = br.read_method_24()
        pos_y      = br.read_method_24()
        velocity_x = br.read_method_24()
        ent_name   = br.read_method_26()

        team       = br.read_method_20(Entity.TEAM_BITS)
        is_player  = bool(br.read_method_15())
        y_offset   = br.read_method_706()

        # Optional cue data
        has_cue = bool(br.read_method_15())
        cue_data = {}
        if has_cue:
            if bool(br.read_method_15()):
                cue_data["character_name"] = br.read_method_13()
            if bool(br.read_method_15()):
                cue_data["DramaAnim"] = br.read_method_13()
            if bool(br.read_method_15()):
                cue_data["SleepAnim"] = br.read_method_13()

        has_summoner = bool(br.read_method_15())
        summoner_id = br.read_method_9() if has_summoner else None

        has_power = bool(br.read_method_15())
        power_id  = br.read_method_9() if has_power else None

        ent_state   = br.read_method_20(Entity.const_316)
        b_left      = bool(br.read_method_15())
        b_running   = bool(br.read_method_15())
        b_jumping   = bool(br.read_method_15())
        b_dropping  = bool(br.read_method_15())
        b_backpedal = bool(br.read_method_15())

        # Track client’s entity ID
        if is_player and session.clientEntID is None:
            session.clientEntID = entity_id
            print(f"[{session.addr}] [PKT08] Learned clientEntID = {entity_id}")

        # Build props
        props = {
            "pos_x": pos_x,
            "pos_y": pos_y,
            "velocity_x": velocity_x,
            "ent_name": ent_name,
            "team": team,
            "is_player": is_player,
            "y_offset": y_offset,
            "cue_data": cue_data,
            "summoner_id": summoner_id,
            "power_id": power_id,
            "ent_state": ent_state,
            "b_left": b_left,
            "b_running": b_running,
            "b_jumping": b_jumping,
            "b_dropping": b_dropping,
            "b_backpedal": b_backpedal,
        }

        #print(f"[{session.addr}] [PKT08] Parsed entity {entity_id}:")
        #pprint.pprint(props, indent=4)

        # Update server-side map
        session.entities[entity_id] = props

        # First-time world load for this player
        if not session.world_loaded:
            session.world_loaded = True
            send_existing_entities_to_joiner(session, all_sessions)

            # Broadcast THIS player’s spawn to others
            char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
            if char:
                ent_dict = build_entity_dict(entity_id, char, props)
                try:
                    pkt = Send_Entity_Data(ent_dict)
                    framed = struct.pack(">HH", 0x0F, len(pkt)) + pkt
                    for other in all_sessions:
                        if other is not session and other.world_loaded and other.current_level == session.current_level:
                            other.conn.sendall(framed)
                            print(f"[JOIN] Broadcasted Send_Entity_Data for {ent_dict['name']} → {other.addr}")
                except Exception as e:
                    print(f"[JOIN] Failed to build/broadcast Send_Entity_Data for new player: {e}")

        # Always forward raw 0x08 packet for movement sync
        for other in all_sessions:
            if other is not session and other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(data)
                print(f"[{session.addr}] [PKT08] Broadcasted raw packet to {other.addr}")

    except Exception as e:
        print(f"[{session.addr}] [PKT08] Error parsing packet: {e}")
        if br.debug:
            for log_line in br.get_debug_log():
                print(log_line)

def handle_entity_incremental_update(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        # 1) Read caster/entity ID
        entity_id = br.read_method_4()

        is_self = (entity_id == session.clientEntID)
        if not is_self and entity_id not in session.entities:
            print(f"[{session.addr}] [PKT07] Unknown entity {entity_id} movement dropped")
            return

        # 2) Read deltas
        delta_x = br.read_method_45()
        delta_y = br.read_method_45()
        delta_vx = br.read_method_45()

        #print(f"delta_x:{delta_x} delta_y : {delta_y} : delta_vx : {delta_vx} ")
        # 3) Read state & flags
        STATE_BITS = Entity.const_316
        ent_state = br.read_method_6(STATE_BITS)
        flags = {
            'b_left':      bool(br.read_method_15()),
            'b_running':   bool(br.read_method_15()),
            'b_jumping':   bool(br.read_method_15()),
            'b_dropping':  bool(br.read_method_15()),
            'b_backpedal': bool(br.read_method_15()),
        }

        # 4) Airborne check
        is_airborne = bool(br.read_method_15())
        velocity_y = br.read_method_24() if is_airborne else 0

        # ────────────────────────────────────────────────────────────
        # ← NEW: always use last-full-update coords if available
        ent = session.entities.get(entity_id, {})
        old_x = ent.get('pos_x')
        old_y = ent.get('pos_y')

        # Determine spawn/origin based on memory and level type
        current_level = session.current_level
        lvl_cfg = LEVEL_CONFIG.get(current_level, (None,) * 4)
        is_dungeon = lvl_cfg[3]

        # ────────────────────────────────────────────────────────────

        # 5) Compute new absolute position
        new_x = old_x + delta_x
        new_y = old_y + delta_y

        # 6) Update server-side map
        ent.update({
            'pos_x':      new_x,
            'pos_y':      new_y,
            'velocity_x': ent.get('velocity_x', 0) + delta_vx,
            'velocity_y':  velocity_y,
            'ent_state':   ent_state,
            **flags
        })
        session.entities[entity_id] = ent

        # 7) Persist file only when non-dungeon and truly moving
        if ent.get('is_player') and not is_dungeon:
            for char in session.char_list:
                if char['name'] == session.current_character:
                    char['CurrentLevel'] = {'name': session.current_level, 'x': new_x, 'y': new_y}
                    save_characters(session.user_id, session.char_list)
                    break

        #print(f"[{session.addr}] [PKT07] | Entity_ID:{entity_id} | Moved to =({new_x},{new_y}), state={ent_state}")
        for other in all_sessions:
            if other is not session and other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(data)
    except Exception as e:
        print(f"[{session.addr}] [PKT07] Error parsing packet: {e}")
        for line in br.get_debug_log():
            print(line)

def handle_start_skit(session, data, all_sessions):
    """
    Handle packet 0xC5: Client requests to start or stop a skit for an entity.
    - Reads entity ID, boolean flag, and text.
    - Sends PKT_ROOM_THOUGHT (0x76) only if flag is True.
    """
    payload = data[4:]  # Strip 4-byte header
    br = BitReader(payload, debug=True)
    try:
        entity_id = br.read_method_9()
        flag = bool(br.read_method_15())
        text = br.read_method_26()
    except Exception as e:
        print(f"[{session.addr}] [PKT0xC5] Error parsing packet: {e}")
        return

    if flag:
        bb = BitBuffer()
        bb.write_method_4(entity_id)
        bb.write_method_13(text)
        payload = bb.to_bytes()
        packet = struct.pack(">HH", 0x76, len(payload)) + payload

        for other_session in all_sessions:
            if other_session.world_loaded and other_session.current_level == session.current_level:
                other_session.conn.sendall(packet)

        print(f"[{session.addr}] [PKT0xC5] Sent skit message from entity {entity_id}: '{text}'")
    else:
        print(f"[{session.addr}] [PKT0xC5] Skit flag is False for entity {entity_id}, message suppressed")

def handle_hotbar_packet(session, raw_data):
    payload = raw_data[4:]
    reader = BitReader(payload)

    slot = 1
    updates = {}   # slot_index (0‑based) -> new skill_id
    while reader.remaining_bits() >= 1:
        changed = reader.read_method_20(1)
        if changed:
            skill_id = reader.read_method_20(7)
            updates[slot - 1] = skill_id
        slot += 1

    print(f"[Hotbar] Player {session.user_id} updates → {updates}")

    # 2) Locate the right character in the save
    for char in session.char_list:
        if char.get("name") == session.current_character:
            # 3) Fetch existing list, or default to zeros
            active = char.get("activeAbilities", [])
            # ensure it's long enough
            max_idx = max(updates.keys(), default=-1)
            while len(active) <= max_idx:
                active.append(0)

            # 4) Apply updates in‑place
            for idx, skill_id in updates.items():
                active[idx] = skill_id

            # 5) Store back
            char["activeAbilities"] = active
            break
    else:
        print(f"[WARNING] Character {session.current_character} not found in save!")
        return

    # 6) Persist full JSON
    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)
    print(f"[Save] activeAbilities for {session.current_character} = {active} saved (user_id={session.user_id})")

def handle_respec_talent_tree(session, data):
    """
    Handles client request 0xD2 to reset the talent tree using a Respec Stone.
    Deducts one Respec Stone (charmID 91) from the character's inventory.
    """
    try:
        # Find active character
        char = next((c for c in session.char_list if c["name"] == session.current_character), None)
        if not char:
            return  # no active character

        # Deduct one Respec Stone (charmID 91)
        charms = char.setdefault("charms", [])
        for entry in charms:
            if entry.get("charmID") == 91:
                if entry.get("count", 0) > 0:
                    entry["count"] -= 1
                    if entry["count"] <= 0:
                        charms.remove(entry)
                break
        else:
            # Optional: No stones available, could log or return
            print(f"[{session.addr}] No Respec Stones available for {char['name']}")
            return

        # Reset the talent tree
        mc = str(char.get("MasterClass", 1))
        talent_tree = char.setdefault("TalentTree", {}).setdefault(mc, {})

        # Reset all 27 slots
        talent_tree["nodes"] = [
            {"nodeID": index_to_node_id(i), "points": 0, "filled": False}
            for i in range(27)
        ]

        # Persist the character data after modification
        save_characters(session.user_id, session.char_list)
        print(f"[{session.addr}] Talent tree reset and 1 Respec Stone used for {char['name']}")

    except Exception as e:
        print(f"[{session.addr}] [PKT_RESPEC] Error: {e}")

def allocate_talent_tree_points(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        # 1) Locate active character & TalentTree
        char = next((c for c in session.char_list if c["name"] == session.current_character), None)
        if not char:
            print(f"[{session.addr}] [PKT_TALENT_UPGRADE] No active character found")
            return

        master_class = str(char.get("MasterClass", 1))
        talent_tree = char.setdefault("TalentTree", {}).setdefault(master_class, {})

        # Initialize a 27-slot array to emulate client var_58
        slots = [None] * 27

        # 2) Parse full tree (27 slots)
        for i in range(27):
            has_node = br.read_method_15()
            node_id = index_to_node_id(i)

            if has_node:
                # Node ID from packet
                node_id_from_packet = br.read_method_6(class_118.const_127)
                points_spent = br.read_method_6(method_277(i)) + 1  # +1 for node itself
                slots[i] = {
                    "nodeID": node_id_from_packet,
                    "points": points_spent,
                    "filled": True
                }
            else:
                # Empty slot
                slots[i] = {
                    "nodeID": node_id,
                    "points": 0,
                    "filled": False
                }

        # 3) Parse incremental actions
        actions = []
        while br.read_method_15():
            is_signet = br.read_method_15()
            if is_signet:
                node_index = br.read_method_6(class_118.const_127)
                signet_group = br.read_method_6(class_118.const_127)
                signet_index = br.read_method_6(class_118.const_127) - 1
                actions.append({
                    "action": "signet",
                    "nodeIndex": node_index,
                    "signetGroup": signet_group,
                    "signetIndex": signet_index
                })
            else:
                node_index = br.read_method_6(class_118.const_127)
                actions.append({
                    "action": "upgrade",
                    "nodeIndex": node_index
                })

        # 4) Save back to TalentTree in array order
        talent_tree["nodes"] = slots

        # 5) Persist to player data and database
        session.player_data["characters"] = session.char_list
        save_characters(session.user_id, session.char_list)

        print(f"[{session.addr}] [PKT_TALENT_UPGRADE] Updated TalentTree[{master_class}]")
        for idx, slot in enumerate(slots):
            print(f"  Slot {idx + 1}: {slot}")
        print(f"  → Actions: {actions}")

    except Exception as e:
        print(f"[{session.addr}] [PKT_TALENT_UPGRADE] Error parsing: {e}")
        for line in br.get_debug_log():
            print(line)