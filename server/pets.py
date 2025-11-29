from Character import save_characters
from bitreader import BitReader

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
