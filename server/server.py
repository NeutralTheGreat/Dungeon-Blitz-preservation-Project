#!/usr/bin/env python3
import secrets
import socket
import sys
import threading
import time

from Character import save_characters
from Commands import  handle_gear_packet, \
    handle_apply_dyes, handle_equip_rune, handle_change_look, handle_create_gearset, handle_name_gearset, \
    handle_apply_gearset, handle_update_equipment, handle_private_message, \
    handle_public_chat, handle_group_invite, handle_entity_incremental_update, PaperDoll_Request, handle_hp_increase_notice, handle_volume_enter, \
    handle_change_offset_y, handle_start_skit, handle_lockbox_reward, handle_linkupdater, \
    handle_emote_begin, handle_mount_equip_packet, handle_pet_info_packet, \
    handle_collect_hatched_egg, handle_talk_to_npc, handle_char_regen, handle_request_armory_gears
from talent import handle_respec_talent_tree, handle_allocate_talent_tree_points, handle_talent_claim, \
    handle_talent_speedup, \
    handle_train_talent_point, handle_clear_talent_research, handle_active_talent_change_request
from skills import handle_skill_trained_claim, handle_skill_research_cancel_request, handle_skill_speed_up_request, handle_start_skill_training, \
    handle_equip_active_skills
from PolicyServer import start_policy_server
from Forge import handle_forge_speed_up_packet, handle_start_forge, handle_collect_forge_charm, handle_cancel_forge, \
    handle_use_forge_xp_consumable, handle_allocate_magic_forge_artisan_skill_points, handle_magic_forge_reroll
from buildings import handle_building_claim, handle_building_upgrade, handle_building_speed_up_request, \
    handle_cancel_building_upgrade
from combat import handle_entity_destroy, handle_buff_tick_dot, handle_respawn_broadcast, handle_request_respawn, \
    handle_grant_reward, handle_power_hit, handle_projectile_explode, handle_add_buff, handle_remove_buff, \
    handle_change_max_speed, handle_power_cast
from entity import handle_entity_full_update
from globals import level_registry, session_by_token, all_sessions, char_tokens, token_char, extended_sent_map, HOST, \
    PORTS, Client_Crash_Reports
from level_config import handle_open_door, handle_level_transfer_request, handle_request_door_state, LEVEL_CONFIG
from login import handle_login_version, handle_login_create, handle_login_authenticate, handle_login_character_create, \
    handle_character_select, handle_gameserver_login
from scheduler import set_active_session_resolver
from static_server import start_static_server


def _level_remove(level, session):
    s = level_registry.get(level)
    if s and session in s:
        s.remove(session)
        if not s:
            level_registry.pop(level, None)

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
        self.close_connection()

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def issue_token(self, char, target_level, previous_level):
        tk = self.ensure_token(char, target_level=target_level, previous_level=previous_level)
        return tk

    def ensure_token(self, char, target_level=None, previous_level=None):
        key = (self.user_id, char.get("name"))
        if key in char_tokens:
            tk = char_tokens[key]
        else:
            tk = new_transfer_token()
            char_tokens[key] = tk
            token_char[tk] = key

        self.clientEntID = tk
        session_by_token[tk] = self
        return tk

    def save_player_position(self):
        """Save player position if not in a dungeon or if in CraftTown."""
        try:
            if not (self.user_id and self.char_list and self.current_character):
                return

            for char in self.char_list:
                if char.get("name") == self.current_character:
                    current_level = getattr(self, "current_level", None)
                    ent = self.entities.get(self.clientEntID, {})

                    if current_level and ent:
                        # check dungeon flag
                        is_dungeon = LEVEL_CONFIG.get(current_level, (None, None, None, False))[3]
                        if not is_dungeon or current_level == "CraftTown":
                            char["CurrentLevel"] = {
                                "name": current_level,
                                "x": ent.get("pos_x", 0),
                                "y": ent.get("pos_y", 0),
                            }
                            save_characters(self.user_id, self.char_list)
                            print(
                                f"[{self.addr}] Saved character {self.current_character}: "
                                f"{char.get('CurrentLevel', {})}"
                            )
                    break

        except Exception as e:
            print(f"[{self.addr}] Error saving player position: {e}")

    def close_connection(self):
        try:
            self.conn.close()
        except:
            pass

        try:
            self.save_player_position()  # replaces old coordinate-saving logic
        except Exception as e:
            print(f"[{self.addr}] Error saving on disconnect: {e}")

        s = session_by_token.get(self.clientEntID)
        if s:
            s.running = False

        if self.current_level:
            _level_remove(self.current_level, self)

        if self in all_sessions:
            all_sessions.remove(self)

        if self.user_id in extended_sent_map:
            extended_sent_map[self.user_id]["last_seen"] = time.time()


def prune_extended_sent_map(timeout: int = 2):
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
    prune_extended_sent_map(timeout=2)
    buffer = bytearray()
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                print(f"[{addr}] Connection closed by client")
                break
            buffer.extend(chunk)
            while len(buffer) >= 4:
                pkt    = int.from_bytes(buffer[0:2], byteorder='big')
                length = int.from_bytes(buffer[2:4], byteorder='big')
                total  = 4 + length
                if len(buffer) < total:
                    break
                data    = bytes(buffer[:total])
                payload = data[4:]
                del buffer[:total]
                # Debug‐print
               #print(f"[{addr}] Framed pkt=0x{pkt:02X} length={length} payload_bytes={len(payload)}")

                # Sanity check
                if len(payload) != length:
                    print(f"[{addr}] ⚠️ Length mismatch: header says {length} but payload is {len(payload)}")

            #Login Screen
            ############################################
            if pkt == 0x11:
                handle_login_version(session, data, conn)
            elif pkt == 0x19:
                PaperDoll_Request(session, data, conn)
            elif pkt == 0x13:
                handle_login_create(session, data, conn)
            elif pkt == 0x14:
                handle_login_authenticate(session, data, conn)
            elif pkt == 0x17:
                handle_login_character_create(session, data, conn)
            elif pkt == 0x16:
                handle_character_select(session, data, conn)
            elif pkt == 0x1f:# --- 0x1F: Welcome / Player_Data (finalize level transfer and spawn NPCs) ---
                handle_gameserver_login(session, data, conn)
            ############################################

            # Level & Door related packets
            ###################################
            elif pkt == 0x1D:# --- 0x1D: Transfer Ready (prepare ENTER_WORLD, do NOT finalize session.current_level) ---
                handle_level_transfer_request(session, data, conn)
            elif pkt == 0x2D:
                handle_open_door(session, data, conn)
            elif pkt == 0x41:
                handle_request_door_state(session, data, conn)
            elif pkt == 0x7D:
                handle_change_offset_y(session, data)
            ###################################

            #Entity Update Related packets
            ###################################
            elif pkt == 0x07:
                handle_entity_incremental_update(session, data, all_sessions)
            elif pkt == 0xA2:
                handle_linkupdater(session, data, all_sessions)
            elif pkt == 0x09:
                handle_power_cast(session, data, all_sessions)
            elif pkt == 0x08:
                handle_entity_full_update(session, data, all_sessions)
            ###################################

              # Combat Related packets
            ############################################
            elif pkt == 0x0D:
               handle_entity_destroy(session, data, all_sessions)
            elif pkt == 0x79:
               handle_buff_tick_dot(session, data, all_sessions)
            elif pkt == 0x82:
               handle_respawn_broadcast(session, data, all_sessions)
            elif pkt == 0x77:
                handle_request_respawn(session, data)
            elif pkt == 0x2A:
                handle_grant_reward(session, data, all_sessions)
            elif pkt == 0x0A:
                handle_power_hit(session, data, all_sessions)
            elif pkt == 0x0E:
                handle_projectile_explode(session, data, all_sessions)
            elif pkt == 0x0B:
                handle_add_buff(session, data, all_sessions)
            elif pkt == 0x0C:
                handle_remove_buff(session, data, all_sessions)
            elif pkt == 0x8A:
                handle_change_max_speed(session, data, all_sessions)
            ############################################

            #Chatting messages NPC talking Emotes etc...
            ############################################
            elif pkt == 0x2C:
                handle_public_chat(session, data, all_sessions)
            elif pkt == 0xC5:
                handle_start_skit(session, data,all_sessions)
            elif pkt == 0x46:
                handle_private_message(session, data, all_sessions)
            elif pkt == 0x7E:
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
            elif pkt == 0x65:
                handle_group_invite(session, data, all_sessions)
            ############################################

            # Skill Related packets
            ############################################
            elif pkt == 0xBD:
                handle_equip_active_skills(session, data)
            elif pkt == 0xBE:
                handle_start_skill_training(session, data, conn)
            elif pkt == 0xD1:
                handle_skill_trained_claim(session)
            elif pkt == 0xDD:
                handle_skill_research_cancel_request(session)
            elif pkt == 0xDE:
                handle_skill_speed_up_request(session, data)
            ############################################

            # Entity Visuals related packets
            ############################################
            elif pkt == 0x8E:
                handle_change_look(session, data, all_sessions)
            elif pkt == 0xBA:
                payload = data[4:]
                handle_apply_dyes(session, payload, all_sessions)
            ############################################

           # Barn and pets related packets
            ############################################
            elif pkt == 0xB2:
                handle_mount_equip_packet(session, data, all_sessions)
            elif pkt == 0xB3:
                handle_pet_info_packet(session, data, all_sessions)
            elif pkt == 0xEA:
                handle_collect_hatched_egg(session, data)
            ############################################

            # Gear Set Related Packets
            ############################################
            elif pkt == 0xC8:
                handle_name_gearset(session, data)
            elif pkt == 0xC7:
                handle_create_gearset(session, data)
            elif pkt == 0xC6:
                handle_apply_gearset(session, data)
            ############################################

            # Gear Related packets
            ############################################
            elif pkt == 0xB0:
                handle_equip_rune(session, data)
            elif pkt == 0x31:
                handle_gear_packet(session, data)
            elif pkt == 0x30:
                handle_update_equipment(session, data)
            elif pkt == 0xF4:
                handle_request_armory_gears(session, data, conn)
            ############################################

            ############################################
            elif pkt == 0xE2:
                handle_forge_speed_up_packet(session, data)
            elif pkt == 0xD0:
                handle_collect_forge_charm(session, data)
            elif pkt == 0xB1:
                handle_start_forge(session, data)
            elif pkt == 0xE1:
                handle_cancel_forge(session, data)
            elif pkt == 0x110:
                handle_use_forge_xp_consumable(session, data)
            elif pkt == 0xD3:
                handle_allocate_magic_forge_artisan_skill_points(session, data)
            elif pkt == 0xCF:
                handle_magic_forge_reroll(session, data)
            ############################################

            ############################################
            elif pkt == 0xD2:
                handle_respec_talent_tree(session, data)
            elif pkt == 0xC0:
                handle_allocate_talent_tree_points(session, data)
            elif pkt == 0xD6:
                handle_talent_claim(session, data)
            elif pkt == 0xE0:
                handle_talent_speedup(session, data)
            elif pkt == 0xD4:
                handle_train_talent_point(session, data)
            elif pkt == 0xDF:
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
            elif pkt == 0xC3:
                handle_active_talent_change_request(session, data)
            ############################################

            # client crash Reports
            ############################################
            elif pkt == 0x7C:
                Client_Crash_Reports(session, data)
            ############################################

            # Buildings Upgrade packets
            ############################################
            elif pkt == 0xDB:
                handle_cancel_building_upgrade(session, data)
            elif pkt == 0xDC:
                handle_building_speed_up_request(session, data)
            elif pkt == 0xD7:
                handle_building_upgrade(session, data)
            elif pkt == 0xD9:
                handle_building_claim(session, data)
            ############################################

            # Misc
            ############################################
            elif pkt == 0xCC:# Client sends this when a new skill is equipped,actual hotbar update follows in 0xBD.
                pass
            elif pkt == 0x78:
                handle_char_regen(session, data)
            elif pkt == 0xF0:
                handle_volume_enter(session, data)
            elif pkt == 0xBB:
                handle_hp_increase_notice(session, data)
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