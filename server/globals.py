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

SECRET_HEX = "815bfb010cd7b1b4e6aa90abc7679028"
SECRET      = bytes.fromhex(SECRET_HEX)

def _level_add(level, session):
    s = level_registry.setdefault(level, set())
    s.add(session)