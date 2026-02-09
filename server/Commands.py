import struct
import random
import time

from bitreader import BitReader
from constants import GearType, class_3, PowerType, Game, class_119, PET_TYPES, get_egg_id
from BitBuffer import BitBuffer
from globals import build_start_skit_packet
from missions import get_mission_extra
from accounts import save_characters
from globals import send_gold_reward, send_gear_reward, send_hp_update, send_material_reward, GS, send_npc_dialog, send_consumable_reward, send_charm_reward, send_mount_reward, send_dye_reward, send_new_pet_packet
from game_data import get_random_gear_id
from data.npc_chats import NPC_CHATS

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
            send_gold_reward(session, amount)
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

    # Fallback: Bubble Chat if no mission dialogue is triggered
    if dialogue_id == 0:
        if npc_type_norm in NPC_CHATS:
            text = random.choice(NPC_CHATS[npc_type_norm])
            send_npc_dialog(session, npc_id, text)
            print(f"[{session.addr}] [PKT0x7A] Bubble Chat {ent_type}: \"{text}\"")
            return

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
    
    # All legendary dyes (rarity "L") from Game.swz.txt - using DyeName format (CamelCase)
    # Client looks up dyes by DyeName, not DisplayName
    LEGENDARY_DYES = [
        "BroodMotherBlack",      # Brood Mother Black
        "ClearcastPearl",        # Clearcast Pearl
        "WizardWoolWhite",       # Wizard Wool White
        "AstralObsidian",        # Astral Obsidian
        "GleamingGold",          # Gleaming Gold
        "ShiningSilver",         # Shining Silver
        "MightyMammothIvory",    # Mighty Mammoth Ivory
        "FieryPhoenixFeather",   # Fiery Phoenix Feather
        "VelvetValkyries",       # Velvet Valkyries
        "YearOfTheMammoth",      # Year Of The Mammoth
        "CheerocracyPackPink",   # Cheerocracy Pack Pink
        "ElegantEmerald",        # Elegant Emerald
        "LeviathanLapisLazuli",  # Leviathan Lapis Lazuli
        "AlluringAmethyst",      # Alluring Amethyst
        "SparklingTourmaline",   # Sparkling Tourmaline
        "DragonCoatRed",         # Dragon Coat Red
        "IridescentOpal",        # Iridescent Opal
        "HailToTheForest",       # Hail To The Forest
        "BrokenHeartBlack",      # Broken Heart Black
        "FrostlordSatin",        # Frostlord Satin
    ]
    
    reward_map = {
        0: ("MountLockbox01L01", True, "mount"),  # Mount (Ivorstorm Guardian)
        1: ("Lockbox01L01", True, "pet"),  # Pet (Darkheart Apparition)
        2: ("GenericBrown", True, "egg"),  # Egg -> client shows "Pet (Level 10)"
        3: ("CommonBrown", True, "egg"),  # Egg
        4: ("OrdinaryBrown", True, "egg"),  # Egg
        5: ("PlainBrown", True, "egg"),  # Egg
        6: ("RarePetFood", True, "consumable"),  # Consumable
        7: ("PetFood", True, "consumable"),  # Consumable
        8: (None, True, "gear"),  # Class Gear - gear ID selected based on player class
        9: ("TripleFind", True, "charm"),  # Charm
        10: ("DoubleFind1", True, "charm"),  # Charm
        11: ("DoubleFind2", True, "charm"),  # Charm
        12: ("DoubleFind3", True, "charm"),  # Charm
        13: ("MajorLegendaryCatalyst", True, "consumable"),  # Consumable
        14: ("MajorRareCatalyst", True, "consumable"),  # Consumable
        15: ("MinorRareCatalyst", True, "consumable"),  # Consumable
        16: ("3,000,000 Gold", True, "gold", 3000000),  # Gold (3 000 000)
        17: ("1,500,000 Gold", True, "gold", 1500000),  # Gold (1 500 000)
        18: ("750,000 Gold", True, "gold", 750000),  # Gold (750 000)
        19: (None, True, "dye"),  # Legendary Dye - actual dye name selected below
    }
    
    # Class gear mapping by player class
    # Each class has 6 gear pieces: Sword, Shield, Hat, Armor, Gloves, Boots
    CLASS_GEAR_IDS = {
        "mage": [1165, 1166, 1167, 1168, 1169, 1170],
        "rogue": [1171, 1172, 1173, 1174, 1175, 1176],
        "paladin": [1177, 1178, 1179, 1180, 1181, 1182],
    }
    
    # Class gear names for client display
    CLASS_GEAR_NAMES = {
        1165: "UniqueMageLockbox01GearSword30",
        1166: "UniqueMageLockbox01GearShield30",
        1167: "UniqueMageLockbox01GearHat30",
        1168: "UniqueMageLockbox01GearArmor30",
        1169: "UniqueMageLockbox01GearGloves30",
        1170: "UniqueMageLockbox01GearBoots30",
        1171: "UniqueRogueLockbox01GearSword30",
        1172: "UniqueRogueLockbox01GearShield30",
        1173: "UniqueRogueLockbox01GearHat30",
        1174: "UniqueRogueLockbox01GearArmor30",
        1175: "UniqueRogueLockbox01GearGloves30",
        1176: "UniqueRogueLockbox01GearBoots30",
        1177: "UniquePaladinLockbox01GearSword30",
        1178: "UniquePaladinLockbox01GearShield30",
        1179: "UniquePaladinLockbox01GearHat30",
        1180: "UniquePaladinLockbox01GearArmor30",
        1181: "UniquePaladinLockbox01GearGloves30",
        1182: "UniquePaladinLockbox01GearBoots30",
    }

    # Get player class for gear selection
    char = session.current_char_dict
    if not char:
        return
    
    player_class = char.get("class", "").lower()
    
    # ===== DUPLICATE PREVENTION FOR LEGENDARY ITEMS =====
    # Get what the player already owns
    owned_mounts = set(char.get("mounts", []))
    owned_dyes = set(char.get("OwnedDyes", []))
    owned_gear_ids = set(g.get("gearID", 0) for g in char.get("inventoryGears", []))
    owned_gear_ids.update(g.get("gearID", 0) for g in char.get("equippedGears", []))
    owned_pet_types = set(p.get("typeID", 0) for p in char.get("pets", []))
    
    # Import mount/pet/dye IDs for checking ownership
    from constants import get_mount_id, get_dye_id
    
    # Check which legendary rewards are still available
    available_rewards = {}
    
    for idx, reward_data in reward_map.items():
        reward_type = reward_data[2]
        
        if reward_type == "mount":
            mount_id = get_mount_id(reward_data[0])
            if mount_id == 0 or mount_id not in owned_mounts:
                available_rewards[idx] = reward_data
                
        elif reward_type == "pet":
            # Check if player already owns this pet type
            pet_def = next((p for p in PET_TYPES if p.get("PetName") == reward_data[0] or p.get("PetID") == reward_data[0]), None)
            if pet_def:
                pet_type_id = pet_def.get("PetID", 0)
                if pet_type_id not in owned_pet_types:
                    available_rewards[idx] = reward_data
            else:
                available_rewards[idx] = reward_data  # Unknown pet, allow it
                
        elif reward_type == "dye":
            # Dye is selected later, so we check if ANY legendary dye is available
            available_dyes = []
            for dye_name in LEGENDARY_DYES:
                dye_id = get_dye_id(dye_name)
                if dye_id == 0 or dye_id not in owned_dyes:
                    available_dyes.append(dye_name)
            if available_dyes:
                available_rewards[idx] = reward_data
                
        elif reward_type == "gear":
            # Check if any class gear is still available
            class_gears = CLASS_GEAR_IDS.get(player_class, CLASS_GEAR_IDS["paladin"])
            available_gears = [g for g in class_gears if g not in owned_gear_ids]
            if available_gears:
                available_rewards[idx] = reward_data

        elif reward_type == "egg":
            # Egg reward - adds Level 10 pet directly to inventory
            # No capacity limit for pet inventory (pets are unlimited)
            available_rewards[idx] = reward_data
                
        else:
            # Gold, consumables, charms - always available (not unique)
            available_rewards[idx] = reward_data
    
    # If no legendary rewards available, fall back to non-legendary rewards only
    if not available_rewards:
        print("[Lockbox] All legendary items owned! Falling back to non-legendary rewards.")
        available_rewards = {k: v for k, v in reward_map.items() if v[2] in ("gold", "consumable", "charm", "egg")}
    
    if not available_rewards:
        print("[Lockbox] ERROR: No rewards available at all!")
        return
    
    idx, reward_data = random.choice(list(available_rewards.items()))
    
    # For dye rewards, select a random legendary dye THE PLAYER DOESN'T OWN
    if reward_data[2] == "dye":
        available_dyes = []
        for dye_name in LEGENDARY_DYES:
            dye_id = get_dye_id(dye_name)
            if dye_id == 0 or dye_id not in owned_dyes:
                available_dyes.append(dye_name)
        if available_dyes:
            selected_dye = random.choice(available_dyes)
            reward_data = (selected_dye, True, "dye")
        else:
            # Fallback: give gold instead
            reward_data = ("750,000 Gold", True, "gold", 750000)
            idx = 18
    
    # For gear rewards, select a random class gear THE PLAYER DOESN'T OWN
    gear_id = 0
    if reward_data[2] == "gear":
        class_gears = CLASS_GEAR_IDS.get(player_class, CLASS_GEAR_IDS["paladin"])
        available_gears = [g for g in class_gears if g not in owned_gear_ids]
        if available_gears:
            gear_id = random.choice(available_gears)
            gear_name = CLASS_GEAR_NAMES.get(gear_id, f"ClassGear{gear_id}")
            reward_data = (gear_name, True, "gear", gear_id)
        else:
            # Fallback: give gold instead
            reward_data = ("750,000 Gold", True, "gold", 750000)
            idx = 18
        
    name = reward_data[0]
    needs_str = reward_data[1]
    reward_type = reward_data[2]
    gold_amount = reward_data[3] if len(reward_data) > 3 and reward_type == "gold" else 0
    reward_gear_id = reward_data[3] if len(reward_data) > 3 and reward_type == "gear" else 0
    
    # For dye rewards, do NOT convert to display name here
    # Client needs CamelCase name (e.g. "BroodMotherBlack") for icon lookup in class_18.method_996
    # Converting to "Brood Mother Black" causes Error #1009 (Null Object Reference)
    # The client handles display name conversion internally using the Dye Object
    # if reward_type == "dye":
    #    from constants import get_dye_display_name
    #    name = get_dye_display_name(name)
    
    # For egg rewards: client looks up class_14.var_233[param4] which is keyed by PetName, not EggName.
    # Sending "PlainBrown" etc. causes null lookup and Error #1009. Send the hatched pet's PetName
    # (EggID matches PetID in data) so the client can show the correct icon. Keep 'name' as egg name for grant.
    name_for_packet = name
    if reward_type == "egg":
        egg_id = get_egg_id(name)
        pet_for_display = next((p for p in PET_TYPES if p.get("PetID") == egg_id), None)
        if pet_for_display:
            name_for_packet = pet_for_display.get("PetName", name)

    # Send visual packet to client
    bb = BitBuffer()
    
    # For dye rewards, send the specific dye from the Dye Pack (Pack ID 4)
    # This allows the client to show the specific dye icon and name.
    # Lockbox legendary dye text colour: client uses Rewardpack Rarity from Game.swz.
    # DyePack01Legendary (pack 4) must have <Rarity>L</Rarity> for yellow text; see
    # extra-modules/swz-scripts/Game.swz.txt (repack into Game.swz if serving custom client).
    if reward_type == "dye":
        # Pack 4 (Dye Pack) contains a single generic dye item at index 0.
        # We must use index 0. The specific dye is determined by the name string we send.
        bb.write_method_6(4, CAT_BITS)        # Pack ID 4 = Dye Pack
        bb.write_method_6(0, ID_BITS)         # Index 0 (The only item in this pack)
    else:
        bb.write_method_6(PACK_ID, CAT_BITS)
        bb.write_method_6(idx, ID_BITS)

    
    bb.write_method_6(1 if needs_str else 0, 1)
    if needs_str:
        bb.write_method_13(name_for_packet)

    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0x108, len(payload)) + payload
    session.conn.sendall(packet)

    print(f"Lockbox reward: idx={idx}, name={name}, type={reward_type}")

    
    save_needed = False
    
    
    # ALWAYS grant Royal Sigils when opening a lockbox (50-150 sigils)
    sigil_reward = random.randint(50, 150)
    current_sigils = int(char.get("SilverSigils", 0))  # Cast to int to avoid string comparison
    char["SilverSigils"] = current_sigils + sigil_reward
    
    # Send Royal Sigil reward packet (0x112)
    bb_sigil = BitBuffer()
    bb_sigil.write_method_4(sigil_reward)
    sigil_payload = bb_sigil.to_bytes()
    sigil_packet = struct.pack(">HH", 0x112, len(sigil_payload)) + sigil_payload
    session.conn.sendall(sigil_packet)
    
    save_needed = True
    print(f"[Lockbox] {char.get('name', 'Unknown')} received {sigil_reward} Royal Sigils (total: {char['SilverSigils']})")
    
    if reward_type == "gold":
        char["gold"] += gold_amount
        send_gold_reward(session, gold_amount, suppress=False)  # Show NEW notification
        save_needed = True
        print(f"[Lockbox] {char['name']} received {gold_amount} Gold")
        
    elif reward_type == "consumable":
        # Add consumable to inventory using consumableID for consistency
        from globals import send_consumable_reward
        from constants import get_consumable_id
        consumable_id = get_consumable_id(name)
        if consumable_id == 0:
            print(f"[Lockbox] Warning: Unknown consumable '{name}'")
        else:
            consumables = char.setdefault("consumables", [])
            found = False
            for entry in consumables:
                if entry.get("consumableID") == consumable_id:
                    entry["count"] = int(entry.get("count", 0)) + 1
                    found = True
                    break
            if not found:
                consumables.append({"consumableID": consumable_id, "count": 1})
            send_consumable_reward(session, name, 1)
            save_needed = True
            print(f"[Lockbox] {char['name']} received {name} (ID:{consumable_id})")
        
    elif reward_type == "charm":
        # Add charm to inventory
        from globals import send_charm_reward
        charms = char.setdefault("charms", [])
        found = False
        for entry in charms:
            if entry.get("charmName") == name:
                entry["count"] = int(entry.get("count", 0)) + 1
                found = True
                break
        if not found:
            charms.append({"charmName": name, "count": 1})
        send_charm_reward(session, name)
        save_needed = True
        print(f"[Lockbox] {char['name']} received charm {name}")
        
    elif reward_type == "mount":
        # Add mount to owned mounts
        from globals import send_mount_reward
        from constants import get_mount_id
        
        mount_id = get_mount_id(name)
        print(f"[Lockbox DEBUG] Mount lookup: name='{name}' -> mount_id={mount_id}")
        
        if mount_id != 0:
            mounts = char.setdefault("mounts", [])
            print(f"[Lockbox DEBUG] Current mounts: {mounts}")
            
            if mount_id not in mounts:
                mounts.append(mount_id)
                save_needed = True
                print(f"[Lockbox] {char['name']} received NEW mount {name} (ID: {mount_id})")
            else:
                print(f"[Lockbox] {char['name']} already owns mount {name} (ID: {mount_id})")
            
            # Always send notification for lockbox rewards (suppress=False)
            send_mount_reward(session, mount_id, suppress=False)
        else:
            print(f"[Lockbox] Warning: Unknown mount ID for {name}, skipping grant")
            
    elif reward_type == "pet":
        # Add pet to owned pets (level 1)
        pet_def = next((p for p in PET_TYPES if p.get("PetName") == name or p.get("PetID") == name), None)
        if pet_def:
            pet_type_id = pet_def["PetID"]
            starting_rank = 1
            
            pets = char.get("pets", [])
            special_id = max((p.get("special_id", 0) for p in pets), default=0) + 1
            
            new_pet = {
                "typeID": pet_type_id,
                "special_id": special_id,
                "level": starting_rank,
                "xp": 0,
            }
            
            pets.append(new_pet)
            char["pets"] = pets
            
            # Send pet notification with suppress=False to show NEW in bottom-left panel
            send_new_pet_packet(session, pet_type_id, special_id, starting_rank, suppress=False)
            save_needed = True
            print(f"[Lockbox] {char['name']} received pet {name}")
        else:
            print(f"[Lockbox] Warning: Pet definition not found for '{name}'")

    elif reward_type == "egg":
        # Egg reward - Add as Level 10 pet directly to inventory
        # (EggID matches PetID in data, so egg_id is the pet type ID)
        egg_id = get_egg_id(name)
        if egg_id and egg_id > 0:
            pet_def = next((p for p in PET_TYPES if p.get("PetID") == egg_id), None)
            if pet_def:
                pet_type_id = pet_def["PetID"]
                starting_level = 10  # Level 10 from egg reward
                
                pets = char.get("pets", [])
                special_id = max((p.get("special_id", 0) for p in pets), default=0) + 1
                
                new_pet = {
                    "typeID": pet_type_id,
                    "special_id": special_id,
                    "level": starting_level,
                    "xp": 0,
                }
                
                pets.append(new_pet)
                char["pets"] = pets
                
                # Send pet notification
                send_new_pet_packet(session, pet_type_id, special_id, starting_level, suppress=False)
                save_needed = True
                print(f"[Lockbox] {char['name']} received level {starting_level} pet {pet_def.get('DisplayName', name)}")
            else:
                print(f"[Lockbox] Warning: Pet definition not found for egg ID {egg_id}")
        else:
            print(f"[Lockbox] Warning: Unknown egg '{name}'")

    elif reward_type == "dye":
        # Add dye to OwnedDyes using integer ID (not string name)
        from globals import send_dye_reward
        from constants import get_dye_id
        
        dye_id = get_dye_id(name)
        if dye_id == 0:
            print(f"[Lockbox] Warning: Unknown dye ID for '{name}'")
        else:
            owned_dyes = char.setdefault("OwnedDyes", [])
            if dye_id not in owned_dyes:
                owned_dyes.append(dye_id)
                send_dye_reward(session, name, suppress=False)  # Show NEW notification - client uses dye's rarity
                save_needed = True
                print(f"[Lockbox] {char['name']} received dye {name} (ID: {dye_id})")
            else:
                print(f"[Lockbox] {char['name']} already owns dye {name} (ID: {dye_id})")
    
    elif reward_type == "gear":
        # Add class gear to inventory (Tier 2 = Legendary)
        if reward_gear_id > 0:
            new_gear = {
                "gearID": reward_gear_id,
                "tier": 2,  # Tier 2 = Legendary (gold/yellow notification)
                "runes": [0, 0, 0],
                "colors": [0, 0]
            }
            
            inventory = char.setdefault("inventoryGears", [])
            inventory.append(new_gear)
            
            # Send gear reward notification with tier 2 for legendary color
            send_gear_reward(session, reward_gear_id, tier=2)
            save_needed = True
            print(f"[Lockbox] {char['name']} received legendary class gear {name} (ID: {reward_gear_id}, Tier: 2)")
    
    if save_needed:
        save_characters(session.user_id, session.char_list)


def handle_buy_treasure_trove(session, data):
    """
    Handle the 0x114 packet for buying treasure troves.
    Payload contains a single byte indicating the purchase option.
    Options: x1 = 50,000 gold, x10 = 375,000 gold, x25 = 625,000 gold
    """
    raw_payload = data[4:]
    print(f"[BuyTrove DEBUG] Raw payload length: {len(raw_payload)} bytes")
    if raw_payload:
        # Print all bits for analysis
        all_bits = ''.join(format(b, '08b') for b in raw_payload)
        print(f"[BuyTrove DEBUG] Raw bits: {all_bits}")
        print(f"[BuyTrove DEBUG] Raw hex: {raw_payload.hex()}")
    
    br = BitReader(raw_payload)
    
    # Try different reading strategies to understand the packet format
    # Strategy 1: Read first 8 bits as raw value
    if len(raw_payload) >= 1:
        first_byte = raw_payload[0]
        print(f"[BuyTrove DEBUG] First byte value: {first_byte}")
    
    # Read lockbox_id (2 bits)
    lockbox_id = br.read_method_6(2)
    print(f"[BuyTrove DEBUG] lockbox_id={lockbox_id} (2 bits), remaining: {br.remaining_bits()}")
    
    # Try reading option with method_4 (variable length) instead of fixed 2 bits
    option_index = br.read_method_4()
    print(f"[BuyTrove DEBUG] option_index={option_index} (method_4)")
    
    print(f"[BuyTrove] Received: lockbox_id={lockbox_id}, option_index={option_index}")
    
    # Define costs and quantities
    TROVE_OPTIONS = {
        0: {"quantity": 1, "cost": 50000},
        1: {"quantity": 10, "cost": 375000},
        2: {"quantity": 25, "cost": 625000},
    }
    
    if option_index not in TROVE_OPTIONS:
        print(f"[BuyTrove] Invalid option index: {option_index}")
        return
    
    option = TROVE_OPTIONS[option_index]
    quantity = option["quantity"]
    cost = option["cost"]
    
    char = session.current_char_dict
    if not char:
        print("[BuyTrove] No character data found")
        return
    
    current_gold = int(char.get("gold", 0))
    
    if current_gold < cost:
        print(f"[BuyTrove] Not enough gold: {current_gold} < {cost}")
        return
    
    # Deduct gold
    char["gold"] = current_gold - cost
    
    # Add treasure troves (lockboxID = 1 for standard treasure trove)
    TROVE_LOCKBOX_ID = 1
    lockboxes = char.setdefault("lockboxes", [])
    
    # Find existing lockbox entry or create new one
    found = False
    for box in lockboxes:
        if box.get("lockboxID") == TROVE_LOCKBOX_ID:
            box["count"] = int(box.get("count", 0)) + quantity
            found = True
            break
    
    if not found:
        lockboxes.append({"lockboxID": TROVE_LOCKBOX_ID, "count": quantity})
    
    # Save character data
    save_characters(session.user_id, session.char_list)
    
    # Send gold loss notification to client (packet 0xB4)
    bb = BitBuffer()
    bb.write_method_4(cost)
    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0xB4, len(payload)) + payload
    session.conn.sendall(packet)
    
    # Send lockbox inventory update to client (packet 0x104)
    # Client reads: method_6(class_15.const_300) = 2 bits for lockbox ID
    #              method_4() for count (this is the DELTA to add, not total!)
    #              method_11() for boolean flag (show notification)
    bb_lockbox = BitBuffer()
    bb_lockbox.write_method_6(TROVE_LOCKBOX_ID, 2)  # 2 bits for lockbox ID
    # Send the quantity purchased (delta), NOT the total count
    # Client adds this value to its local count
    bb_lockbox.write_method_4(quantity)
    bb_lockbox.write_method_11(1, 1)  # Show notification = true
    lockbox_payload = bb_lockbox.to_bytes()
    lockbox_packet = struct.pack(">HH", 0x104, len(lockbox_payload)) + lockbox_payload
    session.conn.sendall(lockbox_packet)
    
    # Calculate new total for logging
    new_count = 0
    for box in lockboxes:
        if box.get("lockboxID") == TROVE_LOCKBOX_ID:
            new_count = int(box.get("count", 0))
            break
    
    print(f"[BuyTrove] {char.get('name', 'Unknown')} purchased {quantity} treasure trove(s) for {cost} gold (new total: {new_count})")


def handle_buy_lockbox_keys(session, data):
    """
    Handle the 0x105 packet for buying lockbox keys with Mammoth Idols.
    Client sends: method_9(option_index) ONLY - no lockbox_id!
    Client adds keys locally and expects NO response packet.
    Options from const_356 = [1, 10, 25], costs from const_1059 = [22, 210, 470]
    """
    raw_payload = data[4:]
    print(f"[BuyKeys DEBUG] Raw payload length: {len(raw_payload)} bytes")
    if raw_payload:
        all_bits = ''.join(format(b, '08b') for b in raw_payload)
        print(f"[BuyKeys DEBUG] Raw bits: {all_bits}")
    
    br = BitReader(raw_payload)
    
    # Client sends ONLY option_index via method_9 (4-bit prefix + variable value)
    # NOT lockbox_id + option_index as previously assumed
    option_index = br.read_method_9()
    print(f"[BuyKeys DEBUG] option_index={option_index}")
    
    # Define costs and quantities for keys
    # From class_131.txt: const_356 = [1, 10, 25], const_1059 = [22, 210, 470]
    KEY_OPTIONS = {
        0: {"quantity": 1, "cost": 22},
        1: {"quantity": 10, "cost": 210},
        2: {"quantity": 25, "cost": 470},
    }
    
    if option_index not in KEY_OPTIONS:
        print(f"[BuyKeys] Invalid option index: {option_index}")
        return
    
    option = KEY_OPTIONS[option_index]
    quantity = option["quantity"]
    cost = option["cost"]
    
    char = session.current_char_dict
    if not char:
        print("[BuyKeys] No character data found")
        return
    
    current_idols = int(char.get("mammothIdols", 0))
    
    if current_idols < cost:
        print(f"[BuyKeys] Not enough Mammoth Idols: {current_idols} < {cost}")
        return
    
    # Deduct Mammoth Idols
    char["mammothIdols"] = current_idols - cost
    
    # Add Dragon Keys
    current_keys = int(char.get("DragonKeys", 0))
    char["DragonKeys"] = current_keys + quantity
    
    # Save character data
    save_characters(session.user_id, session.char_list)
    
    # Send Mammoth Idols deduction to client (packet 0xB5)
    # Client's method_1000 reads:
    #   1. method_13() - purchase name string
    #   2. method_4() - cost to deduct
    # Then: this.var_1.mMammothIdols -= cost
    bb_idols = BitBuffer()
    bb_idols.write_method_13(f"DragonKeys_x{quantity}")  # Purchase name string
    bb_idols.write_method_4(cost)  # Cost to deduct from idols
    idols_payload = bb_idols.to_bytes()
    idols_packet = struct.pack(">HH", 0xB5, len(idols_payload)) + idols_payload
    session.conn.sendall(idols_packet)
    
    print(f"[BuyKeys] {char.get('name', 'Unknown')} purchased {quantity} key(s) for {cost} Mammoth Idols")
    print(f"[BuyKeys] New totals - Keys: {char['DragonKeys']}, Idols: {char['mammothIdols']}")


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
    
    # Check if the NPC exists and has already granted rewards (Authoritative Check)
    level_npcs = GS.level_npcs.get(session.current_level, {})
    npc = level_npcs.get(source_id)
    
    if npc:
        if npc.get("rewards_granted", False):
            print(f"[EXPLOIT PREVENTED] {session.addr} tried to claim rewards from {source_id} again.")
            return
        npc["rewards_granted"] = True

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
        # Fix: ensure ent_type_data is not None (get_ent_type can return None)
        if ent_type_data is None:
            ent_type_data = {}
            
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

def process_drop_reward(session, x, y, gold=0, hp_gain=0, drop_gear=False, material_id=0, target_id=0, gear_tier=0, specific_gear_id=None):
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
        # Only drop gear if we have a valid specific_gear_id
        # The fallback get_random_gear_id() can return IDs without valid client graphics
        if specific_gear_id and specific_gear_id > 0:
            lid = generate_loot_id()
            gear_id = specific_gear_id
            session.pending_loot[lid] = {"gear": gear_id, "tier": gear_tier}
            
            pkt = build_lootdrop(
                loot_id=lid,
                x=x + random.randint(-20, 20),
                y=y + random.randint(-10, 10),
                gear_id=gear_id, 
                gear_tier=gear_tier
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