import struct
import random
import time

from bitreader import BitReader
from constants import GearType, class_3, PowerType, Game
from BitBuffer import BitBuffer
from globals import build_start_skit_packet
from missions import get_mission_extra

#TODO...
#these names may be wrong
def handle_set_level_complete(session, data):
    br = BitReader(data[4:])

    send_dummy_level_complete(session)

    pkt_completion_percent = br.read_method_9()
    pkt_bonus_score_total  = br.read_method_9()
    pkt_gold_reward        = br.read_method_9()
    pkt_material_reward    = br.read_method_9()
    pkt_gear_count         = br.read_method_9()
    pkt_remaining_kills    = br.read_method_9()
    pkt_required_kills     = br.read_method_9()
    pkt_level_width_score  = br.read_method_9()
    """
    print(
        f"  completion_percent = {pkt_completion_percent}\n"
        f"  bonus_score_total  = {pkt_bonus_score_total}\n"
        f"  gold_reward        = {pkt_gold_reward}\n"
        f"  material_reward    = {pkt_material_reward}\n"
        f"  gear_count         = {pkt_gear_count}\n"
        f"  remaining_kills    = {pkt_remaining_kills}\n"
        f"  required_kills     = {pkt_required_kills}\n"
        f"  level_width_score  = {pkt_level_width_score}\n"
    )"""

def send_dummy_level_complete(
    session,
    stars=3,
    result_bar=1,
    rank=1,
    kills=50,
    accuracy=50,
    deaths=5,
    treasure=5000,
    time=6000,
):
    bb = BitBuffer()

    bb.write_method_6(stars, 4)
    bb.write_method_4(result_bar)
    bb.write_method_4(rank)
    bb.write_method_4(kills)
    bb.write_method_4(accuracy)
    bb.write_method_4(deaths)
    bb.write_method_4(treasure)
    bb.write_method_4(time)

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x87, len(payload)) + payload
    session.conn.sendall(pkt)


def handle_send_combat_stats(session, data):
    br = BitReader(data[4:])

    melee_damage = br.read_method_9()
    magic_damage = br.read_method_9()
    max_hp       = br.read_method_9()

    stat_scale   = br.read_method_20(Game.const_794)
    stat_rev     = br.read_method_9()
    print(
        f"[COMBAT_STATS] melee={melee_damage} "
        f"magic={magic_damage} "
        f"maxHP={max_hp} "
        f"scale={stat_scale} "
        f"rev={stat_rev}"
    )


#TODO...
def handle_pickup_lootdrop(session, data):
    br = BitReader(data[4:])
    loot_id = br.read_method_9()
    #print(f" loot id : {loot_id}")

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
def handle_power_use(session, data):
    br = BitReader(data[4:])
    power = br.read_method_20(PowerType.const_423)
    #print(f"power : {power}")


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
    ent_type = npc.get("character_name") or npc.get("entType") or npc.get("name")

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

        # Normalize them BEFORE matching (auto-map via character_name)
        if contact and contact != npc_type_norm:
            # Allow character_name to solve mismatches
            if norm(mextra.get("ContactName")) == norm(npc.get("character_name")):
                contact = npc_type_norm
        if ret and ret != npc_type_norm:
            if norm(mextra.get("ReturnName")) == norm(npc.get("character_name")):
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
def generate_loot_id():
    return random.randint(1_000_000, 9_999_999)

def handle_grant_reward(session, data):
    return

    br = BitReader(data[4:])

    receiver_id = br.read_method_9()
    source_id   = br.read_method_9()

    drop_item   = br.read_method_15()
    item_mult   = br.read_method_309()

    drop_gear   = br.read_method_15()
    gear_mult   = br.read_method_309()

    drop_material = br.read_method_15()
    drop_trove    = br.read_method_15()

    exp     = br.read_method_9()
    pet_exp = br.read_method_9()
    hp_gain = br.read_method_9()
    gold    = br.read_method_9()

    world_x = br.read_method_24()
    world_y = br.read_method_24()

    killing_blow = br.read_method_15()
    combo = br.read_method_9() if killing_blow else 0
    """
    print("\n========== PKTTYPE_GRANT_REWARD (0x2A) ==========")
    print(f" Receiver EntityID : {receiver_id}")
    print(f" Source EntityID   : {source_id}")
    print("-------------------------------------------------")
    print(f" Drop Item Flag    : {drop_item}")
    print(f" Item Multiplier   : {item_mult}")
    print(f" Drop Gear Flag    : {drop_gear}")
    print(f" Gear Multiplier   : {gear_mult}")
    print(f" Drop Material     : {drop_material}")
    print(f" Drop Trove        : {drop_trove}")
    print("-------------------------------------------------")
    print(f" EXP Granted       : {exp}")
    print(f" Pet EXP Granted   : {pet_exp}")
    print(f" HP Gain           : {hp_gain}")
    print(f" Gold Granted      : {gold}")
    print("-------------------------------------------------")
    print(f" World X           : {world_x}")
    print(f" World Y           : {world_y}")
    print("-------------------------------------------------")
    print(f" Killing Blow      : {killing_blow}")
    if killing_blow:
        print(f" Killer Combo ID   : {combo}")
    print("-------------------------------------------------")
    """
    PROCESSED_REWARD_SOURCES = set()
    reward_key = (session.current_level, source_id)
    if reward_key in PROCESSED_REWARD_SOURCES:
        return
    PROCESSED_REWARD_SOURCES.add(reward_key)

    drop_loot = True

    if drop_loot:
        pkt = build_lootdrop(
            loot_id=generate_loot_id(),
            x=world_x,
            y=world_y,
        )
        session.conn.sendall(pkt)

def build_lootdrop(
        loot_id: int,
        x: int,
        y: int,
):
    bb = BitBuffer()

    bb.write_method_4(loot_id)
    bb.write_method_45(x)
    bb.write_method_45(y)

    # only one boolean must be True at a time if all False then the client will drop dyes

    # Gear branch
    bb.write_method_15(False)
    #bb.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)
    #bb.write_method_6(tier, GearType.GEARTYPE_BITSTOSEND)  # 3 tears in total 0/2

    # material Branch
    bb.write_method_15(False)
    #bb.write_method_4(Mat_ID)  # Materials ID 126 in Total

    # Gold Branch
    bb.write_method_15(False)
    #bb.write_method_4(Gold_amount)

    # Health Branch
    bb.write_method_15(False)
    #bb.write_method_4(health_amount)

    # Chest Trove Branch
    bb.write_method_15(False)
    #bb.write_method_4(1)  # only one Trove is possible since only one exists ID 1

    # Fallback branch: dye ID
    bb.write_method_4(1)  # 250 Dye IDs in total

    body = bb.to_bytes()
    return struct.pack(">HH", 0x32, len(body)) + body