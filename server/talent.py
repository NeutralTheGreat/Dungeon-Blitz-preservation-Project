import struct
import time

from BitBuffer import BitBuffer
from Character import save_characters
from bitreader import BitReader
from constants import index_to_node_id, class_118, method_277, class_66, Game
from globals import send_premium_purchase, send_talent_point_research_complete
from scheduler import scheduler, schedule_Talent_point_research, _on_talent_done_for

def handle_respec_talent_tree(session, data):
    char = next((c for c in session.char_list
                 if c["name"] == session.current_character), None)
    if not char:
        return

    charms = char.get("charms", [])
    for entry in charms:
        if entry.get("charmID") == 91 and entry.get("count", 0) > 0:
            entry["count"] -= 1
            if entry["count"] <= 0:
                charms.remove(entry)
            break
    else:
        return

    mc = str(char.get("MasterClass", 1))
    talent_tree = char.setdefault("TalentTree", {}).setdefault(mc, {})

    # reset 27 nodes
    talent_tree["nodes"] = [
        {"nodeID": index_to_node_id(i), "points": 0, "filled": False}
        for i in range(27)
    ]

    save_characters(session.user_id, session.char_list)

def handle_allocate_talent_tree_points(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    char = next((c for c in session.char_list if c["name"] == session.current_character), None)

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

    talent_tree["nodes"] = slots

    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)

def handle_talent_claim(session, data):
    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        return

    tr = char.get("talentResearch", {})
    class_idx = tr.get("classIndex")
    if class_idx is None:
        return

    pts = char.setdefault("talentPoints", {})
    pts[str(class_idx)] = pts.get(str(class_idx), 0) + 1

    sched_id = tr.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
        except:
            pass

    char["talentResearch"] = {
        "classIndex": None,
        "ReadyTime": 0
    }

    save_characters(session.user_id, session.char_list)

    mem_char = next((c for c in session.char_list
                     if c.get("name") == session.current_character), None)
    if mem_char:
        mem_char.setdefault("talentPoints", {})[str(class_idx)] = pts[str(class_idx)]
        mem_char["talentResearch"] = char["talentResearch"].copy()

def handle_talent_speedup(session, data):
    payload = data[4:]
    br = BitReader(payload)

    try:
        idol_cost = br.read_method_9()
    except:
        return

    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        return

    tr = char.get("talentResearch", {})
    class_idx = tr.get("classIndex")
    if class_idx is None:
        return

    if idol_cost > 0:
        current_idols = char.get("mammothIdols", 0)
        if current_idols < idol_cost:
            return
        char["mammothIdols"] = current_idols - idol_cost
        send_premium_purchase(session, "TalentSpeedup", idol_cost)

    sched_id = tr.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
        except:
            pass

    tr["ReadyTime"] = 0
    char["talentResearch"] = tr

    save_characters(session.user_id, session.char_list)

    mem = next((c for c in session.char_list
                if c.get("name") == session.current_character), None)
    if mem:
        mem["mammothIdols"] = char["mammothIdols"]
        mem["talentResearch"] = tr.copy()

    send_talent_point_research_complete(session, class_idx)

def handle_train_talent_point(session, data):
    payload = data[4:]
    br = BitReader(payload)

    class_index = br.read_method_20(2)
    is_instant = br.read_method_15()   # TRUE = idols instant, FALSE = gold timed

    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        return

    pts = char.setdefault("talentPoints", {})
    current_points = pts.get(str(class_index), 0)

    duration_idx = current_points + 1
    duration = class_66.RESEARCH_DURATIONS[duration_idx]
    gold_cost = class_66.RESEARCH_COSTS[duration_idx]
    idol_cost = class_66.IDOL_COST[duration_idx]

    now = int(time.time())

    if is_instant:
        if char.get("mammothIdols", 0) < idol_cost:
            return

        char["mammothIdols"] -= idol_cost
        tr = {
            "classIndex": class_index,
            "ReadyTime": now
        }
        char["talentResearch"] = tr

        save_characters(session.user_id, session.char_list)
        send_premium_purchase(session, "TalentResearch", idol_cost)

        # Immediately complete
        _on_talent_done_for(session.user_id, session.current_character)

        mem = next((c for c in session.char_list
                    if c.get("name") == session.current_character), None)
        if mem:
            mem["mammothIdols"] = char["mammothIdols"]
            mem["talentResearch"] = tr.copy()

        return

    if char.get("gold", 0) < gold_cost:
        return

    char["gold"] -= gold_cost

    ready_ts = now + duration
    tr = {
        "classIndex": class_index,
        "ReadyTime": ready_ts
    }
    char["talentResearch"] = tr

    save_characters(session.user_id, session.char_list)

    schedule_Talent_point_research(
        session.user_id,
        session.current_character,
        ready_ts
    )

    mem = next((c for c in session.char_list
                if c.get("name") == session.current_character), None)
    if mem:
        mem["gold"] = char["gold"]
        mem["talentResearch"] = tr.copy()

def handle_clear_talent_research(session, data):
    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        return

    tr = char.get("talentResearch", {})
    sched_id = tr.pop("schedule_id", None)
    if sched_id:
        try:
            scheduler.cancel(sched_id)
        except:
            pass

    char["talentResearch"] = {
        "classIndex": None,
        "ReadyTime": 0
    }

    save_characters(session.user_id, session.char_list)

    mem = next((c for c in session.char_list
                if c.get("name") == session.current_character), None)
    if mem:
        mem["talentResearch"] = char["talentResearch"].copy()

def send_active_talent_tree_data(session, entity_id):
    mc = None
    nodes = [None] * class_118.NUM_TALENT_SLOTS

    for char in session.char_list:
        if char.get("name") == session.current_character:
            mc = char.get("MasterClass", 1)
            tree = char.get("TalentTree", {}).get(str(mc), {})
            nodes = tree.get("nodes", [None] * class_118.NUM_TALENT_SLOTS)
            break
    else:
        return

    session.player_data["characters"] = session.char_list

    bb = BitBuffer()
    bb.write_method_4(entity_id)

    for i, slot in enumerate(nodes):
        slot = slot or {"filled": False, "points": 0, "nodeID": i + 1}

        if slot.get("filled", False):
            bb.write_method_6(1, 1)  # has this node
            node_id = slot.get("nodeID", i + 1)
            bb.write_method_6(node_id, class_118.const_127)  # send nodeIdx (1-based)
            width = method_277(i)
            bb.write_method_6(slot["points"] - 1, width)
        else:
            bb.write_method_6(0, 1)  # no node present

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0xC1, len(payload)) + payload
    session.conn.sendall(pkt)

def handle_active_talent_change_request(session, raw_data):
    payload = raw_data[4:]
    br = BitReader(payload)
    entity_id       = br.read_method_4()
    master_class_id = br.read_method_6(Game.const_209)

    for char in session.char_list:
        if char.get("name") == session.current_character:
            char["MasterClass"] = master_class_id
            break
    else:
        return

    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)

    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_6(master_class_id, Game.const_209)
    resp = struct.pack(">HH", 0xC3, len(bb.to_bytes())) + bb.to_bytes()
    session.conn.sendall(resp)
    send_active_talent_tree_data(session, entity_id)
