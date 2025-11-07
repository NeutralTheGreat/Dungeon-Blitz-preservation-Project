import struct
import time

from BitBuffer import BitBuffer
from Character import save_characters
from bitreader import BitReader
from constants import find_building_data
from globals import send_premium_purchase
from scheduler import schedule_building_upgrade


def handle_building_upgrade(session, data):
    try:
        payload = data[4:]
        br = BitReader(payload, debug=True)

        building_id = br.read_method_20(5)
        client_rank = br.read_method_20(5)
        used_idols  = bool(br.read_method_15())

        print(f"[{session.addr}] [0xD7] Upgrade request: "
              f"buildingID={building_id}, rank={client_rank}, idols={used_idols}")

        char = next(c for c in session.char_list if c["name"] == session.current_character)

        mf = char.setdefault("magicForge", {})
        stats_dict = mf.setdefault("stats_by_building", {})
        current_rank = stats_dict.get(str(building_id), 0)

        # Sanity: requested rank must be exactly +1
        if client_rank != current_rank + 1:
            print(f"[{session.addr}] [0xD7] invalid rank upgrade "
                  f"(current={current_rank}, requested={client_rank})")
            return

        bdata        = find_building_data(building_id, client_rank)
        gold_cost    = int(bdata["GoldCost"])
        idol_cost    = int(bdata.get("IdolCost", 0))
        upgrade_time = int(bdata["UpgradeTime"])

        if used_idols:
            current_idols = int(char.get("mammothIdols", 0))
            if current_idols < idol_cost:
                print(f"[{session.addr}] [0xD7] not enough idols ({current_idols} < {idol_cost})")
                return
            char["mammothIdols"] = current_idols - idol_cost
            send_premium_purchase(session, "BuildingUpgrade", idol_cost)
            print(f"[{session.addr}] Deducted {idol_cost} idols for upgrade "
                  f"→ Remaining: {char['mammothIdols']}")
        else:
            current_gold = int(char.get("gold", 0))
            if current_gold < gold_cost:
                print(f"[{session.addr}] [0xD7] not enough gold ({current_gold} < {gold_cost})")
                return
            char["gold"] = current_gold - gold_cost
            print(f"[{session.addr}] Deducted {gold_cost} gold for upgrade "
                  f"→ Remaining: {char['gold']}")

        now = int(time.time())
        ready_time = now + upgrade_time

        char["buildingUpgrade"] = {
            "buildingID": building_id,
            "rank": client_rank,
            "ReadyTime": ready_time,
            "done": False
        }

        for i, c in enumerate(session.char_list):
            if c["name"] == session.current_character:
                session.char_list[i] = char
                break

        save_characters(session.user_id, session.char_list)
        schedule_building_upgrade(
            session.user_id,
            session.current_character,
            ready_time
        )

    except Exception as e:
        print(f"[{session.addr}] [0xD7] Error: {e}")

def handle_building_speed_up_request(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        idol_cost = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [0xDC] parse error: {e}")
        return

    print(f"[{session.addr}] [0xDC] Speed-up requested: cost={idol_cost}")

    # --- Locate character ---
    char = next((c for c in session.char_list
                 if c["name"] == session.current_character), None)
    if not char:
        return

    # --- Deduct idols and notify client ---
    if idol_cost > 0:
        char["mammothIdols"] = char.get("mammothIdols", 0) - idol_cost
        send_premium_purchase(session, "BuildingSpeedup", idol_cost)
        print(f"[{session.addr}] Deducted {idol_cost} idols for speed-up")

    # --- Grab pending upgrade ---
    bu = char.get("buildingUpgrade", {})
    building_id = bu.get("buildingID")
    new_rank    = bu.get("rank")
    if not building_id or new_rank is None:
        print(f"[{session.addr}] [0xDC] no active building upgrade")
        save_characters(session.user_id, session.char_list)
        return

    # --- Cancel scheduler (if any) ---
    bu.pop("schedule_id", None)  # we don’t track IDs, just clean
    # (scheduled task will auto-skip if buildingID==0)

    # --- Apply upgrade immediately ---
    stats_dict = char.setdefault("magicForge", {}).setdefault("stats_by_building", {})
    stats_dict[str(building_id)] = new_rank

    # --- Clear pending upgrade ---
    char["buildingUpgrade"] = {
        "buildingID": 0,
        "rank": 0,
        "ReadyTime": 0,
        "done": False,
    }

    save_characters(session.user_id, session.char_list)

    # --- Mirror in session ---
    mem_char = next((c for c in session.char_list
                     if c.get("name") == session.current_character), None)
    if mem_char:
        mem_char["mammothIdols"] = char["mammothIdols"]
        mem_char.setdefault("magicForge", {})["stats_by_building"] = stats_dict.copy()
        mem_char["buildingUpgrade"] = char["buildingUpgrade"].copy()

    # --- Notify client (0xD8) ---
    try:
        bb = BitBuffer()
        bb.write_method_6(building_id, 5)   # class_9.const_129
        bb.write_method_6(new_rank, 5)      # class_9.const_28
        bb.write_method_15(True)            # complete flag
        payload = bb.to_bytes()
        session.conn.sendall(struct.pack(">HH", 0xD8, len(payload)) + payload)
        print(f"[{session.addr}] [0xDC] completed upgrade ID={building_id}, rank={new_rank}")
    except Exception as e:
        print(f"[{session.addr}] [0xDC] failed to send 0xD8: {e}")

def handle_cancel_building_upgrade(session, data):
    """
    Handle 0xDB: client canceled an ongoing building upgrade.
    Just clears buildingUpgrade; scheduled task will auto-skip.
    """
    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        return

    bu = char.get("buildingUpgrade", {})
    building_id = bu.get("buildingID", 0)

    # Reset upgrade state (cancel)
    char["buildingUpgrade"] = {
        "buildingID": 0,
        "rank": 0,
        "ReadyTime": 0,
        "done": False,
    }
    save_characters(session.user_id, session.char_list)

    print(f"[{session.addr}] [0xDB] building upgrade canceled for buildingID={building_id}")

    mem = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if mem:
        mem["buildingUpgrade"] = char["buildingUpgrade"].copy()

def handle_building_claim(session, data):
    """
    Handle 0xD9: client acknowledged a completed building upgrade.
    Usually sent after 0xD8 completion has been processed.
    """
    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] [0xD9] no character found")
        return

    bu = char.get("buildingUpgrade", {})
    building_id = bu.get("buildingID", 0)
    rank        = bu.get("rank", 0)

    # Clear upgrade state just in case it wasn’t cleared already
    char["buildingUpgrade"] = {
        "buildingID": 0,
        "rank": 0,
        "ReadyTime": 0,
        "done": False,
    }
    save_characters(session.user_id, session.char_list)

    # Mirror to in-memory session
    mem = next((c for c in session.char_list
                if c.get("name") == session.current_character), None)
    if mem:
        mem["buildingUpgrade"] = char["buildingUpgrade"].copy()

    print(f"[{session.addr}] [0xD9] building upgrade claim ack "
          f"(buildingID={building_id}, rank={rank})")