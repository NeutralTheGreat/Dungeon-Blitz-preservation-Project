import struct

from BitBuffer import BitBuffer
from constants import class_3, class_1, class_64, class_111, class_66

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
level_npcs = {}
level_players = {}

SECRET_HEX = "815bfb010cd7b1b4e6aa90abc7679028"
SECRET      = bytes.fromhex(SECRET_HEX)

def _level_add(level, session):
    s = level_registry.setdefault(level, set())
    s.add(session)

# Helpers
#############################################

def get_active_character_name(session) -> str:
    return session.current_character or "<unknown>"

def send_talent_point_research_complete(session, class_index: int):
    bb = BitBuffer()
    bb.write_method_6(class_index, class_66.const_571)  # 2 bits
    bb.write_method_6(1, 1)  # status = 1 (complete)
    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0xD5, len(payload)) + payload
    session.conn.sendall(packet)

def send_building_complete_packet(session, building_id: int, rank: int):
    bb = BitBuffer()
    bb.write_method_6(building_id, 5)  # class_9.const_129
    bb.write_method_6(rank, 5)         # class_9.const_28
    bb.write_method_15(True)           # complete flag
    payload = bb.to_bytes()
    session.conn.sendall(struct.pack(">HH", 0xD8, len(payload)) + payload)
    print(f"[{session.addr}] Sent 0xD8 building complete → id={building_id}, rank={rank}")

def send_skill_complete_packet(session, ability_id: int):
    bb = BitBuffer()
    bb.write_method_6(ability_id, 7)
    payload = bb.to_bytes()
    session.conn.sendall(struct.pack(">HH", 0xBF, len(payload)) + payload)
    print(f"[{session.addr}] Sent 0xBF complete for abilityID={ability_id}")

# updates players consumables inventory when a  consumable is used
def send_consumable_update(conn, consumable_id: int, new_count: int):
    bb = BitBuffer()
    bb.write_method_6(consumable_id, class_3.const_69)
    bb.write_method_4(new_count)
    body = bb.to_bytes()
    packet = struct.pack(">HH", 0x10C, len(body)) + body
    conn.sendall(packet)

def build_start_skit_packet(entity_id: int, dialogue_id: int = 0, mission_id: int = 0) -> bytes:
    """
    Build packet for client to start a skit/dialogue.
    entity_id: The NPC's entity ID.
    dialogue_id: Which dialogue to show (0–5).
    mission_id: Currently unused, but protocol reserves it.
    dialogue ID should always be 0 for NPCs with no linked missions
    """
    bb = BitBuffer()
    bb.write_method_4(entity_id)        # Entity ID
    bb.write_method_6(dialogue_id, 3)   # Dialogue ID (3 bits)
    bb.write_method_4(mission_id)       # Mission ID (reserved / unused for now)
    payload = bb.to_bytes()
    return struct.pack(">HH", 0x7B, len(payload)) + payload

def send_npc_dialog(session, npc_id, text):
    bb = BitBuffer()
    bb.write_method_4(npc_id)
    bb.write_method_13(text)
    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0x76, len(payload)) + payload
    session.conn.sendall(packet)
    print(f"[DEBUG] Sent NPC dialog: {text}")

# this is required for every time MamothIdols Are used to make a purchase to update the current amount of Idols in the client
def send_premium_purchase(session, item_name: str, cost: int):
    bb = BitBuffer()
    bb.write_method_13(item_name)
    bb.write_method_4(cost)
    body = bb.to_bytes()
    packet = struct.pack(">HH", 0xB5, len(body)) + body
    session.conn.sendall(packet)
    print(f"[DEBUG] Deducted {cost} Mammoth Idols for {item_name}")

def _send_error(conn, msg):
    encoded = msg.encode("utf-8")
    payload = struct.pack(">H", len(encoded)) + encoded
    conn.sendall(struct.pack(">HH", 0x44, len(payload)) + payload)

def build_destroy_entity_packet(entity_id: int, is_player: bool = True) -> bytes:
    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_15(is_player)
    payload = bb.to_bytes()
    return struct.pack(">HH", 0x0D, len(payload)) + payload

def handle_entity_destroy_server(session, entity_id: int, is_player: bool, all_sessions: list):
    if session.entities.pop(entity_id, None) is None:
        print(f"[WARN] Tried to destroy unknown entity {entity_id}")

    pkt = build_destroy_entity_packet(entity_id, is_player)
    for s in all_sessions:
        if s.world_loaded and s.current_level == session.current_level:
            try:
                s.conn.sendall(pkt)
            except Exception:
                pass

    print(f"[EntityDestroy] Entity {entity_id} destroyed (is_player={is_player}) in level {session.current_level}")

def send_forge_reroll_packet(
    session,
    primary,
    roll_a,
    roll_b,
    tier,
    secondary,
    usedlist,
    action="reroll"
):
    bb = BitBuffer()

    # Primary charm info
    bb.write_method_6(primary, class_1.const_254)

    # forge_roll_a & forge_roll_b
    bb.write_method_91(int(roll_a))
    bb.write_method_91(int(roll_b))

    # Tier (secondary_tier)
    bb.write_method_6(tier, class_64.const_499)

    if tier:
        bb.write_method_6(secondary, class_64.const_218)
        bb.write_method_6(usedlist, class_111.const_432)

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0xCD, len(payload)) + payload
    session.conn.sendall(pkt)

    print(f"[Forge] Sent {action} packet → primary={primary}, tier={tier}, secondary={secondary}, usedlist={usedlist}")


def Client_Crash_Reports(session, data):
    _, length = struct.unpack_from(">HH", data, 0)
    payload = data[4:4 + length]
    msg = payload.decode("utf-8", errors="replace")
    print(f"[{session.addr}] CLIENT ERROR (0x7C): {msg}")
