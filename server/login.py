import copy
import hashlib
import json
import os
import secrets
import struct
import time

from Character import load_characters, build_login_character_list_bitpacked, load_class_template, save_characters
from WorldEnter import build_enter_world_packet, Player_Data_Packet
from accounts import get_or_create_user_id, load_accounts, build_popup_packet, _SAVES_DIR, is_character_name_taken
from ai_logic import AI_ENABLED, ensure_ai_loop, run_ai_loop
from bitreader import BitReader
from constants import EntType
from entity import Send_Entity_Data, ensure_level_npcs
from globals import SECRET, session_by_token, _level_add, pending_world, current_characters, used_tokens, \
    extended_sent_map, token_char
from level_config import LEVEL_CONFIG, get_spawn_coordinates

def handle_login_version(session, data, conn):
    br = BitReader(data[4:])
    client_version = br.read_method_9()

    if client_version != 100:
        print(f"[{session.addr}] Unsupported client version: {client_version}")
        return

    print(f"[{session.addr}] Client version OK: {client_version}")

    sid = secrets.randbelow(1 << 16)
    sid_bytes = sid.to_bytes(2, "big")
    digest = hashlib.md5(sid_bytes + SECRET).hexdigest()[:12]

    challenge = f"{sid:04x}{digest}"
    session.challenge_str = challenge

    utf_bytes = challenge.encode("utf-8")
    payload = struct.pack(">H", len(utf_bytes)) + utf_bytes
    pkt = struct.pack(">HH", 0x12, len(payload)) + payload

    conn.sendall(pkt)
    print(f"[{session.addr}] → Sent 0x12 login challenge sid={sid:04x} hash={digest}")

def handle_login_create(session, data, conn):
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
    br = BitReader(data[4:])
    client_facebook_id = br.read_method_26()
    client_kongregate_id = br.read_method_26()
    email = br.read_method_26().strip().lower()
    encrypted_password = br.read_method_26()
    legacy_auth_key = br.read_method_26()

    accounts = load_accounts()
    user_id = accounts.get(email)

    if not user_id:
        conn.sendall(build_popup_packet("Account not found", disconnect=True))
        print(f"[{session.addr}] [0x14] Login failed — no account for {email}")
        return

    session.user_id = user_id
    save_path = os.path.join(_SAVES_DIR, f"{user_id}.json")

    if os.path.exists(save_path):
        with open(save_path, "r", encoding="utf-8") as f:
            session.player_data = json.load(f)
    else:
        print(f"[{session.addr}] [0x14] No save file for user {user_id}, creating blank save.")
        session.player_data = {"email": email, "characters": []}

    session.char_list = session.player_data.get("characters", [])
    session.authenticated = True

    pkt = build_login_character_list_bitpacked(session.char_list)
    conn.sendall(pkt)

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

    # --- build new character ---
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

    # --- append + save ---
    session.char_list.append(new_char)
    session.player_data["characters"] = session.char_list
    save_path = os.path.join(_SAVES_DIR, f"{session.user_id}.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

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
    br = BitReader(data[4:])
    try:
        name = br.read_method_26()
    except Exception as e:
        print(f"[{session.addr}] [0x16] Error reading character name: {e}, raw={data.hex()}")
        return

    for c in session.char_list:
        if c["name"] == name:
            session.current_character = name
            session.current_char_dict = c
            current_level = c.get("CurrentLevel", {}).get("name", "CraftTown")
            prev_level = c.get("PreviousLevel", {}).get("name", "NewbieRoad")
            session.current_level = current_level

            # Issue token
            tk = session.ensure_token(c, target_level=current_level, previous_level=prev_level)
            session.clientEntID = tk
            session_by_token[tk] = session
            _level_add(current_level, session)

            level_config = LEVEL_CONFIG.get(
                current_level, ("LevelsNR.swf/a_Level_NewbieRoad", 1, 1, False)
            )
            is_hard = current_level.endswith("Hard")
            new_moment = "Hard" if is_hard else ""
            new_alter = "Hard" if is_hard else ""

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
            pending_world[tk] = (c, current_level, prev_level)

            # Save the updated player_data format
            session.player_data["characters"] = session.char_list
            save_path = os.path.join(_SAVES_DIR, f"{session.user_id}.json")
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(session.player_data, f, indent=2)

            print(f"[{session.addr}] [0x16] Transfer begin: {name}, tk={tk}, level={current_level}")
            break

def handle_gameserver_login(session, data, conn):
    token = int.from_bytes(data[4:], 'big')

    entry = used_tokens.get(token) or pending_world.get(token)
    if entry is None:
        if len(pending_world) == 1:
            token, entry = next(iter(pending_world.items()))
        else:
            s = session_by_token.get(token)
            if s:
                entry = (
                    getattr(s, "current_char_dict", None)
                    or {"name": s.current_character},
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

    # Determine dungeon entry
    is_dungeon = LEVEL_CONFIG.get(target_level, (None, None, None, False))[3]
    session.entry_level = previous_level if is_dungeon else None

    # user_id already known from authentication
    if not session.user_id:
        key = token_char.get(token)
        if key:
            uid, char_name = key
            session.user_id = uid
            session.current_character = char_name
            print(f"[{session.addr}] Restored user_id from token: {uid}")
        else:
            print(f"[{session.addr}] Warning: could not resolve user_id for token {token}")
            return

    # Update character list in save
    session.char_list = load_characters(session.user_id)
    updated = False
    for i, c in enumerate(session.char_list):
        if c["name"] == char["name"]:
            session.char_list[i] = char
            updated = True
            break
    if not updated:
        session.char_list.append(char)

    session.player_data["characters"] = session.char_list
    save_path = os.path.join(_SAVES_DIR, f"{session.user_id}.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

    pending_world.pop(token, None)
    session.current_level = target_level
    session.current_character = char["name"]
    session.current_char_dict = char
    current_characters[session.user_id] = session.current_character
    session.authenticated = True

    used_tokens[token] = (char, target_level, previous_level)

    new_x, new_y, new_has_coord = get_spawn_coordinates(char, previous_level, target_level)

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

    print(f"[{session.addr}] Welcome: {char['name']} (token {token})")

    npcs = ensure_level_npcs(session.current_level)
    if AI_ENABLED:
        ensure_ai_loop(session.current_level, run_ai_loop)
    else:
        print(f"[AI] Skipping loop for level {session.current_level} (AI disabled)")

    for npc in npcs.values():
        try:
            payload = Send_Entity_Data(npc)
            conn.sendall(struct.pack(">HH", 0x0F, len(payload)) + payload)
            session.entities[npc["id"]] = npc
        except Exception as e:
            print(f"[{session.addr}] Error sending NPC {npc['id']} to {session.current_level}: {e}")

    print(f"[{session.addr}] NPCs synced for level {session.current_level}")