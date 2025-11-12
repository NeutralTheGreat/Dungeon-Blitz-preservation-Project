import struct
import time

from BitBuffer import BitBuffer
from Character import save_characters
from bitreader import BitReader
from constants import index_to_node_id, class_118, method_277, class_66
from globals import send_premium_purchase
from scheduler import scheduler, schedule_Talent_point_research, _on_talent_done_for

def handle_respec_talent_tree(session, data):
    """
    Handles client request 0xD2 to reset the talent tree using a Respec Stone.
    Deducts one Respec Stone (charmID 91) from the character's inventory.
    """
    try:
        char = next((c for c in session.char_list if c["name"] == session.current_character), None)
        if not char:
            return

        charms = char.setdefault("charms", [])
        for entry in charms:
            if entry.get("charmID") == 91:
                if entry.get("count", 0) > 0:
                    entry["count"] -= 1
                    if entry["count"] <= 0:
                        charms.remove(entry)
                break
        else:
            # this is probably not needed but placing it here just in case
            print(f"[{session.addr}] No Respec Stones available for {char['name']}")
            return

        mc = str(char.get("MasterClass", 1))
        talent_tree = char.setdefault("TalentTree", {}).setdefault(mc, {})

        # Reset all 27 slots
        talent_tree["nodes"] = [
            {"nodeID": index_to_node_id(i), "points": 0, "filled": False}
            for i in range(27)
        ]

        save_characters(session.user_id, session.char_list)
        print(f"[{session.addr}] Talent tree reset and 1 Respec Stone used for {char['name']}")

    except Exception as e:
        print(f"[{session.addr}] [PKT_RESPEC] Error: {e}")

def handle_allocate_talent_tree_points(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        char = next((c for c in session.char_list if c["name"] == session.current_character), None)
        if not char:
            print(f"[{session.addr}] [PKT_TALENT_UPGRADE] No active character found")
            return

        master_class = str(char.get("MasterClass", 1))
        talent_tree = char.setdefault("TalentTree", {}).setdefault(master_class, {})

        # Initialize a 27-slot array to emulate client var_58
        slots = [None] * 27

        # Parse full tree (27 slots)
        for i in range(27):
            has_node = br.read_method_15()
            node_id = index_to_node_id(i)

            if has_node:
                # Node ID from packet
                node_id_from_packet = br.read_method_6(class_118.const_127)
                points_spent = br.read_method_6(method_277(i)) + 1  # +1 for node itself
                slots[i] = {
                    "nodeID": node_id_from_packet,
                    "points": points_spent,
                    "filled": True
                }
            else:
                # Empty slot
                slots[i] = {
                    "nodeID": node_id,
                    "points": 0,
                    "filled": False
                }

        # Parse incremental actions
        actions = []
        while br.read_method_15():
            is_signet = br.read_method_15()
            if is_signet:
                node_index = br.read_method_6(class_118.const_127)
                signet_group = br.read_method_6(class_118.const_127)
                signet_index = br.read_method_6(class_118.const_127) - 1
                actions.append({
                    "action": "signet",
                    "nodeIndex": node_index,
                    "signetGroup": signet_group,
                    "signetIndex": signet_index
                })
            else:
                node_index = br.read_method_6(class_118.const_127)
                actions.append({
                    "action": "upgrade",
                    "nodeIndex": node_index
                })

        # Save back to TalentTree in array order
        talent_tree["nodes"] = slots

        # Persist to player data and database
        session.player_data["characters"] = session.char_list
        save_characters(session.user_id, session.char_list)

        print(f"[{session.addr}] [PKT_TALENT_UPGRADE] Updated TalentTree[{master_class}]")
        for idx, slot in enumerate(slots):
            print(f"  Slot {idx + 1}: {slot}")
        print(f"  → Actions: {actions}")

    except Exception as e:
        print(f"[{session.addr}] [PKT_TALENT_UPGRADE] Error parsing: {e}")
        for line in br.get_debug_log():
            print(line)

def handle_talent_claim(session, data):
    """
    Handle 0xD6: client claiming a completed talent research.
    Client sends this with an empty payload after upgrading is done.
    Server should persist the talent point and clear talentResearch.
    """
    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xD6] no character found")
        return

    tr = char.get("talentResearch", {})
    class_idx = tr.get("classIndex")

    # Award the point (server-side persistence)
    pts = char.setdefault("talentPoints", {})
    pts[str(class_idx)] = pts.get(str(class_idx), 0) + 1

    # Clear research state
    char["talentResearch"] = {
        "classIndex": None,
        "ReadyTime": 0,
        "done": False,
    }

    # Persist save
    save_characters(session.user_id, session.char_list)

    # Mirror to in-memory session
    mem_char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if mem_char:
        mem_char.setdefault("talentPoints", {})[str(class_idx)] = pts[str(class_idx)]
        mem_char["talentResearch"] = char["talentResearch"].copy()

    print(f"[{session.addr}] [0xD6] Awarded talent point for classIndex={class_idx}")

def handle_talent_speedup(session, data):
    """
    Handle 0xE0: client clicked Speed-up on talent research.
    Client sends the idol cost (0 if free).
    """
    # 1) Parse idol cost
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        idol_cost = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [0xE0] parse error: {e}")
        return

    print(f"[{session.addr}] [0xE0] Talent speed-up requested: cost={idol_cost}")

    # 2) Locate character
    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xE0] no character found")
        return

    tr = char.get("talentResearch", {})
    class_idx = tr.get("classIndex")

    # 3) Deduct idols if cost > 0
    if idol_cost > 0:
        char["mammothIdols"] = char.get("mammothIdols", 0) - idol_cost
        send_premium_purchase(session, "TalentSpeedup", idol_cost)
        print(f"[{session.addr}] [0xE0] Deducted {idol_cost} idols")

    # 4) Cancel scheduler if one exists
    sched_id = tr.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
            print(f"[{session.addr}] canceled scheduled research id={sched_id}")
        except Exception:
            pass

    # 5) Mark research complete immediately
    tr["ReadyTime"] = 0
    tr["done"] = True
    char["talentResearch"] = tr

    # 6) Persist & mirror in memory
    save_characters(session.user_id, session.char_list)
    mem = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if mem:
        mem["mammothIdols"] = char["mammothIdols"]
        mem["talentResearch"] = tr.copy()

    # 7) Send the 0xD5 “complete” notification
    try:
        bb = BitBuffer()
        bb.write_method_6(class_idx, class_66.const_571)  # classIndex
        bb.write_method_6(1, 1)                           # status=complete
        payload = bb.to_bytes()
        session.conn.sendall(struct.pack(">HH", 0xD5, len(payload)) + payload)
        print(f"[{session.addr}] [0xE0] sent 0xD5 to mark research complete")
    except Exception as e:
        print(f"[{session.addr}] [0xE0] failed to send 0xD5: {e}")

def handle_train_talent_point(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        class_index = br.read_method_20(2)
        # client doesn’t actually send an instant flag — discard
        br.read_method_15()
    except Exception as e:
        print(f"[{session.addr}] [PKT0xD4] parse error: {e}")
        return

    char = next((c for c in session.char_list if c["name"] == session.current_character), None)
    if not char:
        return

    pts = char.setdefault("talentPoints", {})
    current_points = pts.get(str(class_index), 0)

    # Duration and costs
    duration_idx = current_points + 1
    duration = class_66.RESEARCH_DURATIONS[duration_idx]
    gold_cost = class_66.RESEARCH_COSTS[duration_idx]
    idol_cost = class_66.IDOL_COST[duration_idx]

    now = int(time.time())

    if char.get("gold", 0) >= gold_cost:
        # Gold path = timed research
        char["gold"] -= gold_cost
        ready_ts = now + duration
        char["talentResearch"] = {
            "classIndex": class_index,
            "ReadyTime": ready_ts,
            "done": False
        }
        print(f"[{session.addr}] Deducted {gold_cost} gold for research → ready in {duration}s")
        save_characters(session.user_id, session.char_list)
        schedule_Talent_point_research(session.user_id, session.current_character, ready_ts)

    else:
        # Idol path = instant research
        if char.get("mammothIdols", 0) < idol_cost:
            print(f"[{session.addr}] Insufficient idols: {char.get('mammothIdols')} < {idol_cost}")
            return
        char["mammothIdols"] -= idol_cost
        char["talentResearch"] = {
            "classIndex": class_index,
            "ReadyTime": now,  # instant
            "done": False
        }
        print(f"[{session.addr}] Deducted {idol_cost} idols for instant research")
        save_characters(session.user_id, session.char_list)
        send_premium_purchase(session, "TalentResearch", idol_cost)
        _on_talent_done_for(session.user_id, session.current_character)

def handle_clear_talent_research(session, data):
    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xDF] no character found")
        return

    # 2) Cancel any pending scheduler
    tr = char.get("talentResearch", {})
    sched_id = tr.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
            print(f"[{session.addr}] [0xDF] canceled scheduled research id={sched_id}")
        except Exception as e:
            print(f"[{session.addr}] [0xDF] failed to cancel schedule: {e}")

    # 3) Clear the research state
    char["talentResearch"] = {
        "classIndex": None,
        "ReadyTime":  0,
        "done":       False,
    }

    # 4) Persist and mirror session
    save_characters(session.user_id, session.char_list)
    mem = next((c for c in session.char_list
                if c.get("name") == session.current_character), None)
    if mem:
        mem["talentResearch"] = char["talentResearch"].copy()

    print(f"[{session.addr}] [0xDF] talentResearch cleared for {session.current_character}")
