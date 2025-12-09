import time

from Character import save_characters
from bitreader import BitReader
from constants import class_20, class_7, class_16, Game, EGG_TYPES, PET_TYPES
from globals import build_hatchery_packet, pick_daily_eggs, send_premium_purchase, send_pet_training_complete, \
    send_egg_hatch_start, send_new_pet_packet
from scheduler import schedule_pet_training, schedule_egg_hatch


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
    if first_pet:
        return Game.const_181  # 180 seconds

    # class_16.const_303 = 0, const_376 = 1
    if egg_rank == 0:
        return 259200   # 3 days
    if egg_rank == 1:
        return 518400   # 6 days
    return 864000       # 10 days

def find_egg_def(egg_id: int):
    for e in EGG_TYPES:
        if e.get("EggID") == egg_id:
            return e
    return None

##############################################################

def handle_equip_pets(session, data, all_sessions):
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


def handle_mount_equip_packet(session, data, all_sessions):
    reader = BitReader(data[4:])
    entity_id = reader.read_method_4()
    mount_id  = reader.read_method_6(class_20.const_297)

    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)

    char["equippedMount"] = mount_id
    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)

    for other in all_sessions:
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
        reset_time = now + 86400
        char["EggResetTime"] = reset_time
        char["OwnedEggsID"] = owned
        save_characters(session.user_id, session.char_list)

    else:
        print("new egg set is not ready yet")

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