import time

from Character import save_characters
from bitreader import BitReader
from constants import get_ability_info
from globals import send_premium_purchase, send_skill_complete_packet
from scheduler import scheduler, _on_research_done_for

def handle_skill_trained_claim(session):
    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xD1] No active character")
        return

    research = char.get("SkillResearch")

    ability_id = research.get("abilityID", 0)
    if not ability_id:
        print(f"[{session.addr}] [0xD1] Missing ability ID in research")
        return

    learned = char.setdefault("learnedAbilities", [])
    for ab in learned:
        if ab["abilityID"] == ability_id:
            ab["rank"] = ab.get("rank", 0) + 1
            break
    else:
        learned.append({"abilityID": ability_id, "rank": 1})

    char["SkillResearch"] = {"abilityID": 0, "ReadyTime": 0}
    save_characters(session.user_id, session.char_list)

def handle_skill_research_cancel_request(session):
    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xDD] No active character")
        return

    char["SkillResearch"] = {"abilityID": 0, "ReadyTime": 0}
    save_characters(session.user_id, session.char_list)

def handle_skill_speed_up_request(session, data):
    br = BitReader(data[4:])
    idol_cost = br.read_method_9()

    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xDE] No active character")
        return

    research = char.get("SkillResearch")

    if idol_cost:
        char["mammothIdols"] = max(0, char.get("mammothIdols", 0) - idol_cost)
        send_premium_purchase(session, "SkillSpeedup", idol_cost)
        print(f"[{session.addr}] [0xDE] Deducted {idol_cost} idols")

    research.update({"ReadyTime": 0})
    save_characters(session.user_id, session.char_list)
    send_skill_complete_packet(session, research["abilityID"])

def handle_start_skill_training(session, data, conn):
    br = BitReader(data[4:], debug=True)
    ability_id = br.read_method_20(7)
    rank       = br.read_method_20(4)
    use_idols  = bool(br.read_method_15())

    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if not char:
        return

    info = get_ability_info(ability_id, rank)
    if not info:
        print(f"[{session.addr}] [0xBE] Invalid ability ({ability_id}, rank={rank})")
        return

    gold_cost, idol_cost, upgrade_time = map(int, (info["GoldCost"], info["IdolCost"], info["UpgradeTime"]))
    if use_idols:
        char["mammothIdols"] = max(0, char.get("mammothIdols", 0) - idol_cost)
        send_premium_purchase(session, "SkillResearch", idol_cost)
        print(f"[{session.addr}] Deducted {idol_cost} idols")
    else:
        char["gold"] = max(0, char.get("gold", 0) - gold_cost)
        print(f"[{session.addr}] Deducted {gold_cost} gold")

    ready_ts = int(time.time()) + upgrade_time
    scheduler.schedule(run_at=ready_ts,
                       callback=lambda uid=session.user_id, cname=char["name"]:
                                 _on_research_done_for(uid, cname))

    char["SkillResearch"] = {"abilityID": ability_id, "ReadyTime": ready_ts}
    save_characters(session.user_id, session.char_list)

def handle_equip_active_skills(session, raw_data):
    reader = BitReader(raw_data[4:])
    updates = {i - 1: reader.read_method_20(7)
               for i in range(1, 9) if reader.remaining_bits() >= 1 and reader.read_method_20(1)}

    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if not char:
        print(f"[WARNING] Character {session.current_character} not found in save!")
        return

    active = char.get("activeAbilities", [])
    if updates:
        max_idx = max(updates)
        if len(active) <= max_idx:
            active.extend([0] * (max_idx + 1 - len(active)))

        for idx, skill_id in updates.items():
            active[idx] = skill_id

    char["activeAbilities"] = active
    save_characters(session.user_id, session.char_list)