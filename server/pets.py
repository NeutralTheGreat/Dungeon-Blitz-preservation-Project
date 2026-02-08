import time

from accounts import save_characters
from bitreader import BitReader
from constants import class_20, class_7, class_16, Game, EGG_TYPES, PET_TYPES, class_3, CONSUMABLES
from globals import build_hatchery_packet, pick_daily_eggs, send_premium_purchase, send_pet_training_complete, \
    send_egg_hatch_start, send_new_pet_packet, GS, send_pet_xp_update, send_consumable_update
from scheduler import schedule_pet_training, schedule_egg_hatch

# Pet XP thresholds for levels 1-20 (from official game values)
PET_XP_THRESHOLDS = [
    0,       # Level 1 (starting level)
    4000,    # Level 2
    12500,   # Level 3
    24200,   # Level 4
    39400,   # Level 5
    57300,   # Level 6
    78800,   # Level 7
    103200,  # Level 8
    130100,  # Level 9
    158800,  # Level 10
    192100,  # Level 11
    229000,  # Level 12
    272100,  # Level 13
    320300,  # Level 14
    375500,  # Level 15
    434600,  # Level 16
    501100,  # Level 17
    573800,  # Level 18
    605300,  # Level 19
    744100,  # Level 20 (max)
]

def get_xp_for_level(level: int) -> int:
    """Get XP threshold for a given level"""
    if level <= 1:
        return 0
    if level > len(PET_XP_THRESHOLDS):
        return PET_XP_THRESHOLDS[-1]
    return PET_XP_THRESHOLDS[level - 1]

def get_level_for_xp(xp: int) -> int:
    """Get the level for a given XP amount"""
    for i, threshold in enumerate(PET_XP_THRESHOLDS):
        if xp < threshold:
            return i  # Return the previous level (1-indexed)
    return len(PET_XP_THRESHOLDS)  # Max level


# Helpers
##############################################################

def get_pet_training_time(rank):
    if rank < len(class_7.const_797):
        return class_7.const_797[rank]
    return 0

def get_pet_training_gold_cost(rank):
    if rank < len(class_7.const_685):
        return class_7.const_685[rank]
    return 0

def get_pet_training_idol_cost(rank):
    if rank < len(class_7.const_650):
        return class_7.const_650[rank]
    return 0

def get_egg_gold_cost(slot_index: int) -> int:
    if 0 <= slot_index < len(class_16.const_644):
        return class_16.const_644[slot_index]
    return 0

def get_egg_idol_cost(slot_index: int) -> int:
    if 0 <= slot_index < len(class_16.const_600):
        return class_16.const_600[slot_index]
    return 0

def get_egg_hatch_time(egg_rank: int, first_pet: bool) -> int:
    """# if the player has no pets  the first egg hatch time will be 180 seconds because of the Tutorial"""
    if first_pet:
        return Game.const_181  # 180 seconds
    if egg_rank == 0:
        return class_16.const_993   # 3 days
    if egg_rank == 1:
        return class_16.const_1093   # 6 days
    return class_16.const_907       # 10 days

def find_egg_def(egg_id: int):
    for e in EGG_TYPES:
        if e.get("EggID") == egg_id:
            return e
    return None

##############################################################

def handle_equip_pets(session, data):
    reader = BitReader(data[4:])

    pets = []
    for i in range(4):
        type_id = reader.read_method_6(7)
        unique_id = reader.read_method_9()
        pets.append((type_id, unique_id))

    (active_type, active_iter) = pets[0]
    resting = pets[1:]

    for char in session.char_list:
        if char.get("name") != session.current_character:
            continue

        char["activePet"] = {
            "typeID": active_type,
            "special_id": active_iter
        }

        char["restingPets"] = [
            {"typeID": resting[0][0], "special_id": resting[0][1]},
            {"typeID": resting[1][0], "special_id": resting[1][1]},
            {"typeID": resting[2][0], "special_id": resting[2][1]}
        ]

        save_characters(session.user_id, session.char_list)
        break


def handle_mount_equip_packet(session, data):
    reader = BitReader(data[4:])
    entity_id = reader.read_method_4()
    mount_id  = reader.read_method_6(class_20.const_297)

    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)

    char["equippedMount"] = mount_id
    save_characters(session.user_id, session.char_list)

    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)


def handle_request_hatchery_eggs(session, data):
    char = session.current_char_dict
    now = int(time.time())

    owned = char.get("OwnedEggsID", [])
    reset_time = char.get("EggResetTime", 0)

    # daily refresh check
    if now >= reset_time:
        max_slots = 8
        open_slots = max_slots - len(owned)

        added_eggs = []

        if open_slots > 0:
            new_egg_count = min(open_slots, 3)
            added_eggs = pick_daily_eggs(count=new_egg_count)

            owned.extend(added_eggs)

            print(f"Added new set of eggs: {added_eggs}")
        else:
            print("Hatchery is full")

        # schedule next timer
        reset_time = now + class_16.new_egg_set_time
        char["EggResetTime"] = reset_time
        char["OwnedEggsID"] = owned
        save_characters(session.user_id, session.char_list)

    else:
        pass

    char["EggNotifySent"] = False
    packet = build_hatchery_packet(owned, reset_time)
    session.conn.sendall(packet)

def handle_train_pet(session, data):
    br = BitReader(data[4:])

    type_id    = br.read_method_6(class_7.const_19)
    unique_id  = br.read_method_9()
    next_rank  = br.read_method_6(class_7.const_75)
    use_idols  = br.read_method_15()

    char = session.current_char_dict

    train_time = get_pet_training_time(next_rank)
    gold_cost  = get_pet_training_gold_cost(next_rank)
    idol_cost  = get_pet_training_idol_cost(next_rank)

    if use_idols:
        current = char.get("mammothIdols", 0)
        char["mammothIdols"] = current - idol_cost
        send_premium_purchase(session, "Pet Training", idol_cost)

    else:
        current = char.get("gold", 0)
        char["gold"] = current - gold_cost

    ready_at = int(time.time()) + train_time

    char["trainingPet"] = [{
        "typeID": type_id,
        "special_id": unique_id,
        "trainingTime": ready_at
    }]

    save_characters(session.user_id, session.char_list)
    schedule_pet_training(session.user_id, session.current_character, ready_at)

def handle_pet_training_collect(session, data):
    char = session.current_char_dict
    tp_list = char.get("trainingPet", [])

    tp = tp_list[0]
    type_id = tp["typeID"]
    special_id = tp["special_id"]

    pets = char.get("pets", [])
    for pet in pets:
        if pet["typeID"] == type_id and pet["special_id"] == special_id:
            pet["level"] = pet.get("level", 0) + 1
            break

    # Active pet?
    ap = char.get("activePet", {})
    if ap.get("special_id") == special_id:
        ap["level"] = ap.get("level", 0) + 1

    char["trainingPet"] = [{
        "typeID": 0,
        "special_id": 0,
        "trainingTime": 0
    }]

    save_characters(session.user_id, session.char_list)

def handle_pet_training_cancel(session, data):
    char = session.current_char_dict
    char["trainingPet"] = [{
        "typeID": 0,
        "special_id": 0,
        "trainingTime": 0
    }]
    save_characters(session.user_id, session.char_list)

def handle_pet_speed_up(session, data):
    br = BitReader(data[4:])
    idol_cost = br.read_method_9()

    char = session.current_char_dict
    tp_list = char.get("trainingPet", [])

    current_idols = char.get("mammothIdols", 0)
    char["mammothIdols"] = current_idols - idol_cost
    save_characters(session.user_id, session.char_list)
    send_premium_purchase(session, "Pet Training Speedup", idol_cost)

    tp = tp_list[0]
    pet_type = tp["typeID"]
    tp["trainingTime"] = 0

    save_characters(session.user_id, session.char_list)
    send_pet_training_complete(session, pet_type)

def handle_egg_hatch(session, data):
    br = BitReader(data[4:])

    slot_index = br.read_method_20(class_16.const_1251)
    use_idols  = br.read_method_15()

    char = session.current_char_dict
    owned = char.get("OwnedEggsID", [])

    # Determine which egg type is in this slot
    egg_type_id = owned[slot_index]
    egg_def = find_egg_def(egg_type_id)
    if not egg_def:
        print(f"[EGG] Unknown egg type ID: {egg_type_id}")
        return

    # Cost calculation per slot index
    gold_cost = get_egg_gold_cost(slot_index)
    idol_cost = get_egg_idol_cost(slot_index)

    # Apply currency cost
    if use_idols:
        current_idols = char.get("mammothIdols", 0)
        char["mammothIdols"] = current_idols - idol_cost
        send_premium_purchase(session, "Hatch Egg", idol_cost)
    else:
        current_gold = char.get("gold", 0)
        char["gold"] = current_gold - gold_cost

    # Compute hatch duration (class_16.method_467)
    egg_rank = egg_def.get("EggRank", 0)   # corresponds to var_392
    # first egg hatch is always 3 minutes because of the tutorial
    has_pets = bool(char.get("pets", []))
    duration = get_egg_hatch_time(egg_rank, first_pet=not has_pets)

    now = int(time.time())
    ready_time = now + duration

    char["EggHachery"] = {
        "EggID": egg_type_id,
        "ReadyTime": ready_time,
        "slotIndex": slot_index,
    }
    char["activeEggCount"] = 1
    save_characters(session.user_id, session.char_list)
    schedule_egg_hatch(session.user_id, session.current_character, ready_time)

def handle_egg_speed_up(session, data):
    br = BitReader(data[4:])
    idol_cost_client = br.read_method_9()

    char = session.current_char_dict

    egg_data = char.get("EggHachery")

    egg_id = egg_data["EggID"]
    current_idols = char.get("mammothIdols", 0)

    char["mammothIdols"] = current_idols - idol_cost_client
    send_premium_purchase(session, "Egg Hatch Speedup", idol_cost_client)

    egg_data["ReadyTime"] = 0   # 0 == finished (client logic)

    save_characters(session.user_id, session.char_list)
    send_egg_hatch_start(session)


def handle_collect_hatched_egg(session, data):
    char = session.current_char_dict
    egg_data = char.get("EggHachery")
    egg_id = egg_data["EggID"]

    pet_def = next((p for p in PET_TYPES if p.get("PetID") == egg_id), None)
    if not pet_def:
        print(f"[EGG] ERROR: No pet definition for EggID/PetID={egg_id}")
        return

    pet_type_id   = pet_def["PetID"]
    starting_rank = 1

    pets = char.get("pets", [])
    special_id = max((p.get("special_id", 0) for p in pets), default=0) + 1

    new_pet = {
        "typeID":     pet_type_id,
        "special_id": special_id,
        "level":      starting_rank,
        "xp":         0,
    }

    pets.append(new_pet)
    char["pets"] = pets

    # Remove the egg from OwnedEggsID at that slot
    owned_eggs = char.get("OwnedEggsID", [])
    slot_index = egg_data.get("slotIndex", None)

    if slot_index is not None and 0 <= slot_index < len(owned_eggs):
        removed = owned_eggs.pop(slot_index)

    char["EggHachery"] = {
        "EggID":    0,
        "ReadyTime": 0,
        "slotIndex": 0,
    }
    char["activeEggCount"] = 0

    save_characters(session.user_id, session.char_list)
    send_new_pet_packet(session, pet_type_id, special_id, starting_rank)

    # Send updated hatchery packet so client refreshes barn
    hatch_packet = build_hatchery_packet(owned_eggs, char.get("EggResetTime", 0))
    session.conn.sendall(hatch_packet)

def handle_cancel_egg_hatch(session, data):
    char = session.current_char_dict

    char["EggHachery"] = {
        "EggID": 0,
        "ReadyTime": 0,
        "slotIndex": 0,
    }
    char["activeEggCount"] = 0

    save_characters(session.user_id, session.char_list)

def handle_use_pet_food(session, data):
    """
    Handle pet food usage
    ConsumableID 10 = RarePetFood (Arcane Chew Bone) - 60000 XP + 1 level
    ConsumableID 11 = PetFood (Savory Steak) - 30000 XP
    
    NOTE: Client only sends consumable ID, not pet info.
    The food is always applied to the currently active pet.
    """
    br = BitReader(data[4:])
    
    # Read the consumable ID (client only sends this)
    consumable_id = br.read_method_6(class_3.const_69)  # 5 bits
    
    print(f"[PET FOOD] Using consumable {consumable_id}")
    
    char = session.current_char_dict
    if not char:
        print("[PET FOOD] ERROR: No character data")
        return
    
    # Find the consumable definition
    consumable_def = None
    for c in CONSUMABLES:
        if c.get("ConsumableID") == consumable_id:
            consumable_def = c
            break
    
    if not consumable_def or consumable_def.get("Type") != "PetFood":
        print(f"[PET FOOD] ERROR: Invalid consumable ID {consumable_id} or not PetFood type")
        return
    
    xp_amount = consumable_def.get("Magnitude", 0)
    is_rare_pet_food = consumable_def.get("ConsumableName") == "RarePetFood"
    
    # Check if player has this consumable
    consumables = char.get("consumables", [])
    consumable_entry = None
    for entry in consumables:
        if entry.get("consumableID") == consumable_id:
            consumable_entry = entry
            break
    
    if not consumable_entry or consumable_entry.get("count", 0) <= 0:
        print(f"[PET FOOD] ERROR: Player doesn't have consumable {consumable_id}")
        return
    
    # Get the active pet from character data
    # Try multiple sources: activePet, equippedPets, or first pet in pets list
    active_pet_info = char.get("activePet", {})
    pet_type_id = active_pet_info.get("typeID", 0)
    pet_special_id = active_pet_info.get("special_id", 0)
    
    # If activePet is empty, try equippedPets (first equipped pet)
    if pet_type_id == 0:
        equipped_pets = char.get("equippedPets", [])
        if equipped_pets and len(equipped_pets) > 0:
            first_equipped = equipped_pets[0]
            pet_type_id = first_equipped.get("typeID", 0)
            pet_special_id = first_equipped.get("special_id", 0)
    
    # If still no pet found, try the first pet from pets list
    if pet_type_id == 0:
        pets = char.get("pets", [])
        if pets and len(pets) > 0:
            first_pet = pets[0]
            pet_type_id = first_pet.get("typeID", 0)
            pet_special_id = first_pet.get("special_id", 0)
    
    if pet_type_id == 0:
        print("[PET FOOD] ERROR: No active pet found in any source")
        return
    
    print(f"[PET FOOD] Applying to pet type={pet_type_id}, special={pet_special_id}")
    
    # Find the pet in the player's pets list
    pets = char.get("pets", [])
    target_pet = None
    for pet in pets:
        if pet.get("typeID") == pet_type_id and pet.get("special_id") == pet_special_id:
            target_pet = pet
            break
    
    if not target_pet:
        print(f"[PET FOOD] ERROR: Pet not found type={pet_type_id}, special={pet_special_id}")
        return
    
    # Get current XP and level
    current_xp = target_pet.get("xp", 0)
    current_level = target_pet.get("level", 1)
    
    # Add XP
    new_xp = current_xp + xp_amount
    
    # Arcane Chew Bone (RarePetFood) also grants +1 level
    # Savory Steak (PetFood) only grants XP, no level change
    if is_rare_pet_food:
        new_level = min(current_level + 1, 20)  # +1 level, max 20
    else:
        new_level = current_level  # Level stays the same
    
    # Update pet data
    target_pet["xp"] = new_xp
    target_pet["level"] = new_level
    
    # Also update activePet if this is the active pet
    active_pet = char.get("activePet", {})
    if active_pet.get("special_id") == pet_special_id:
        active_pet["xp"] = new_xp
        active_pet["level"] = new_level
    
    # Decrease consumable count
    consumable_entry["count"] = consumable_entry.get("count", 1) - 1
    new_count = consumable_entry["count"]
    
    # Save changes
    save_characters(session.user_id, session.char_list)
    
    # Send consumable update to client
    send_consumable_update(session.conn, consumable_id, new_count)
    
    # Send pet XP update to client
    # IMPORTANT: Client ADDS the value to current XP (not sets it)
    # So we send the XP gain amount (xp_amount), not the total (new_xp)
    send_pet_xp_update(session, pet_type_id, pet_special_id, xp_amount, new_level, is_rare_pet_food)
    
    if is_rare_pet_food:
        print(f"[PET FOOD] Success: Pet XP {current_xp} -> {new_xp}, Level {current_level} -> {new_level}")
    else:
        print(f"[PET FOOD] Success: Pet XP {current_xp} -> {new_xp}, Level stays at {current_level}")