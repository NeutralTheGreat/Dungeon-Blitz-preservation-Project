#!/usr/bin/env python3
import secrets
import socket
import sys
import threading
import time

from PKTTYPES import PACKET_HANDLERS
from PolicyServer import start_policy_server
from globals import all_sessions, HOST, PORTS, handle_entity_destroy_server, GS
from scheduler import set_active_session_resolver
from static_server import start_static_server
from Character import save_characters
from level_config import LEVEL_CONFIG


#===========#

ENABLE_ADMIN_PANEL = False

#===========#

def _level_remove(level, session):
    # Remove from registry
    s = GS.level_registry.get(level)
    if s and session in s:
        s.remove(session)

    # Remove from level_players
    players = GS.level_players.get(level)
    if players:
        GS.level_players[level] = [
            p for p in players if p.get("session") is not session
        ]


def new_transfer_token():
    """Allocate a persistent 16-bit token not in use."""
    while True:
        t = secrets.randbits(16)
        if t not in GS.session_by_token:
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
        self.player_spawned = False
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


    def ensure_token(self, char, target_level=None, previous_level=None):
        key = (self.user_id, char.get("name"))

        # Look up or assign a token
        if key in GS.char_tokens:
            tk = GS.char_tokens[key]
        else:
            tk = new_transfer_token()
            GS.char_tokens[key] = tk
            GS.token_char[tk] = key

        # Store session mapping
        self.clientEntID = tk
        GS.session_by_token[tk] = self

        return tk

    def save_player_position(self):
        if not (self.user_id and self.char_list and self.current_character):
            return

        char = next((c for c in self.char_list if c.get("name") == self.current_character), None)
        if not char:
            return

        current_level = self.current_level
        ent = self.entities.get(self.clientEntID)

        if not (current_level and ent):
            return

        # Determine whether saving is allowed
        is_dungeon = LEVEL_CONFIG.get(current_level, ("", 0, 0, False))[3]
        allow_save = (current_level == "CraftTown") or not is_dungeon

        if not allow_save:
            return

        # ONLY update coords, never the level name here
        char["CurrentLevel"]["x"] = ent.get("pos_x", 0)
        char["CurrentLevel"]["y"] = ent.get("pos_y", 0)

        save_characters(self.user_id, self.char_list)

        #print(
        #    f"[{self.addr}] Saved player position: "
        #    f"{char['CurrentLevel']['name']} → "
        #    f"({char['CurrentLevel']['x']}, {char['CurrentLevel']['y']})"
        #)

    def close_connection(self):

        self.save_player_position()

        if self.player_spawned and self.clientEntID is not None:
            handle_entity_destroy_server(self, self.clientEntID, all_sessions=all_sessions)
            #print("destroyed entity removal")

        try:
            self.conn.close()
        except:
            pass

        s = GS.session_by_token.get(self.clientEntID)
        if s:
            s.running = False

        if self.player_spawned and self.current_level:
            _level_remove(self.current_level, self)

        if self in all_sessions:
            all_sessions.remove(self)


def handle_client(session: ClientSession):
    conn = session.conn
    addr = session.addr
    print("Connected:", addr)
    conn.settimeout(300)
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

                # Sanity check
                if len(payload) != length:
                    print(f"[{addr}] Length mismatch: header says {length} but payload is {len(payload)}")

                handler = PACKET_HANDLERS.get(pkt)

                if handler:
                    handler(session, data)
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

    if ENABLE_ADMIN_PANEL:
        try:
            from admin_panel import run_admin_panel

            threading.Thread(target=run_admin_panel,args=(lambda: all_sessions, 5000),daemon=True).start()
            print("Debug Panel running on http://127.0.0.1:5000/")
        except ModuleNotFoundError:
            print(
                """
        ------------------------------------------------------------------------------------------
        Flask is not installed. Admin panel disabled.

        If you want to use the admin panel you need to install Flask:

        Enter this command in the command prompt => pip install flask

        Then restart the server.
        ------------------------------------------------------------------------------------------
                """
            )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down servers...")
        for server, port in servers:
            server.close()
        sys.exit(0)