import time

from Character import save_characters
from bitreader import BitReader
from constants import class_20, class_7
from globals import build_hatchery_packet, pick_daily_eggs, send_premium_purchase

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