import random
import struct
import time

from BitBuffer import BitBuffer
from constants import class_3, class_1, class_64, class_111, class_66, GearType, EGG_TYPES, class_16, class_7

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
level_npcs = {}
level_players = {}

SECRET_HEX = "815bfb010cd7b1b4e6aa90abc7679028"
SECRET      = bytes.fromhex(SECRET_HEX)

def _level_add(level, session):
    s = level_registry.setdefault(level, set())
    s.add(session)

# Helpers
#############################################

def send_chat_status(session, text: str):
    """
    Send PKTTYPE_CHAT_STATUS (0x44) to show a chat status message
    such as 'Player not found' or 'You cannot friend yourself'.
    """
    bb = BitBuffer()
    bb.write_method_13(text)

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x44, len(payload)) + payload
    session.conn.sendall(pkt)

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

def build_destroy_entity_packet(entity_id: int) -> bytes:
    bb = BitBuffer()
    bb.write_method_4(entity_id)  # Entity ID
    bb.write_method_15(False) # Boolean (1 bit) - client currently ignores this
    payload = bb.to_bytes()
    return struct.pack(">HH", 0x0D, len(payload)) + payload

def handle_entity_destroy_server(session, entity_id: int, all_sessions: list):
    # Remove locally
    session.entities.pop(entity_id, None)

    # Build packet once
    pkt = build_destroy_entity_packet(entity_id)

    # Send to everyone in same level
    for s in all_sessions:
        if s.player_spawned and s.current_level == session.current_level:
            s.conn.sendall(pkt)

    print(f"[EntityDestroy] Entity {entity_id} destroyed")


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

def build_room_thought_packet(entity_id: int, text: str) -> bytes:
    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_13(text)
    body = bb.to_bytes()
    return struct.pack(">HH", 0x76, len(body)) + body

def build_change_offset_y_packet(entity_id: int, offset_y: int) -> bytes:
    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_739(offset_y)
    payload = bb.to_bytes()
    return struct.pack(">HH", 0x7D, len(payload)) + payload


def build_empty_group_packet():
    bb = BitBuffer()
    bb.write_method_15(False)  # no group
    body = bb.to_bytes()
    return struct.pack(">HH", 0x75, len(body)) + body


def build_group_chat_packet(sender: str, message: str) -> bytes:
    bb = BitBuffer()
    bb.write_method_13(sender)
    bb.write_method_13(message)
    body = bb.to_bytes()
    return struct.pack(">HH", 0x64, len(body)) + body


def build_groupmate_map_packet(sess, x, y):
    bb = BitBuffer()

    # name of the player whose coords are being updated
    bb.write_method_26(sess.current_character)
    bb.write_method_91(x)
    bb.write_method_91(y)

    body = bb.to_bytes()
    return struct.pack(">HH", 0x8C, len(body)) + body

def send_deduct_sigils(session, amount):
    bb = BitBuffer()
    bb.write_method_4(amount)
    pkt = struct.pack(">HH", 0x10F, len(bb.to_bytes())) + bb.to_bytes()
    session.conn.sendall(pkt)

def send_mount_reward(session, mount_id, suppress=False):
    bb = BitBuffer()
    bb.write_method_4(mount_id)
    bb.write_method_11(1 if suppress else 0, 1)
    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x36, len(payload)) + payload
    session.conn.sendall(pkt)

def send_gold_reward(session, amount, show_fx=False):
    bb = BitBuffer()
    bb.write_method_4(amount)
    bb.write_method_11(1 if show_fx else 0, 1)
    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x35, len(payload)) + payload
    session.conn.sendall(pkt)

def send_gear_reward(session, gear_id, tier=0, has_mods=False):
    bb = BitBuffer()
    bb.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)
    bb.write_method_6(tier, GearType.const_176)
    bb.write_method_11(1 if has_mods else 0, 1)
    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x33, len(payload)) + payload
    session.conn.sendall(pkt)


def build_hatchery_packet(eggs: list[int], reset_time: int):
    bb = BitBuffer()

    max_slots = class_16.const_1290
    trimmed = (eggs or [])[:max_slots]
    padded  = trimmed + [0] * (max_slots - len(trimmed))

    # Send the fixed count so client builds a Vector<uint> of that length
    bb.write_method_6(max_slots, class_16.const_167)

    # Egg IDs (0 means empty slot)
    for eid in padded:
        bb.write_method_6(eid, class_16.const_167)

    # Reset timestamp
    bb.write_method_4(reset_time)

    payload = bb.to_bytes()
    return struct.pack(">HH", 0xE5, len(payload)) + payload


def build_hatchery_notify_packet():
    return struct.pack(">HH", 0xFF, 0)


def pick_daily_eggs(count=3):
    """
    Picks 'count' random eggs from EGG_TYPES.
    """
    valid = [e for e in EGG_TYPES if e.get("EggID", 0) > 0]

    if len(valid) < count:
        return [e["EggID"] for e in valid]

    chosen = random.sample(valid, count)
    return [e["EggID"] for e in chosen]

def send_pet_training_complete(session, type_id):
    bb = BitBuffer()
    bb.write_method_6(type_id, class_7.const_19)
    bb.write_method_4(int(time.time()))

    body = bb.to_bytes()
    pkt = struct.pack(">HH", 0xEE, len(body)) + body
    session.conn.sendall(pkt)

def send_egg_hatch_start(session):
    egg_data = session.current_char_dict.get("EggHachery")
    egg_id = egg_data["EggID"]

    bb = BitBuffer()
    bb.write_method_6(egg_id, class_16.const_167)

    body = bb.to_bytes()
    pkt = struct.pack(">HH", 0xE7, len(body)) + body
    session.conn.sendall(pkt)

    print(f"[EGG] Sent hatch-start packet for egg {egg_id}")

def send_new_pet_packet(session, type_id, special_id, rank):
    bb = BitBuffer()
    bb.write_method_6(type_id, class_7.const_19)
    bb.write_method_4(special_id)
    bb.write_method_6(rank, class_7.const_75)
    bb.write_method_15(True)  # isNew = true

    body = bb.to_bytes()
    pkt = struct.pack(">HH", 0x37, len(body)) + body
    session.conn.sendall(pkt)

    print(f"[PET] Sent NEW PET : type={type_id}, special_id={special_id}, rank={rank}")

def send_server_shutdown_warning(seconds):
    bb = BitBuffer()
    bb.write_method_4(seconds)
    body = bb.to_bytes()

    pkt = struct.pack(">HH", 0x101, len(body)) + body

    for sess in all_sessions:
        sess.conn.sendall(pkt)

def send_admin_chat(msg, targets=None):
    """
    Sends an admin message to either:
      - a list of players
      - a single player
      - everyone if (targets=None)
    """
    bb = BitBuffer()
    bb.write_method_13(msg)
    body = bb.to_bytes()

    pkt = struct.pack(">HH", 0x102, len(body)) + body

    # If no targets are specified, then broadcast to everybody
    if targets is None:
        targets = all_sessions

    # If a single session is passed then wrap in list
    if not isinstance(targets, (list, tuple, set)):
        targets = [targets]

    # Send to all selected sessions
    for sess in targets:
            sess.conn.sendall(pkt)