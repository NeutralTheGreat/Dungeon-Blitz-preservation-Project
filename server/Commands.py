import struct
import random
import time

from bitreader import BitReader
from constants import GearType, class_3, PowerType, Game, class_119
from BitBuffer import BitBuffer
from globals import build_start_skit_packet
from missions import get_mission_extra
from accounts import save_characters
from globals import send_gold_reward, send_gear_reward, send_hp_update, send_material_reward
from game_data import get_random_gear_id

def handle_dungeon_run_report(session, data):
    br = BitReader(data[4:])

    master_class_id           = br.read_method_20(Game.const_209)
    player_level              = br.read_method_9()
    session_play_time         = br.read_method_9()
    time_in_combat            = br.read_method_9()
    total_damage_dealt_player = br.read_method_24()
    total_damage_dealt_pets   = br.read_method_24()
    expected_damage_scale     = br.read_method_24()
    kills                     = br.read_method_24()
    healing_dealt             = br.read_method_24()
    damage_received           = br.read_method_24()
    damage_resisted           = br.read_method_24()
    deaths                    = br.read_method_24()
    healing_received          = br.read_method_24()
    primary_damage_stat       = br.read_method_24()
    magic_damage              = br.read_method_24()
    armor_class               = br.read_method_24()
    attack_speed_scaled       = br.read_method_24()
    movement_speed_scaled     = br.read_method_24()
    max_hp                    = br.read_method_24()
    average_group_size_scaled = br.read_method_24()
    session_flags_bitfield    = br.read_method_20(class_119.const_228)
    time_rank                 = br.read_method_9()
    kills_score               = br.read_method_9()
    accuracy_score            = br.read_method_9()
    deaths_score              = br.read_method_9()
    treasure_score            = br.read_method_9()
    time_score                = br.read_method_9()
    entries = []
    while br.read_method_15():
        entry = read_class_166(br)
        entries.append(entry)

    log_block = {
    "master_class_id"           : master_class_id,
    "player_level"              : player_level,
    "session_play_time"         : session_play_time,
    "time_in_combat"            : time_in_combat,
    "total_damage_dealt_player" : total_damage_dealt_player,
    "total_damage_dealt_pets"   : total_damage_dealt_pets,
    "expected_damage_scale"     : expected_damage_scale,
    "kills"                     : kills,
    "healing_dealt"             : healing_dealt,
    "damage_received"           : damage_received,
    "damage_resisted"           : damage_resisted,
    "deaths"                    : deaths,
    "healing_received"          : healing_received,
    "primary_damage_stat"       : primary_damage_stat,
    "magic_damage"              : magic_damage,
    "armor_class"               : armor_class,
    "attack_speed_scaled"       : attack_speed_scaled,
    "movement_speed_scaled"     : movement_speed_scaled,
    "max_hp"                    : max_hp,
    "average_group_size_scaled" : average_group_size_scaled,
    "session_flags_bitfield"    : session_flags_bitfield,
    "time_rank"                 : time_rank,
    "kills_score"               : kills_score,
    "accuracy_score"            : accuracy_score,
    "deaths_score"              : deaths_score,
    "treasure_score"            : treasure_score,
    "time_score"                : time_score,
    }
    #pprint(log_block)
    #print(f"power_stats_count = {len(entries)}")

def read_class_166(br):
    entry = {}

    entry["stat_id"] = br.read_method_9()
    entry["delta"]   = br.read_method_24()
    entry["time"]    = br.read_method_24()

    return entry

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

    # Sync with player entity
    ent = session.entities.get(session.clientEntID)
    session.authoritative_max_hp = max_hp # Store on session for persistence across level loads
    
    if ent:
        prev_max_hp = ent.get("max_hp", 0)
        ent["max_hp"] = max_hp
        
        # If this is the first time we get stats or max_hp increased, 
        # initialize hp if not already set or at old max
        if "hp" not in ent or ent["hp"] == prev_max_hp:
            ent["hp"] = max_hp
        else:
            # Ensure current HP doesn't exceed new max
            ent["hp"] = min(ent["hp"], max_hp)


#TODO...
def handle_pickup_lootdrop(session, data):
    br = BitReader(data[4:])
    loot_id = br.read_method_9()

    # Check if we have record of this loot
    loot = getattr(session, "pending_loot", {}).pop(loot_id, None)
    
    if loot:
        char = session.current_char_dict
        if not char: return

        save_needed = False

        if "gold" in loot:
            amount = loot["gold"]
            char["gold"] += amount
            send_gold_reward(session, amount, show_fx=False)
            save_needed = True
            print(f"[Loot] {char['name']} picked up {amount} Gold.")

        if "health" in loot:
            hp_gain = loot["health"]
            # Update entity HP
            ent = session.entities.get(session.clientEntID)
            
            # Use session-based max_hp if available
            # If not yet synced (authoritative_max_hp is None), we skip clamping to avoid false "Full" reports
            max_hp = getattr(session, "authoritative_max_hp", None)
            
            if ent:
                current_hp = ent.get("hp", 100)
                
                # Check if already at max HP (only if we have authoritative max_hp)
                if max_hp is not None:
                    ent["max_hp"] = max_hp # Keep entity in sync
                    if current_hp >= max_hp:
                        print(f"[Loot] {char['name']} picked up health globe but HP is full (HP: {current_hp}/{max_hp}).")
                        return # Don't consume or heal if full
                else:
                    # If we don't have max_hp yet, assume not full (or use a huge fallback)
                    print(f"[Loot] {char['name']} picked up health globe (MaxHP sync pending).")

                new_hp = (min(max_hp, current_hp + hp_gain)) if max_hp else (current_hp + hp_gain)
                actual_gain = new_hp - current_hp
                ent["hp"] = new_hp
                
                # Send HP update to client
                send_hp_update(session, session.clientEntID, actual_gain)
                print(f"[Loot] {char['name']} healed +{actual_gain} HP (Final: {new_hp}/{max_hp if max_hp else '?'}).")
            else:
                 # Fallback for just updating session text if entity is missing temporarily
                 print(f"[Loot] {char['name']} picked up health globe but entity is missing. HP Sync required.")
            print(f"[Loot] {char['name']} picked up health globe (+{hp_gain} HP).")
             
        if "gear" in loot:
            gear_id = loot["gear"]
            tier = loot.get("tier", 1)
            
            # Create gear object
            new_gear = {
                "gearID": gear_id,
                "tier": tier,
                "runes": [0, 0, 0],
                "colors": [0, 0]
            }
            
            # Add to inventory
            if "inventoryGears" not in char:
                char["inventoryGears"] = []
            
            char["inventoryGears"].append(new_gear)
            
            # Trigger client notification "Received New Item"
            send_gear_reward(session, gear_id, tier=tier)
            
            save_needed = True
            print(f"[Loot] {char['name']} picked up Gear {gear_id} (Tier {tier}).")
             
        if "material" in loot:
            mat_id = loot["material"]
            
            # Add to inventory
            mats = char.setdefault("materials", [])
            found = False
            for entry in mats:
                if entry["materialID"] == mat_id:
                    entry["count"] = int(entry.get("count", 0)) + 1
                    found = True
                    break
            if not found:
                mats.append({"materialID": mat_id, "count": 1})
            
            send_material_reward(session, mat_id)
            save_needed = True
            print(f"[Loot] {char['name']} picked up Material {mat_id}.")

        if save_needed:
            save_characters(session.user_id, session.char_list)
    else:
        # print(f"Unknown loot pick up {loot_id}")
        pass

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
_last_loot_id = 900000
def generate_loot_id():
    global _last_loot_id
    _last_loot_id += 1
    return _last_loot_id

def handle_grant_reward(session, data):
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

    # Deduplication: Check if this source has already been processed in this level
    if not hasattr(session, "processed_reward_sources"):
        session.processed_reward_sources = set()
    
    reward_key = (session.current_level, source_id)
    if reward_key in session.processed_reward_sources:
        return
    session.processed_reward_sources.add(reward_key)

    # Physical Drops Only: We no longer add gold/xp directly to the character here.
    # Everything must be collected via physical loot drops (globes/gold piles).

    # --- Hybrid Loot Drop Logic ---
    # 1. Look up the source entity (Mob) to check if it's Flying.
    # 2. Flying Mobs: Spawn at Player Y (Ground) with offset.
    # 3. Ground Mobs: Spawn at Mob X/Y (Preserve Ramp Height) from packet.
    
    from game_data import get_ent_type # ensure import available if not top-level
    
    is_flying = False
    source_ent = None
    ent_name = None
    
    # Try to find source entity
    # Check session entities first
    if source_id in session.entities:
        source_ent = session.entities[source_id]
    # Check global level NPCs
    elif session.current_level in GS.level_npcs and source_id in GS.level_npcs[session.current_level]:
        source_ent = GS.level_npcs[session.current_level][source_id]
        
    if source_ent:
        ent_name = source_ent.get("name")
        ent_type_data = get_ent_type(ent_name) if ent_name else {}
        if ent_type_data.get("Flying") == "True":
            is_flying = True

    if is_flying:
        # Use player's X and Y coordinate (Gravity Fallback)
        player_ent = session.entities.get(session.clientEntID)
        if player_ent:
            if "pos_y" in player_ent:
                world_y = int(player_ent["pos_y"])
            if "pos_x" in player_ent:
                # Add a small random offset (30-60 pixels) so loot doesn't spawn *inside* the player
                offset = random.choice([-1, 1]) * random.randint(30, 60)
                world_x = int(player_ent["pos_x"]) + offset
    else:
        # Ground Mob: Trust the coordinates reported by client (which likely match the mob's death location)
        # OR force use of source_ent coordinates if available to be safe
        if source_ent and "x" in source_ent and "y" in source_ent:
             world_x = int(source_ent["x"])
             world_y = int(source_ent["y"])

    # print(f"[DEBUG_LOOT] Mob={source_id} Name={ent_name} Flying={is_flying} FinalX={world_x} FinalY={world_y}")

    process_drop_reward(session, world_x, world_y, gold, hp_gain, drop_gear, target_id=source_id)
    
    print(f"Granted Reward Request for {source_id}: XP={exp}, Gold={gold}, Item={drop_gear}")

def process_drop_reward(session, x, y, gold=0, hp_gain=0, drop_gear=False, material_id=0, target_id=0):
    # Initialize session tracking if needed
    if not hasattr(session, "pending_loot"):
        session.pending_loot = {}
    if not hasattr(session, "processed_reward_sources"):
        session.processed_reward_sources = set()

    # Deduplication check
    if target_id != 0:
        reward_key = (session.current_level, target_id)
        if reward_key in session.processed_reward_sources:
            return
        session.processed_reward_sources.add(reward_key)

    # Drop Gold
    if gold > 0:
        lid = generate_loot_id()
        # Store for pickup verification
        session.pending_loot[lid] = {"gold": gold}
        
        pkt = build_lootdrop(
            loot_id=lid,
            x=x,
            y=y,
            gold=gold
        )
        session.conn.sendall(pkt)

    # Drop Health
    if hp_gain > 0:
        lid = generate_loot_id()
        session.pending_loot[lid] = {"health": hp_gain}
        
        pkt = build_lootdrop(
            loot_id=lid,
            x=x + random.randint(-15, 15),
            y=y + random.randint(-15, 15),
            health=hp_gain
        )
        session.conn.sendall(pkt)

    # Drop Gear
    if drop_gear:
        lid = generate_loot_id()
        # Randomly select gear and use Tier 2 (Legendary)
        class_name = session.current_char_dict.get("class") if session.current_char_dict else None
        gear_id = get_random_gear_id(class_name)
        session.pending_loot[lid] = {"gear": gear_id, "tier": 2}
        
        pkt = build_lootdrop(
            loot_id=lid,
            x=x + random.randint(-20, 20),
            y=y + random.randint(-10, 10),
            gear_id=gear_id, 
            gear_tier=2
        )
        session.conn.sendall(pkt)

    # Drop Material
    if material_id and material_id > 0:
        lid = generate_loot_id()
        session.pending_loot[lid] = {"material": material_id}
        
        pkt = build_lootdrop(
            loot_id=lid,
            x=x + random.randint(-20, 20),
            y=y + random.randint(-10, 10),
            material_id=material_id
        )
        session.conn.sendall(pkt)

def build_lootdrop(
        loot_id: int,
        x: int,
        y: int,
        gear_id: int = 0,
        gear_tier: int = 0,
        material_id: int = 0,
        gold: int = 0,
        health: int = 0,
        trove: int = 0,
        dye_id: int = 0
):
    bb = BitBuffer()

    bb.write_method_4(loot_id)
    bb.write_method_45(x)
    bb.write_method_45(y)

    # Gear branch
    if gear_id > 0:
        bb.write_method_15(True)
        bb.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)
        bb.write_method_6(gear_tier, GearType.GEARTYPE_BITSTOSEND)
        body = bb.to_bytes()
        return struct.pack(">HH", 0x32, len(body)) + body
    else:
        bb.write_method_15(False)

    # Material Branch
    if material_id > 0:
        bb.write_method_15(True)
        bb.write_method_4(material_id)
        body = bb.to_bytes()
        return struct.pack(">HH", 0x32, len(body)) + body
    else:
        bb.write_method_15(False)

    # Gold Branch
    if gold > 0:
        bb.write_method_15(True)
        bb.write_method_4(gold)
        body = bb.to_bytes()
        return struct.pack(">HH", 0x32, len(body)) + body
    else:
        bb.write_method_15(False)

    # Health Branch
    if health > 0:
        bb.write_method_15(True)
        bb.write_method_4(health)
        body = bb.to_bytes()
        return struct.pack(">HH", 0x32, len(body)) + body
    else:
        bb.write_method_15(False)

    # Chest Trove Branch
    if trove > 0:
        bb.write_method_15(True)
        bb.write_method_4(trove)
        body = bb.to_bytes()
        return struct.pack(">HH", 0x32, len(body)) + body
    else:
        bb.write_method_15(False)

    # Fallback branch: dye ID
    val = dye_id if dye_id > 0 else 1
    bb.write_method_4(val)

    body = bb.to_bytes()
    return struct.pack(">HH", 0x32, len(body)) + body