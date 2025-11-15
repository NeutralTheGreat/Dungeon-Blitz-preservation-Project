import time

from Character import save_characters
from bitreader import BitReader
from constants import find_building_data
from globals import send_premium_purchase, send_building_complete_packet
from scheduler import schedule_building_upgrade

def handle_building_upgrade(session, data):
    br = BitReader(data[4:], debug=True)
    building_id = br.read_method_20(5)
    target_rank = br.read_method_20(5)
    used_idols = bool(br.read_method_15())

    char = next(c for c in session.char_list if c["name"] == session.current_character)
    mf = char.setdefault("magicForge", {})
    stats = mf.setdefault("stats_by_building", {})
    current_rank = int(stats.get(str(building_id), 0))

    bdata = find_building_data(building_id, target_rank)
    if not bdata:
        return

    gold_cost = int(bdata["GoldCost"])
    idol_cost = int(bdata.get("IdolCost", 0))
    upgrade_time = int(bdata["UpgradeTime"])

    if used_idols:
        idols = int(char.get("mammothIdols", 0))
        if idols < idol_cost:
            print(f"[{session.addr}] Not enough idols ({idols} < {idol_cost})")
            return
        char["mammothIdols"] = idols - idol_cost
        send_premium_purchase(session, "BuildingUpgrade", idol_cost)
    else:
        gold = int(char.get("gold", 0))
        if gold < gold_cost:
            print(f"[{session.addr}] Not enough gold ({gold} < {gold_cost})")
            return
        char["gold"] = gold - gold_cost

    ready_time = int(time.time()) + upgrade_time
    char["buildingUpgrade"] = {
        "buildingID": building_id,
        "rank": target_rank,
        "ReadyTime": ready_time,
        "done": False
    }

    save_characters(session.user_id, session.char_list)
    schedule_building_upgrade(session.user_id, session.current_character, ready_time)

def handle_building_speed_up_request(session, data):
    br = BitReader(data[4:], debug=True)
    idol_cost = br.read_method_9()
    char = next((c for c in session.char_list if c["name"] == session.current_character), None)

    if idol_cost > 0:
        char["mammothIdols"] = max(0, char.get("mammothIdols", 0) - idol_cost)
        send_premium_purchase(session, "BuildingSpeedup", idol_cost)

    upgrade = char.get("buildingUpgrade", {})
    building_id = upgrade.get("buildingID", 0)
    new_rank = upgrade.get("rank", 0)

    if not building_id or not new_rank:
        save_characters(session.user_id, session.char_list)
        return

    stats = char.setdefault("magicForge", {}).setdefault("stats_by_building", {})
    stats[str(building_id)] = new_rank
    char["buildingUpgrade"] = {"buildingID": 0, "rank": 0, "ReadyTime": 0, "done": False}
    save_characters(session.user_id, session.char_list)

    mem_char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if mem_char:
        mem_char["mammothIdols"] = char["mammothIdols"]
        mem_char.setdefault("magicForge", {})["stats_by_building"] = stats.copy()
        mem_char["buildingUpgrade"] = char["buildingUpgrade"].copy()

    send_building_complete_packet(session, building_id, new_rank)

def handle_cancel_building_upgrade(session, data):
    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    upgrade = char.get("buildingUpgrade", {})
    building_id = upgrade.get("buildingID", 0)

    char["buildingUpgrade"] = {"buildingID": 0, "rank": 0, "ReadyTime": 0, "done": False}
    save_characters(session.user_id, session.char_list)

    mem_char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if mem_char:
        mem_char["buildingUpgrade"] = char["buildingUpgrade"].copy()

def handle_building_claim(session, data):
    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)

    upgrade = char.get("buildingUpgrade", {})
    building_id = upgrade.get("buildingID", 0)
    rank = upgrade.get("rank", 0)

    char["buildingUpgrade"] = {"buildingID": 0, "rank": 0, "ReadyTime": 0, "done": False}
    save_characters(session.user_id, session.char_list)

    mem_char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if mem_char:
        mem_char["buildingUpgrade"] = char["buildingUpgrade"].copy()
