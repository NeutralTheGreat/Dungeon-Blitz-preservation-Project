import json
import struct

from BitBuffer import BitBuffer
from Character import save_characters
from Commands import SAVE_PATH_TEMPLATE
from bitreader import BitReader
from constants import class_111, class_1_const_254, class_8, class_3
from globals import send_consumable_update
from scheduler import scheduler, schedule_forge


def magic_forge_packet(session, data):
    payload = data[4:]
    br = BitReader(payload)
    idols_to_spend = br.read_method_9()
    print(f"[{session.addr}] Speed‑up request: spend {idols_to_spend} idols")

    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c.get("name") == session.current_character), None)
    if char is None:
        print(f"[{session.addr}] Character {session.current_character} not found")
        return

    mf        = char.setdefault("magicForge", {})
    available = char.get("mammothIdols", 0)

    # ONLY check hasSession (i.e. an upgrade in progress), not status==1
    if mf.get("hasSession") and available >= idols_to_spend:
        # 1) Deduct idols
        char["mammothIdols"] = available - idols_to_spend

        # 2) Cancel the scheduled completion, if any
        sched_id = mf.get("schedule_id")
        if sched_id is not None:
            try:
                scheduler.cancel(sched_id)
                print(f"[{session.addr}] Canceled scheduled forge completion (id={sched_id})")
            except Exception as e:
                print(f"[{session.addr}] Failed to cancel scheduler id={sched_id}: {e}")
        mf.pop("schedule_id", None)

        # 3) Mark forge as completed via speed‑up
        mf["status"]   = class_111.const_264  # completed via speed‑up
        mf["duration"] = 0
        mf["hasSession"] = False

        # 4) Persist save
        save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(session.player_data, f, indent=2)

        # 5) Build & send the 0xCD “forge update” response
        bb = BitBuffer()
        bb.write_method_6(mf.get("primary", 0), class_1_const_254)
        bb.write_method_91(mf.get("var_2675", 0))
        bb.write_method_91(mf.get("var_2316", 0))
        bb.write_method_11(0, 1)  # no secondary/usedlist

        resp_payload = bb.to_bytes()
        resp = struct.pack(">HH", 0xCD, len(resp_payload)) + resp_payload
        session.conn.sendall(resp)
        print(f"[{session.addr}] Sent 0xCD forge‑update (speed‑up applied)")

    else:
        print(f"[{session.addr}] Speed‑up denied: hasSession={mf.get('hasSession')}, idols={available}")

#TODO... for every collect the forge should gain level XP
def collect_forge_charm(session, data):
    """
    Handle 0xD0 "collect charm" from client:
    - Grant the player the charm they just forged (computed full ID)
    - Clear out the forge session
    - Persist save
    - Reply with an empty 0xD0 ack
    """
    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c.get("name") == session.current_character), None)
    if char is None:
        print(f"[{session.addr}] Character {session.current_character} not found")
        return

    mf = char.get("magicForge", {})
    if not mf.get("hasSession", False):
        print(f"[{session.addr}] No active forge session to collect")
        return

    # Compute full charm ID
    primary = mf.get("primary", 0)
    secondary = mf.get("secondary", 0)
    var_8 = mf.get("var_8", 0)
    charm_id = (primary & 0x1FF) | ((secondary & 0x1F) << 9) | ((var_8 & 0x3) << 14)

    if primary <= 0:
        print(f"[{session.addr}] Invalid primary ID: {primary}")
    else:
        charms = char.setdefault("charms", [])
        for entry in charms:
            if entry.get("charmID") == charm_id:
                entry["count"] = entry.get("count", 0) + 1
                break
        else:
            charms.append({"charmID": charm_id, "count": 1})
        print(f"[{session.addr}] Granted charmID={charm_id}. New charms: {char['charms']}")

    # Clear forge session
    mf.update({
        "hasSession": False,
        "primary": 0,
        "secondary": 0,
        "status": 0,
        "duration": 0,
        "var_8": 0,
        "usedlist": 0,
        "var_2675": 0,
        "var_2316": 0,
        "var_2434": False
    })

    # Save file
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)
    print(f"[{session.addr}] Forge session cleared and saved")

    # Reply with 0xD0 ACK
    resp = struct.pack(">HH", 0xD0, 0)
    session.conn.sendall(resp)
    print(f"[{session.addr}] Sent 0xD0 collect-ack")

#TODO... implement the proper system to calculate the runnes  for each craft and the timers
def start_forge_packet(session, data):
    """
    Handle 0xB1: client clicked Craft on the Magic Forge.
    Also deducts materials and consumables from the character’s save,
    updates the session.char_list, and persists the result.
    """
    payload = data[4:]
    br = BitReader(payload)

    # 1) Read primary gem ID
    primary = br.read_method_20(class_1_const_254)
    print(f"[{session.addr}] Forge start: primary gemID={primary}")

    # 2) Read materials list
    materials_used = {}
    while br.read_method_15():  # method_15(true)
        mat_id = br.read_method_20(class_8.const_658)
        count = br.read_method_20(class_8.const_731)
        materials_used[mat_id] = count
    print(f"[{session.addr}] Forge materials: {materials_used}")

    # 3) Read consumable flags (4 total)
    consumable_flags = [br.read_method_15() for _ in range(4)]
    print(f"[{session.addr}] Forge consumables flags: {consumable_flags}")

    # 4) Locate the character dict in session.char_list
    char = next((c for c in session.char_list
                 if c["name"] == session.current_character), None)
    if not char:
        print(f"[{session.addr}] ERROR: character not found for forge start")
        return

    # 5) Deduct materials
    mats = char.setdefault("materials", [])
    for mat_id, used in materials_used.items():
        for entry in mats:
            if entry["materialID"] == mat_id:
                entry["count"] = max(0, entry["count"] - used)
                break
        else:
            mats.append({"materialID": mat_id, "count": 0})

    # 6) Deduct consumables
    consumable_ids = [
        class_3.var_1415,
        class_3.var_2082,
        class_3.var_1374,
        class_3.var_1462
    ]
    cons = char.setdefault("consumables", [])
    for flag, cid in zip(consumable_flags, consumable_ids):
        if flag:
            for entry in cons:
                if entry["consumableID"] == cid:
                    entry["count"] = max(0, entry["count"] - 1)
                    break
            else:
                cons.append({"consumableID": cid, "count": 0})

    # 7) Decide if the result has a secondary buff
    import random, time
    has_secondary = random.random() < 0.25  # 25%
    secondary    = random.randint(1, 9) if has_secondary else 0
    var_8        = 1 if has_secondary else 0

    # 8) Start the forge session on the character
    mf = char.setdefault("magicForge", {})
    mf.update({
        "hasSession": True,
        "primary": primary,
        "secondary": secondary,
        "status": class_111.const_286,  # in-progress
        "duration": 60000,              # ms
        "_start_time": time.time(),     # timestamp
        "var_8": var_8,
        "usedlist": 0,
        "var_2675": 0,
        "var_2316": 0,
        "var_2434": True
    })

    # 9) Sync and persist initial in‑progress state
    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)
    print(f"[{session.addr}] Forge session started and saved")

    # 10) Schedule completion callback
    now = int(time.time())
    # duration is in ms
    run_at = now + (mf["duration"] // 1000)
    schedule_forge(session.user_id,
                   session.current_character,
                   run_at,
                   primary,
                   secondary)
    print(f"[{session.addr}] Forge completion scheduled at {run_at}")

def cancel_forge_packet(session, data):
    """
    Handle 0xE1: client clicked Cancel on the Magic Forge.
    Clears the session so the UI resets.
    """
    print(f"[{session.addr}] Cancel‑forge request received")

    # 1) Find the character in the save
    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c["name"] == session.current_character), None)
    if char is None:
        print(f"[{session.addr}] ERROR: character not found for cancel forge")
        return

    # 2) Clear the forge session (no gem, no secondary, no timer)
    mf = char.setdefault("magicForge", {})
    mf["hasSession"] = False
    mf["status"]     = 0
    mf["duration"]   = 0
    mf["primary"]    = 0
    mf["secondary"]  = 0
    mf["var_8"]      = 0
    mf["usedlist"]   = 0
    mf["var_2675"]   = 0
    mf["var_2316"]   = 0
    mf["var_2434"]   = False

    # 3) Persist the change
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)
    print(f"[{session.addr}] Forge session canceled and save updated")

def use_forge_xp_consumable(session, data):
    payload = data[4:]
    br = BitReader(payload)
    cid = br.read_method_20(class_3.const_69)
    print(f"[{session.addr}] ForgeXP consumable used: cid={cid}")

    chars = getattr(session, "char_list", [])
    current_name = getattr(session, "current_character", None)
    char = next((c for c in chars if c.get("name") == current_name), None)
    if not char:
        print(f"[{session.addr}] ERROR: character not found (current_character={current_name})")
        return

    new_count = 0
    for entry in char.get("consumables", []):
        if entry.get("consumableID") == cid:
            entry["count"] = max(0, entry.get("count", 0) - 1)
            new_count = entry["count"]
            break
    cap = 159_948
    gain = 4000
    
    before = int(char.get("craftXP", 0))
    char["craftXP"] = min(before + gain, cap)
    print(f"[{session.addr}] ForgeXP +{gain} -> {char['craftXP']} (cap {cap})")
    save_characters(session.user_id, session.char_list)
    send_consumable_update(session.conn, cid, new_count)

def allocate_talent_points(session, data):
    payload = data[4:]
    br = BitReader(payload)
    packed = br.read_method_9()

    points = [(packed >> (i * 4)) & 0xF for i in range(5)]
    print(f"[{session.addr}] Craft talent allocation: {points}")

    # find active character from session.char_list
    chars = getattr(session, "char_list", [])
    current_name = getattr(session, "current_character", None)
    char = next((c for c in chars if c.get("name") == current_name), None)
    if not char:
        print(f"[{session.addr}] ERROR: character not found (current_character={current_name})")
        return

    char["craftTalentPoints"] = points
    save_characters(session.user_id, session.char_list)
    print(f"[{session.addr}] Saved craftTalentPoints for {char['name']}: {points}")
