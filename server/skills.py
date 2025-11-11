import struct
import time

from BitBuffer import BitBuffer
from Character import save_characters
from bitreader import BitReader
from constants import get_ability_info
from globals import send_premium_purchase
from scheduler import scheduler, _on_research_done_for


def handle_skill_trained_claim(session):
    """
    Handle packet 0xD1: player claims completed skill research.
    """
    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] No character found to complete research")
        return

    research = char.get("SkillResearch")
    if not research or not research.get("done"):
        print(f"[{session.addr}] No completed research to claim")
        return

    ability_id = research["abilityID"]

    # Find or add ability
    learned = char.setdefault("learnedAbilities", [])
    for ab in learned:
        if ab["abilityID"] == ability_id:
            ab["rank"] += 1
            break
    else:
        learned.append({"abilityID": ability_id, "rank": 1})

    print(f"[{session.addr}] Claimed research: abilityID={ability_id}")

    char["SkillResearch"] = {
        "abilityID": 0,
        "ReadyTime": 0,
        "done": True
    }

    save_characters(session.user_id, session.char_list)


def handle_skill_research_cancel_request(session):
    """
    Handle 0xDD: cancel skill research.
    Clears research state and cancels any pending scheduler.
    """
    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xDD] Cannot cancel research: no character found")
        return

    research = char.get("SkillResearch")
    if not research or research.get("done"):
        print(f"[{session.addr}] [0xDD] No active research to cancel")
        return

    ability_id = research.get("abilityID")

    # Cancel any scheduled completion task
    sched_id = research.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
            print(f"[{session.addr}] [0xDD] Cancelled scheduled research id={sched_id}")
        except Exception as e:
            print(f"[{session.addr}] [0xDD] Failed to cancel scheduler: {e}")

    # Clear research state
    char["SkillResearch"] = {
        "abilityID": 0,
        "ReadyTime": 0,
        "done": True
    }

    save_characters(session.user_id, session.char_list)
    print(f"[{session.addr}] [0xDD] Research cancelled for abilityID={ability_id}")


def handle_skill_speed_up_request(session, data):
    """
    Handles skill research speed-up request (0xDE).
    Deducts idols, completes research immediately,
    and sends 0xBF + idol update (0xB5).
    """
    br = BitReader(data[4:])
    idol_cost = br.read_method_9()

    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xDE] Cannot speed up: no character found")
        return

    research = char.get("SkillResearch")
    if not research or research.get("done"):
        print(f"[{session.addr}] [0xDE] No active research to speed up")
        return

    if idol_cost > 0:
        char["mammothIdols"] = char.get("mammothIdols", 0) - idol_cost
        send_premium_purchase(session, "SkillSpeedup", idol_cost)
        print(f"[{session.addr}] [0xDE] Deducted {idol_cost} idols for skill speed-up")

    # Complete instantly
    research["ReadyTime"] = 0
    research["done"] = True
    save_characters(session.user_id, session.char_list)

    # Mirror in-memory
    mem_char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if mem_char:
        mem_char["mammothIdols"] = char["mammothIdols"]
        mem_char["SkillResearch"] = research.copy()

    # Send completion packet 0xBF
    try:
        bb = BitBuffer()
        bb.write_method_6(research["abilityID"], 7)
        payload = bb.to_bytes()
        session.conn.sendall(struct.pack(">HH", 0xBF, len(payload)) + payload)
        print(f"[{session.addr}] [0xDE] Sent 0xBF complete for abilityID={research['abilityID']}")
    except Exception as e:
        print(f"[{session.addr}] [0xDE] Failed to send 0xBF: {e}")


def handle_start_skill_training(session, data, conn):
    br = BitReader(data[4:], debug=True)
    try:
        ability_id = br.read_method_20(7)
        rank       = br.read_method_20(4)
        used_idols = bool(br.read_method_15())

        print(f"[{session.addr}] [0xBE] Skill upgrade request: "
              f"abilityID={ability_id}, rank={rank}, idols={used_idols}")

        char = next((c for c in session.char_list
                     if c.get("name") == session.current_character), None)
        if not char:
            return

        # --- Lookup by ID + Rank ---
        ability_data = get_ability_info(ability_id, rank)
        if not ability_data:
            print(f"[{session.addr}] [0xBE] Invalid ability/rank ({ability_id}, {rank})")
            return

        gold_cost    = int(ability_data["GoldCost"])
        idol_cost    = int(ability_data["IdolCost"])
        upgrade_time = int(ability_data["UpgradeTime"])

        # --- Deduct currency ---
        if used_idols:
            char["mammothIdols"] = char.get("mammothIdols", 0) - idol_cost
            send_premium_purchase(session, "SkillResearch", idol_cost)
            print(f"[{session.addr}] Deducted {idol_cost} idols for skill upgrade")
        else:
            char["gold"] = char.get("gold", 0) - gold_cost
            print(f"[{session.addr}] Deducted {gold_cost} gold for skill upgrade")

        # --- Save research state ---
        ready_ts = int(time.time()) + upgrade_time
        sched_id = scheduler.schedule(
            run_at=ready_ts,
            callback=lambda uid=session.user_id, cname=char["name"]:
                _on_research_done_for(uid, cname)
        )

        char["SkillResearch"] = {
            "abilityID": ability_id,
            "ReadyTime": ready_ts,
            "done": False,
        }
        save_characters(session.user_id, session.char_list)

        print(f"[{session.addr}] [0xBE] Research scheduled: ready at {ready_ts}, id={sched_id}")

    except Exception as e:
        print(f"[{session.addr}] [0xBE] Error: {e}")


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
    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)
