import struct
import random
import time

from bitreader import BitReader
from constants import GearType, class_3
from BitBuffer import BitBuffer
from globals import build_start_skit_packet, GS
from missions import get_mission_extra


#TODO...
def handle_queue_potion(session, data):
    br = BitReader(data[4:])
    queued_potion_id = br.read_method_20(class_3.const_69)
    #print(f"queued potion ID : {queued_potion_id}")

# i have no clue what purpose does this payload serves
def handle_badge_request(session, data):
    br = BitReader(data[4:])
    badge_key = br.read_method_26()
    print(f"[0x8D] Badge request: {badge_key}")


#TODO...
def handle_talk_to_npc(session, data):

    br = BitReader(data[4:])
    npc_id = br.read_method_9()

    npc = session.entities.get(npc_id)
    if not npc:
        print(f"[{session.addr}] [PKT0x7A] Unknown NPC ID {npc_id}")
        return

    # NPC internal type name:
    # This is the ONLY correct name to compare missions with.
    ent_type = npc.get("Linked_Mission") or npc.get("entType") or npc.get("name")

    # Normalize
    def norm(x):
        return (x or "").replace(" ", "").replace("_", "").lower()

    npc_type_norm = norm(ent_type)

    # Default values
    dialogue_id = 0
    mission_id = 0

    # Player mission data
    char_data = session.current_char_dict or {}
    player_missions = char_data.get("missions", {})

    # Check mission matches
    for mid_str, mdata in player_missions.items():
        try:
            mid = int(mid_str)
        except:
            continue

        mextra = get_mission_extra(mid)
        if not mextra:
            continue

        # Mission-side names
        contact = norm(mextra.get("ContactName"))
        ret     = norm(mextra.get("ReturnName"))

        # Normalize them BEFORE matching (auto-map via Linked_Mission)
        if contact and contact != npc_type_norm:
            # Allow Linked_Mission to solve mismatches
            if norm(mextra.get("ContactName")) == norm(npc.get("Linked_Mission")):
                contact = npc_type_norm
        if ret and ret != npc_type_norm:
            if norm(mextra.get("ReturnName")) == norm(npc.get("Linked_Mission")):
                ret = npc_type_norm

        # Mission state
        state = mdata.get("state", 0)  # 0=not accepted, 1=active, 2=completed

        # Match: Offering the mission
        if npc_type_norm == contact:
            if state == 0:
                dialogue_id = 2  # OfferText
                mission_id = 0
                break
            elif state == 1:
                dialogue_id = 3  # ActiveText
                mission_id = mid
                break
            elif state == 2:
                dialogue_id = 5  # PraiseText
                mission_id = mid
                break

        # Returning the mission
        if npc_type_norm == ret:
            if state == 1:
                dialogue_id = 4  # ReturnText
                mission_id = mid
                break
            elif state == 2:
                dialogue_id = 5  # PraiseText
                mission_id = mid
                break

    pkt = build_start_skit_packet(npc_id, dialogue_id, mission_id)
    session.conn.sendall(pkt)

    print(
        f"[{session.addr}] [PKT0x7A] TalkToNPC id={npc_id} entType={ent_type} → "
        f"dialogue_id={dialogue_id}, mission_id={mission_id}"
    )

REWARD_TYPES = ['gear', 'item', 'gold', 'chest', 'xp', 'potion']

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
                bb.write_method_6(value1, GearType.GEARTYPE_BITSTOSEND)
                bb.write_method_6(value2, GearType.GEARTYPE_BITSTOSEND)
            else:
                bb.write_method_4(value1)
            break

    payload = bb.to_bytes()
    header  = struct.pack('>HH', 0x32, len(payload))
    return header + payload

def handle_lockbox_reward(session, data):
    _=data[4:]
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


def handle_hp_increase_notice(session, data):
       pass


#TODO...
def handle_linkupdater(session, data):
    return  # return here no point doing anything here for now at least

    br = BitReader(data[4:])

    client_elapsed = br.read_method_24()
    client_desync  = br.read_method_15()
    server_echo    = br.read_method_24()

    now_ms = int(time.time() * 1000)

    # First update → establish baseline
    if not hasattr(session, "clock_base"):
        session.clock_base = now_ms
        session.clock_offset_ms = 0
        session.last_desync_time = None

    session.client_elapsed = client_elapsed
    session.server_elapsed = server_echo

    # Compute offset (server_time - expected_client_time)
    session.clock_offset_ms = now_ms - (session.clock_base + client_elapsed)
    offset = abs(session.clock_offset_ms)

    DESYNC_THRESHOLD = 2500     # ms allowed before warning
    DESYNC_KICK_TIME = 2.0      # seconds of continuous desync before kick

    if offset > DESYNC_THRESHOLD or client_desync:
        # First time detecting desync
        if session.last_desync_time is None:
            session.last_desync_time = time.time()
            print(f"[{session.addr}] Desync detected offset={offset}ms (timer started)")
        else:
            elapsed = time.time() - session.last_desync_time
            if elapsed >= DESYNC_KICK_TIME:
                print(f"[{session.addr}] Kicking player for severe desync (offset={offset}ms)")
                session.conn.close()
                session.stop()
                return

    props = {
        "client_elapsed": client_elapsed,
        "client_desync": client_desync,
        "server_echo": server_echo,
        "clock_base": getattr(session, "clock_base", None),
        "server_now_ms": now_ms,
        "client_offset_ms": session.clock_offset_ms,
    }

    #print(f"Player [{get_active_character_name(session)}]")
    #pprint.pprint(props, indent=4)

#TODO... this is just for testing
def handle_grant_reward(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)

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
        for other in GS.all_sessions:
            if other.player_spawned and other.current_level == session.current_level:
                other.conn.sendall(pkt)
