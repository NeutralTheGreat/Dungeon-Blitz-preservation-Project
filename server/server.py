#!/usr/bin/env python3
import copy
import os
import json
import socket, struct, hashlib, sys, time, secrets, threading

from Brain import tick_npc_brains
from accounts import get_or_create_user_id, load_accounts, _SAVES_DIR, is_character_name_taken, build_popup_packet
from Character import (
    build_login_character_list_bitpacked,
    build_paperdoll_packet,
    load_characters,
    save_characters, get_inventory_gears, build_level_gears_packet, load_class_template
)
from BitBuffer import BitBuffer
from Commands import handle_hotbar_packet, handle_masterclass_packet, handle_gear_packet, \
    handle_apply_dyes, handle_rune_packet, handle_change_look, handle_create_gearset, handle_name_gearset, \
    handle_apply_gearset, handle_update_equipment, magic_forge_packet, collect_forge_charm, start_forge_packet, \
    cancel_forge_packet, allocate_talent_points, use_forge_xp_consumable, handle_private_message, \
    handle_public_chat, handle_group_invite, handle_power_cast, handle_power_hit, \
    handle_projectile_explode, handle_add_buff, handle_remove_buff, handle_entity_full_update, \
    handle_entity_incremental_update, handle_request_door_state, Start_Skill_Research, \
    handle_research_claim, PaperDoll_Request, Skill_Research_Cancell_Request, Skill_SpeedUp, handle_building_upgrade, \
    handle_speedup_request, handle_cancel_upgrade, handle_train_talent_point, handle_talent_speedup, \
    handle_talent_claim, handle_clear_talent_research, handle_hp_increase_notice, handle_volume_enter, \
    handle_change_offset_y, handle_start_skit, handle_change_max_speed, handle_lockbox_reward, handle_grant_reward, \
    handle_linkupdater, handle_request_respawn, handle_respawn_ack, PKTTYPE_BUFF_TICK_DOT, handle_entity_destroy, \
    handle_emote_begin, Client_Crash_Reports, handle_mount_equip_packet, handle_pet_info_packet, \
    handle_collect_hatched_egg, handle_talk_to_npc, handle_char_regen, allocate_talent_tree_points, \
    handle_respec_talent_tree, handle_building_claim
from WorldEnter import build_enter_world_packet, Player_Data_Packet
#from admin_panel import run_admin_panel
from bitreader import BitReader
from PolicyServer import start_policy_server
from constants import EntType
from static_server import start_static_server
from entity import Send_Entity_Data, load_npc_data_for_level
from level_config import DOOR_MAP, LEVEL_CONFIG, get_spawn_coordinates
from scheduler import set_active_session_resolver

HOST = "127.0.0.1"
PORTS = [8080]# Developer mode Port : 7498
pending_world = {}
all_sessions = []
current_characters = {}
used_tokens = {}
session_by_token = {}
level_registry = {}
char_tokens = {}
token_char   = {}
extended_sent_map = {}  # user_id -> bool
level_npcs = {}  # { "LevelName": {eid: npc_dict, ...}, ... }

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

#with open("saves/ac89b54f094c.json", "r", encoding="utf-8") as f:
    #DEV_DUMMY_CHAR = json.load(f)["characters"][0]

SECRET_HEX = "815bfb010cd7b1b4e6aa90abc7679028"
SECRET      = bytes.fromhex(SECRET_HEX)

def _level_add(level, session):
    s = level_registry.setdefault(level, set())
    s.add(session)

def _level_remove(level, session):
    s = level_registry.get(level)
    if s and session in s:
        s.remove(session)
        if not s:
            level_registry.pop(level, None)

def send_login_challenge(conn):
    # 1) pick a random 16-bit sid
    sid = secrets.randbelow(1 << 16)
    sid_bytes = sid.to_bytes(2, "big")
    # 2) compute MD5(sid_bytes || SECRET) → take first 12 hex chars
    digest = hashlib.md5(sid_bytes + SECRET).hexdigest()[:12]
    # 3) build a single ASCII-hex string: 4 hex digits of sid + 12 hex digits of digest
    #    e.g. "1A2B3c4d5e6f7a8b9c0d"
    sid_hex = f"{sid:04x}"
    challenge_str = sid_hex + digest  # total length = 16 chars
    # 4) UTF-encode it with a 2-byte length prefix
    utf_bytes = challenge_str.encode("utf-8")
    payload = struct.pack(">H", len(utf_bytes)) + utf_bytes
    # 5) prepend the 0x12 header
    packet = struct.pack(">HH", 0x12, len(payload)) + payload
    # 6) send to client
    conn.sendall(packet)
    print(f"→ Sent 0x12 login challenge sid={sid_hex} hash={digest}")

def new_transfer_token():
    """Allocate a persistent 16-bit token not in use."""
    while True:
        t = secrets.randbits(16)
        if t not in session_by_token:
           return t

def find_active_session(user_id, char_name):
    for s in all_sessions:
        if getattr(s, 'user_id', None) == user_id and getattr(s, 'current_character', None) == char_name and s.authenticated:
            return s
    return None

# register resolver
set_active_session_resolver(find_active_session)

class ClientSession:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr

        # Authentication / account
        self.user_id = None
        self.authenticated = False
        self.char_list = []           # list of characters belonging to this user
        self.current_character = None # name of active character
        self.current_char_dict = None # dict of active character’s data

        # World state
        self.current_level = None
        self.entry_level = None
        self.world_loaded = False
        self.clientEntID = None       # entity ID assigned to the player

        # Entities / NPCs
        self.entities = {}            # {eid: props} for all tracked entities in this session
        self.spawned_npcs = []        # list of NPC dicts spawned in this session

        # Misc
        self.player_data = {}
        self.running = True

    def stop(self):
        self.running = False
        self.cleanup()

    def get_entity(self, entity_id):
        """
        Retrieve an entity from session.entities by its ID.
        Returns the entity dictionary or None if not found.
        """
        return self.entities.get(entity_id)

    def issue_token(self, char, target_level, previous_level):
        # Backward-compat wrapper: we now keep a persistent token per session
        tk = self.ensure_token(char, target_level=target_level, previous_level=previous_level)
        return tk

    def ensure_token(self, char, target_level=None, previous_level=None):
        key = (char.get("user_id"), char.get("name"))
        if key in char_tokens:
            tk = char_tokens[key]
        else:
            tk = new_transfer_token()
            char_tokens[key] = tk
            token_char[tk] = key
        self.clientEntID = tk
        session_by_token[tk] = self
        return tk

    def cleanup(self):
        try: self.conn.close()
        except: pass

        if self.clientEntID in session_by_token:
            session_by_token.pop(self.clientEntID, None)
        if self.current_level:

            _level_remove(self.current_level, self)
        if self in all_sessions:
            all_sessions.remove(self)

        if self.user_id in extended_sent_map:
            extended_sent_map[self.user_id]["last_seen"] = time.time()


def prune_extended_sent_map(timeout: int = 2):
    """Remove users from extended_sent_map if they haven't reconnected in 'timeout' seconds."""
    now = time.time()
    for uid, data in list(extended_sent_map.items()):
        if now - data.get("last_seen", now) > timeout:
            extended_sent_map.pop(uid, None)
            print(f"[DEBUG] Cleared extended_sent_map for user_id={uid} (timeout expired)")


def read_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf

def handle_client(session: ClientSession):
    conn = session.conn
    addr = session.addr
    print("Connected:", addr)
    conn.settimeout(300)

    tick_npc_brains(all_sessions)

    prune_extended_sent_map(timeout=2)
    buffer = bytearray()
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                print(f"[{addr}] Connection closed by client")
                break
            buffer.extend(chunk)

            # Try to extract complete packets
            while len(buffer) >= 4:
                # Peek header
                pkt    = int.from_bytes(buffer[0:2], byteorder='big')
                length = int.from_bytes(buffer[2:4], byteorder='big')
                total  = 4 + length

                # If we don’t yet have the full packet, wait for more data
                if len(buffer) < total:
                    break

                # We have a full packet in buffer[0:total]
                data    = bytes(buffer[:total])
                payload = data[4:]
                # Remove it from buffer
                del buffer[:total]

                # Debug‐print
               #print(f"[{addr}] Framed pkt=0x{pkt:02X} length={length} payload_bytes={len(payload)}")

                # Sanity check
                if len(payload) != length:
                    print(f"[{addr}] ⚠️ Length mismatch: header says {length} but payload is {len(payload)}")
                    # continue

            if pkt == 0x11:# Done
                send_login_challenge(conn)
                continue

            elif pkt == 0x13:  # Done
                br = BitReader(data[8:], debug=True)
                email = br.read_method_26().strip().lower()
                session.user_id = get_or_create_user_id(email)
                session.char_list = load_characters(session.user_id)
                session.authenticated = True
                conn.sendall(build_login_character_list_bitpacked(session.char_list))

            elif pkt == 0x14:  # Done
                br = BitReader(data[4:], debug=True)
                try:
                    client_facebook_id = br.read_method_26()  # Facebook platform ID
                    client_kongregate_id = br.read_method_26()  # Kongregate platform ID
                    email = br.read_method_26().strip().lower()  # Primary login identifier
                    password = br.read_method_26()  # Password or session token
                    legacy_auth_key = br.read_method_26()  # Embed auth key / API key
                except Exception as e:
                    print(f"[{session.addr}] [PKT0x14] Error parsing packet: {e}, raw payload={data[4:].hex()}")
                    continue
                accounts = load_accounts()
                user_id = accounts.get(email)
                if not user_id:
                    #print(f"[{session.addr}] [PKT0x14] Login failed—no account for {email}")
                    conn.sendall(build_popup_packet("Account not found", disconnect=True))
                    continue
                session.user_id = user_id
                try:
                    with open(os.path.join(_SAVES_DIR, f"{session.user_id}.json"), "r", encoding="utf-8") as f:
                        session.player_data = json.load(f)
                except FileNotFoundError:
                    session.player_data = {"email": email, "characters": []}
                session.char_list = session.player_data.get("characters", [])
                session.authenticated = True
                conn.sendall(build_login_character_list_bitpacked(session.char_list))
                print(f"[{session.addr}] [PKT0x14] Logged in {email} → user_id={user_id}, chars={len(session.char_list)}")



            elif pkt == 0x17:
                if not session.authenticated:
                    err_packet = build_popup_packet("Please log in first", disconnect=True)
                    conn.sendall(err_packet)
                    continue
                br = BitReader(data[4:], debug=True)
                try:
                    name = br.read_method_26()  # character name
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
                    print(f"[{session.addr}] [PKT0x17] Parsed character creation: "
                          f"name={name}, class={class_name}, gender={gender}")
                except Exception as e:
                    print(f"[{session.addr}] [PKT0x17] Error parsing packet: {e}, raw payload={data[4:].hex()}")
                    continue
                if is_character_name_taken(name):
                    err_packet = build_popup_packet(
                        "Character name is unavailable. Please choose a new name.",
                        disconnect=False
                    )
                    conn.sendall(err_packet)
                    continue
                # Load class template
                base_template = load_class_template(class_name)
                new_char = copy.deepcopy(base_template)
                # Apply the client-selected cosmetic choices
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
                session.char_list.append(new_char)
                save_characters(session.user_id, session.char_list)

                # Send updated character list (0x15)
                conn.sendall(build_login_character_list_bitpacked(session.char_list))
                print(f"[{session.addr}] [PKT0x17] Sent 0x15 character list update")

                # Send paperdoll packet (0x1A)
                pd = build_paperdoll_packet(new_char)
                conn.sendall(struct.pack(">HH", 0x1A, len(pd)) + pd)
                print(f"[{session.addr}] [PKT0x17] Sent 0x1A paperdoll packet, len={len(pd)},")

                # Send popup message (0x1B)
                popup = build_popup_packet("Character Successfully Created", disconnect=False)
                conn.sendall(popup)
                print(f"[{session.addr}] [PKT0x17] Sent 0x1B popup message")


            elif pkt == 0x16:
                name = BitReader(data[4:]).read_method_26()
                for c in session.char_list:
                    if c["name"] == name:
                        session.current_character = name
                        current_level = c.get("CurrentLevel", {}).get("name", "CraftTown")
                        session.current_level = current_level
                        c["user_id"] = session.user_id
                        # Set default PreviousLevel if unset
                        prev_name = c.get("PreviousLevel", {}).get("name", "NewbieRoad")
                        tk = session.ensure_token(c, target_level=current_level, previous_level=prev_name)
                        session.clientEntID = tk
                        session_by_token[tk] = session
                        _level_add(current_level, session)
                        level_config = LEVEL_CONFIG.get(current_level, ("LevelsNR.swf/a_Level_NewbieRoad", 1, 1, False))
                        # detect hard mode (Dread levels)
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
                            new_moment=new_moment,# momentParamsString
                            new_alter=new_alter, # alterParamsString
                            new_is_dungeon=level_config[3],
                            new_has_coord=False,
                            new_x=0,
                            new_y=0,
                            char=c
                        )
                        session.conn.sendall(pkt_out)
                        pending_world[tk] = (c, current_level, prev_name)
                        # Save updated char_list to ensure PreviousLevel is set
                        session.char_list = load_characters(session.user_id)
                        for i, char in enumerate(session.char_list):
                            if char["name"] == name:
                                session.char_list[i] = c
                                break
                        save_characters(session.user_id, session.char_list)
                        print(f"[{session.addr}] Transfer begin: {name}, tk={tk}, level={current_level}")
                        break
            #TODO...
            #the 0x1f and 0x1D needs to be rewritten and organised since the code is a mess
            elif pkt == 0x1f:
                if len(data) < 6:
                    print(f"[{session.addr}] Error: Packet 0x1f too short, len={len(data)}")
                    continue
                token = int.from_bytes(data[4:6], 'big')

                entry = used_tokens.get(token) or pending_world.get(token)
                # do not pop; tokens are persistent now
                if entry is None:
                    if len(pending_world) == 1:
                        token, entry = next(iter(pending_world.items()))
                    else:
                        print(f"[{session.addr}] Error: No entry found for token {token}, pending_world size={len(pending_world)}")
                        continue
                if len(entry) == 2:
                    char, target_level = entry
                    previous_level = session.current_level or char.get("PreviousLevel", {}).get("name", "NewbieRoad")
                else:
                    char, target_level, previous_level = entry
                    if isinstance(previous_level, dict):
                        previous_level = previous_level.get("name", "NewbieRoad")
                if char is None:
                    print(f"[{session.addr}] Error: Character is None for token {token}")
                    continue
                is_dungeon = LEVEL_CONFIG.get(target_level, (None, None, None, False))[3]
                if is_dungeon:
                    session.entry_level = previous_level if previous_level else char.get("PreviousLevel", "NewbieRoad")
                else:
                    session.entry_level = None
                session.user_id = char["user_id"]
                if not session.user_id:
                    print(f"[{session.addr}] Error: session.user_id is None for token {token}")
                    continue
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
                print(f"[{session.addr}] Saved character {char['name']}: CurrentLevel={char['CurrentLevel']}, PreviousLevel={char.get('PreviousLevel')}")
                pending_world.pop(token, None)
                session.current_level = target_level
                session.current_character = char["name"]
                session.current_char_dict = char
                current_characters[session.user_id] = session.current_character
                session.authenticated = True
                used_tokens[token] = (
                    char, target_level, session.current_level or char.get("PreviousLevel", "NewbieRoad"))
                # Calculate coordinates for Player_Data_Packet
                new_x, new_y, new_has_coord = get_spawn_coordinates(char, previous_level, target_level)
                user_id = session.user_id  # however you’re tracking the account
                send_ext = not extended_sent_map.get(user_id, {}).get("sent", False)
                welcome = Player_Data_Packet(
                    char,
                    transfer_token=token,
                    target_level=target_level,
                    new_x=int(round(new_x)),
                    new_y=int(round(new_y)),
                    new_has_coord=new_has_coord,
                    send_extended=send_ext
                )
                extended_sent_map[user_id] = {"sent": True, "last_seen": time.time()}
                conn.sendall(welcome)
                session.clientEntID = token
                print(f"[{session.addr}] Welcome: {char['name']} (token {token}) on level {session.current_level}, pos=({new_x},{new_y})")
                if session.current_character and session.char_list:
                    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
                    if char and session.current_level and "crafttown" in session.current_level.lower():
                        gears_list = get_inventory_gears(char)
                        print(f"[{session.addr}] Sending 0xF5 packet with {len(gears_list)} gears for Armory")
                        packet = build_level_gears_packet(gears_list)
                        conn.sendall(packet)
                    else:
                        print(f"[{session.addr}] Skipping 0xF5 packet: not in CraftTown or no character")
                else:
                    print(f"[{session.addr}] Skipping 0xF5 packet: no character selected")
                #TODO...
                npcs = ensure_level_npcs(session.current_level)

                # Send NPCs to the new player only
                for npc in npcs.values():
                    try:
                        payload = Send_Entity_Data(npc)
                        conn.sendall(struct.pack(">HH", 0x0F, len(payload)) + payload)
                        # Save them in the player's session entity map too
                        session.entities[npc["id"]] = npc
                    except Exception as e:
                        print(f"[{session.addr}] Error sending NPC {npc['id']} to {session.current_level}: {e}")

                print(f"[{session.addr}] NPCs synced for level {session.current_level}")


            # Level Transfer request
            elif pkt == 0x1D:
                br = BitReader(data[4:])
                try:
                    _old_token = br.read_method_9()
                    level_name = br.read_method_13()
                except Exception as e:
                    print(f"[{session.addr}] ERROR: Failed to parse 0x1D packet: {e}, raw payload = {data[4:].hex()}")
                    continue

                # 1) Pull the entry (no longer popped; tokens are persistent)
                entry = used_tokens.get(_old_token) or pending_world.get(_old_token)
                if not entry:
                    # try resolve by session token
                    s = session_by_token.get(_old_token)
                    if s:
                        entry = (
                        getattr(s, "current_char_dict", None) or {"name": s.current_character, "user_id": s.user_id},
                        s.current_level)
                if not entry:
                    print(f"[{session.addr}] ERROR: No character for token {_old_token}")
                    continue
                # 2) Unpack character and target_level
                char, target_level = entry[:2]
                # 3) Snapshot the level we're leaving (extract name if it’s a dict)
                raw = char.get("CurrentLevel")
                if isinstance(raw, dict):
                    old_level = raw.get("name", session.current_level or "NewbieRoad")
                else:
                    old_level = raw or session.current_level or "NewbieRoad"

                # 4) Clear player’s entity from old level to reflect they’ve left
                if session.clientEntID in session.entities:
                    del session.entities[session.clientEntID]
                    print(f"[{session.addr}] Removed entity {session.clientEntID} from level {old_level}")
                # 5) Bootstrap session with this character
                session.user_id = char.get("user_id")
                if not session.user_id:
                    print(f"[{session.addr}] ERROR: char['user_id'] missing for {char['name']}")
                    continue
                session.char_list = load_characters(session.user_id)
                session.current_character = char["name"]
                session.authenticated = True
                # 6) If the packet's level_name is empty, fallback
                if not level_name:
                    level_name = target_level
                    print(f"[{session.addr}] WARNING: Empty level_name, using target_level={level_name}")
                # 7) Update the character record
                is_dungeon = LEVEL_CONFIG.get(level_name, (None, None, None, False))[3]

                # 7a) Save current level’s coords to PreviousLevel
                prev_rec = char.get("CurrentLevel", {})
                prev_x = prev_rec.get("x", 0.0)
                prev_y = prev_rec.get("y", 0.0)
                char["PreviousLevel"] = {
                    "name": old_level,
                    "x": prev_x,
                    "y": prev_y
                }
                # 7b) Determine coordinates for the new level
                new_x, new_y, new_has_coord = get_spawn_coordinates(char, old_level, level_name)
                # 7c) Update CurrentLevel (skip coords for dungeons unless CraftTown)
                if not is_dungeon or level_name == "CraftTown":
                    char["CurrentLevel"] = {"name": level_name, "x": new_x, "y": new_y}
                save_characters(session.user_id, session.char_list)

                # 8) Write back into session.char_list and save
                for i, c in enumerate(session.char_list):
                    if c["name"] == char["name"]:
                        session.char_list[i] = char
                        break
                else:
                    session.char_list.append(char)
                save_characters(session.user_id, session.char_list)
                print(f"[{session.addr}] Saved character {char['name']}: "f"CurrentLevel={char['CurrentLevel']}, PreviousLevel={char['PreviousLevel']}")

                # 9) Update session.current_level
                session.current_level = level_name
                session.world_loaded = False
                # 10) For testing purposes only; uncomment to broadcast level change, remove after testing
                #broadcast_level_change(session, char["name"], level_name)
                # 11) Issue the new transfer token

                # Keep the same transfer token (persistent per session)
                new_token = session.ensure_token(
                    char,
                    target_level=level_name,
                    previous_level=old_level
                )
                pending_world[new_token] = (char, level_name, old_level)

                # 12) Build and send the ENTER_WORLD packet, including info about the level we just left
                #    old_level     := the name of the level we departed
                #    prev_rec      := char["PreviousLevel"] ⟶ {name, x, y}
                #    old_swf       := its SWF path
                #    old_has_coord := True if we have stored coords
                old_name = old_level
                prev_rec = char.get("PreviousLevel", {})
                prev_x = prev_rec.get("x", 0)
                prev_y = prev_rec.get("y", 0)
                old_swf, _, _, old_is_inst = LEVEL_CONFIG.get(old_name, ("", 0, 0, False))
                old_has_coord = ("x" in prev_rec and "y" in prev_rec)

                swf_path, map_id, base_id, is_inst = LEVEL_CONFIG[level_name]
                is_hard = level_name.endswith("Hard")
                new_moment = "Hard" if is_hard else ""
                new_alter = "Hard" if is_hard else ""

                pkt_out = build_enter_world_packet(
                    transfer_token=new_token,
                    old_level_id=0,
                    # tell the client what we just left
                    old_swf = old_swf,
                    has_old_coord  = old_has_coord,
                    old_x = int(round(prev_x)),
                    old_y = int(round(prev_y)),

                    host="127.0.0.1",
                    port=8080,
                    # New level the player is entering
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
                session.conn.sendall(pkt_out)
                print(f"[{session.addr}] Sent ENTER_WORLD with token {new_token} for level {level_name}, pos=({new_x},{new_y})")

            elif pkt == 0x2D:
                br = BitReader(data[4:])
                try:
                    door_id = br.read_method_9()
                except Exception as e:
                    print(f"[{session.addr}] ERROR: Failed to parse 0x2D packet: {e}, raw payload = {data[4:].hex()}")
                    continue
                print(f"[{session.addr}] OpenDoor request: doorID={door_id}, current_level={session.current_level}")
                is_dungeon = LEVEL_CONFIG.get(session.current_level, (None, None, None, False))[3]
                # Determine target level
                target_level = None
                if is_dungeon and door_id in (0, 1, 2):
                    target_level = session.entry_level
                    if not target_level:
                        print(f"[{session.addr}] Error: No entry_level set for door {door_id} in dungeon {session.current_level}")

                        continue
                elif door_id == 999:
                    target_level = "CraftTown"
                else:
                    target_level = DOOR_MAP.get((session.current_level, door_id))
                if target_level:
                    if target_level not in LEVEL_CONFIG:
                        print(f"[{session.addr}] Error: Target level {target_level} not found in LEVEL_CONFIG")
                        continue
                    # Send DOOR_TARGET response
                    bb = BitBuffer()
                    bb.write_method_4(door_id)
                    bb.write_method_13(target_level)
                    payload = bb.to_bytes()
                    resp = struct.pack(">HH", 0x2E, len(payload)) + payload
                    session.conn.sendall(resp)
                    print(f"[{session.addr}] Sent DOOR_TARGET: doorID={door_id}, level='{target_level}'")
                    # Reset world state
                    session.world_loaded = False
                    session.entities.clear()
                else:
                    print(f"[{session.addr}] Error: No target for door {door_id} in level {session.current_level}")

            #elif pkt == 0x1E:  # MASTER_CLIENT (dev mode)
                #rd = BitReader(data[4:], debug=False)
                #map_id = rd.read_method_9()
                # = rd.read_method_15() == 1
                #print(f"[DEBUG] MASTER_CLIENT: map_id={map_id}, first={is_first}")
                # Always use dummy char in dev flow
                #session.current_level = "NewbieRoad"  # or use DevSettings.standAloneMapInternalName if you parse it
                #session.current_character = DEV_DUMMY_CHAR["name"]
                #session.current_char_dict = DEV_DUMMY_CHAR
                #session.user_id = "dev"
                #player_packet = Player_Data_Packet(
                    #DEV_DUMMY_CHAR,
                    #transfer_token=map_id,
                    #send_extended=True,
                    #target_level=session.current_level
                #)
                #session.conn.sendall(player_packet)
                #print(f"[DEBUG] Sent Player_Data_Packet (0x10) using DEV_DUMMY_CHAR")
                # IMPORTANT: do NOT spawn NPCs in dev mode
                # The client will handle spawning monsters/entities itself because
                # DEVFLAG_MASTER_CLIENT + DEVFLAG_SPAWN_MONSTERS are set.

            elif pkt == 0xA4:
                pass

            # Level & Door related packets
            ###################################
            elif pkt == 0x41:
                handle_request_door_state(session, data, conn)
            elif pkt == 0x7D:
                handle_change_offset_y(session, data)
            ###################################

            #Entity Update Related packets
            ###################################
            elif pkt == 0x07:# Done
                handle_entity_incremental_update(session, data, all_sessions)
            elif pkt == 0xA2:# Done
                handle_linkupdater(session, data, all_sessions)
            elif pkt == 0x09:# Done
                handle_power_cast(session, data, all_sessions)
            elif pkt == 0x08:  # Done
                handle_entity_full_update(session, data, all_sessions)
            ###################################


              # Combat Related packets
            ############################################
            elif pkt == 0x0D: # Done
               handle_entity_destroy(session, data, all_sessions)
            elif pkt == 0x79: # Done
               PKTTYPE_BUFF_TICK_DOT(session, data, all_sessions)
            elif pkt == 0x82: # Done
               handle_respawn_ack(session, data, all_sessions)
            elif pkt == 0x77:# Done
                handle_request_respawn(session, data, all_sessions)
            elif pkt == 0x2A:
                handle_grant_reward(session, data, all_sessions)
            elif pkt == 0x0A:# Done
                handle_power_hit(session, data, all_sessions)
            elif pkt == 0x0E:# Done
                handle_projectile_explode(session, data, all_sessions)
            elif pkt == 0x0B:# Done
                handle_add_buff(session, data, all_sessions)
            elif pkt == 0x0C:# Done
                handle_remove_buff(session, data, all_sessions)
            elif pkt == 0x8A:
                handle_change_max_speed(session, data, all_sessions)
            ############################################


            #Login Screen
            ############################################
            elif pkt == 0x19:# Done
                PaperDoll_Request(session, data, conn)
            ############################################


            #Chatting messages NPC talking Emotes etc...
            ############################################
            elif pkt == 0x2C:# Done
                handle_public_chat(session, data, all_sessions)
            elif pkt == 0xC5:# Done
                handle_start_skit(session, data,all_sessions)
            elif pkt == 0x46:# Done
                handle_private_message(session, data, all_sessions)
            elif pkt == 0x7E:# Done
               handle_emote_begin(session, data, all_sessions)
            elif pkt == 0x113:
                #handle_alert_update(session, data)
                pass
            elif pkt == 0x7A:
                handle_talk_to_npc(session, data, all_sessions)
                pass
            ############################################


            # Group Related packets
            ############################################
            elif pkt == 0x65:# Done
                handle_group_invite(session, data, all_sessions)
            ############################################


            # Skill Related packets
            ############################################
            elif pkt == 0xBD:# Done
                handle_hotbar_packet(session, data)  # Equipped skills
            elif pkt == 0xCC:# Done
                # Client sends this when a new skill is equipped,
                # actual hotbar update follows in 0xBD.
                pass
            elif pkt == 0xBE:# Done
                Start_Skill_Research(session, data, conn)
            elif pkt == 0xD1:# Done
                handle_research_claim(session)
            elif pkt == 0xDD:# Done
                Skill_Research_Cancell_Request(session)
            elif pkt == 0xDE:# Done
                Skill_SpeedUp(session, data)
            ############################################


            # Entity Visuals related packets
            ############################################
            elif pkt == 0x8E:# Done
                handle_change_look(session, data, all_sessions)
            elif pkt == 0xBA:# Done
                payload = data[4:]
                handle_apply_dyes(session, payload, all_sessions)
            ############################################


           # Barn and pets related packets
            ############################################
            elif pkt == 0xB2:# Done
                handle_mount_equip_packet(session, data, all_sessions)
            elif pkt == 0xB3:# Done
                handle_pet_info_packet(session, data, all_sessions)
            elif pkt == 0xEA:
                handle_collect_hatched_egg(session, data)
                pass
            ############################################


            # Gear Set Related Packets
            ############################################
            elif pkt == 0xC8:# Done
                handle_name_gearset(session, data)
            elif pkt == 0xC7:# Done
                handle_create_gearset(session, data)
            elif pkt == 0xC6:# Done
                handle_apply_gearset(session, data)
            ############################################


            # Gear Related packets
            ############################################
            elif pkt == 0xB0:# Done
                handle_rune_packet(session, data) # equips runes on weapon slots
            elif pkt == 0x31:# Done
                handle_gear_packet(session, data)
            elif pkt == 0x30:# Done
                handle_update_equipment(session, data)
            ############################################


            #TODO...
            # Forge related packets
            ############################################
            elif pkt == 0xE2:
                magic_forge_packet(session, data)
            elif pkt == 0xD0:
                collect_forge_charm(session, data)
            elif pkt == 0xB1:
                start_forge_packet(session, data)
            elif pkt == 0xE1:
                cancel_forge_packet(session, data)
            elif pkt == 0x110:
                use_forge_xp_consumable(session, data)
            elif pkt == 0xD3:
                allocate_talent_points(session, data)
            ############################################


            ############################################
            elif pkt == 0xD2 :# Done
                handle_respec_talent_tree(session, data)
            elif pkt == 0xC0:# Done
                allocate_talent_tree_points(session,data)
            elif pkt == 0xD6:# Done
                handle_talent_claim(session, data)
            elif pkt == 0xE0:# Done
                handle_talent_speedup(session, data)
            elif pkt == 0xD4:# Done
                handle_train_talent_point(session, data)
            elif pkt == 0xDF:# Done
                handle_clear_talent_research(session, data)
            ############################################


            # LockBox related packets
            ###################################
            elif pkt == 0x107:
                payload = data[4:]
                handle_lockbox_reward(session)
            ###################################


            # Master class related packets
            ############################################
            elif pkt == 0xC3:# Done
                handle_masterclass_packet(session, data)
            ############################################


            # client crash Reports
            ############################################
            elif pkt == 0x7C:
                Client_Crash_Reports(session, data)
            ############################################


            # Buildings Upgrade packets
            ############################################
            elif pkt == 0xDB:# Done
                handle_cancel_upgrade(session, data)
            elif pkt == 0xDC:# Done
                handle_speedup_request(session, data)
            elif pkt == 0xD7:# Done
                handle_building_upgrade(session, data)
            elif pkt == 0xD9:# Done
                handle_building_claim(session, data)
            ############################################




            elif pkt == 0xF0:
                handle_volume_enter(session, data)
            elif pkt == 0xBB:
                handle_hp_increase_notice(session, data)
                pass
            elif pkt == 0x78:
                handle_char_regen(session, data)
                pass
            elif pkt == 0x10E:
                pass

            else:
                print(f"[{session.addr}] Unhandled packet type: 0x{pkt:02X}, raw payload = {data.hex()}")
    except Exception as e:
        print("Session error:", e)
    finally:
        print("Disconnect:", addr)
        session.stop()

def start_server(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((HOST, port))
    except PermissionError:
        print(f"Error: Cannot bind to port {port}. Ports below 1024 require root privileges.")
        return None
    except OSError as e:
        print(f"Error: Cannot bind to port {port}. {e}")
        return None
    s.listen(5)
    print(f"Server listening on {HOST}:{port}")
    return s

def accept_connections(s, port):
    while True:
        conn, addr = s.accept()
        session = ClientSession(conn, addr)
        all_sessions.append(session)
        threading.Thread(target=handle_client, args=(session,), daemon=True).start()

def start_servers():
    servers = []
    for port in PORTS:
        server = start_server(port)
        if server:
            servers.append((server, port))
            threading.Thread(target=accept_connections, args=(server, port), daemon=True).start()
    return servers

if __name__ == "__main__":
    start_policy_server(host="127.0.0.1", port=843)
    start_static_server(host="127.0.0.1", port=80, directory="content/localhost")
    servers = start_servers()
    print("For Browser running on : http://localhost/index.html")
    print("For Flash Projector running on : http://localhost/p/cbv/DungeonBlitz.swf?fv=cbq&gv=cbv")


    #threading.Thread(target=run_admin_panel, args=(lambda: all_sessions, 5000)).start()
    #print("Debug Panel running on http://127.0.0.1:5000/")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down servers...")
        for server, port in servers:
            server.close()
        sys.exit(0)
