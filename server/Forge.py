import json
import math
import random
import struct
import time

from BitBuffer import BitBuffer
from Character import save_characters
from Commands import SAVE_PATH_TEMPLATE
from bitreader import BitReader
from constants import class_111, class_1_const_254, class_8, class_3, class_1, Game, class_64, \
    CHARM_DB, CONSUMABLE_BOOSTS, class_86
from globals import send_consumable_update, send_premium_purchase
from scheduler import scheduler, schedule_forge

"""
craftTalentPoints layout:
  [0] = Crafting time reduction
  [1] = Rare / Legendary chance
  [2] = Bonus material efficiency
  [3] = Material yield
  [4] = Craft XP gain speed
"""

def get_forge_level_from_xp(xp: int) -> int:
    for i, threshold in enumerate(class_86.FORGE_XP_THRESHOLDS[1:], start=1):
        if xp < threshold:
            return i
    return 50

def get_charm_size(primary_id: int) -> int:
    try:
        entry = CHARM_DB.get(int(primary_id))
        if not entry:
            return 1
        size = int(entry.get("CharmSize", 1))
        return max(1, min(10, size))
    except Exception as e:
        print(f"[Forge] get_charm_size error for id={primary_id}: {e}")
        return 1

def get_craft_time_bonus_percent(char: dict) -> float:
    base_bonus = 5.0          # default base reduction %
    per_point_bonus = 0.5     # each point in slot 0 adds faster time
    points = char.get("craftTalentPoints", [])
    if not points or not isinstance(points, list):
        return base_bonus

    # Use only the first element for forge speed
    time_points = points[0] if len(points) > 0 else 0
    total_bonus = base_bonus + (per_point_bonus * float(time_points))
    return max(0.0, min(total_bonus, 50.0))

def compute_forge_duration_seconds(char: dict, primary_id: int, forge_flags: dict) -> int:
    if primary_id == class_1.const_405:
        return class_64.const_1073 if forge_flags.get("var_2434") else Game.const_181
    if primary_id == class_1.const_459:
        return class_64.const_1166

    size = max(1, min(10, int(get_charm_size(primary_id))))
    craft_xp = int(char.get("craftXP", 0))
    if not craft_xp and size == 1:
        return Game.const_181

    base = class_8.const_1055[size - 1]
    bonus_percent = float(get_craft_time_bonus_percent(char))  # ← now 5.0
    result = math.ceil(base * (1 - bonus_percent * class_8.const_1299))
    return int(result)

def pick_secondary_rune(primary_id: int, consumable_flags: list[bool], char: dict | None = None) -> tuple[int, int]:
    # Base chance for any secondary
    chance_any = 25.0  # 25%

    # Find which consumables are active (IDs 1–4 are catalysts)
    cons_ids = [1, 2, 3, 4]
    total_rare_boost = 0
    total_legend_boost = 0

    for flag, cid in zip(consumable_flags, cons_ids):
        if not flag:
            continue
        boosts = CONSUMABLE_BOOSTS.get(cid)
        if boosts:
            total_rare_boost += boosts.get("RareBoost", 0)
            total_legend_boost += boosts.get("LegendaryBoost", 0)

    # Normalize these boost values to percentages
    chance_any += total_rare_boost * 100   # e.g., +10% if RareBoost=100
    chance_any += total_legend_boost * 100  # same scaling
    chance_any = min(chance_any, 75.0)

    # Add small craft XP bonus (5% max)
    craft_xp = int(char.get("craftXP", 0)) if char else 0
    chance_any += min(5.0, (craft_xp / 160000) * 5.0)

    has_secondary = (random.random() * 100) < chance_any
    if not has_secondary:
        return 0, 0

    # Rarity determination
    chance_legendary = 10.0 + (total_legend_boost * 0.1)  # boost from catalysts
    chance_legendary = min(chance_legendary, 60.0)

    var_8 = 2 if (random.random() * 100) < chance_legendary else 1
    secondary_id = random.randint(1, 9)
    return secondary_id, var_8

def start_forge_packet(session, data):
    br = BitReader(data[4:])
    primary = br.read_method_20(class_1.const_254)
    print(f"[{session.addr}] Forge start: primary charmID={primary}")

    materials_used = {}
    while br.read_method_15():
        mat_id = br.read_method_20(class_8.const_658)
        cnt = br.read_method_20(class_8.const_731)
        materials_used[mat_id] = materials_used.get(mat_id, 0) + cnt
    print(f"[{session.addr}] Forge materials: {materials_used}")

    consumable_flags = [br.read_method_15() for _ in range(4)]
    print(f"[{session.addr}] Forge consumables flags: {consumable_flags}")

    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] ERROR: character not found for forge start")
        return

    mats = char.setdefault("materials", [])
    for mat_id, used in materials_used.items():
        for entry in mats:
            if entry["materialID"] == mat_id:
                entry["count"] = max(0, int(entry.get("count", 0)) - used)
                break
        else:
            mats.append({"materialID": mat_id, "count": 0})

    cons_ids = [class_3.var_1415, class_3.var_2082, class_3.var_1374, class_3.var_1462]
    cons = char.setdefault("consumables", [])

    for flag, cid in zip(consumable_flags, cons_ids):
        if not flag:
            continue
        new_count = 0
        for entry in cons:
            if entry["consumableID"] == cid:
                entry["count"] = max(0, int(entry.get("count", 0)) - 1)
                new_count = entry["count"]
                break
        else:
            cons.append({"consumableID": cid, "count": 0})
        send_consumable_update(session.conn, cid, new_count)

    forge_flags = {"var_2434": (primary == class_1.const_405)}

    duration_sec = compute_forge_duration_seconds(char, primary, forge_flags)
    now_ts = int(time.time())
    end_ts = now_ts + duration_sec
    secondary, var_8 = pick_secondary_rune(primary, consumable_flags, char)

    mf = char.setdefault("magicForge", {})
    mf.update({
        "hasSession": True,
        "primary": primary,
        "secondary": secondary,
        "status": class_111.const_286,  # in progress
        "ReadyTime": end_ts,
        "var_8": var_8,
        "usedlist": 0,
        "var_2675": 0,
        "var_2316": 0,
        "var_2434": bool(forge_flags.get("var_2434", False)),
    })
    save_characters(session.user_id, session.char_list)
    schedule_forge(session.user_id, session.current_character, end_ts, primary, secondary)
    print(
        f"[{session.addr}] Forge started → ReadyTime={end_ts} "
        f"({duration_sec}s), primary={primary}, secondary={secondary}, var_8={var_8}"
    )

def forge_speed_up_packet(session, data):
    br = BitReader(data[4:])
    idols_to_spend = br.read_method_9()
    print(f"[{session.addr}] Forge speed-up: spend {idols_to_spend} idols")
    char = next((c for c in session.player_data.get("characters", [])
                 if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] Error: active character not found")
        return

    mf = char.setdefault("magicForge", {})
    if not mf.get("hasSession") or mf.get("status") != class_111.const_286:
        print(f"[{session.addr}] No active forge session to speed-up")
        return

    char["mammothIdols"] = max(0, int(char.get("mammothIdols", 0)) - idols_to_spend)
    send_premium_purchase(session, "Forge Speed-Up", idols_to_spend)

    if "schedule_id" in mf:
        try:
            scheduler.cancel(mf["schedule_id"])
            print(f"[{session.addr}] Canceled forge schedule id={mf['schedule_id']}")
        except Exception:
            pass
        mf.pop("schedule_id", None)

    mf.update({
        "status": class_111.const_264,   # completed
        "hasSession": True,              # still waiting to collect
        "ReadyTime": 0
    })

    # Ensure secondary exists (some forges might not have rolled yet)
    primary = mf.get("primary", 0)
    var_8   = mf.get("var_8", 0)
    secondary = mf.get("secondary", 0)
    usedlist = mf.get("usedlist", 0)
    if not var_8 or not secondary:
        sec, rarity = pick_secondary_rune(primary, [False] * 4, char)
        mf["secondary"], mf["var_8"] = sec, rarity
        secondary, var_8 = sec, rarity

    with open(SAVE_PATH_TEMPLATE.format(user_id=session.user_id), "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

    bb = BitBuffer()
    bb.write_method_6(primary, class_1_const_254)
    bb.write_method_91(int(mf.get("var_2675", 0)))
    bb.write_method_91(int(mf.get("var_2316", 0)))
    bb.write_method_6(var_8, class_64.const_499)
    if var_8:
        bb.write_method_6(secondary, class_64.const_218)
        bb.write_method_6(usedlist, class_111.const_432)

    pkt = struct.pack(">HH", 0xCD, len(bb.to_bytes())) + bb.to_bytes()
    session.conn.sendall(pkt)

#TODO: the xp after collecting the charm is not correct
def collect_forge_charm(session, data):
    char = next((c for c in session.player_data.get("characters", [])
                 if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] Character {session.current_character} not found")
        return

    mf = char.get("magicForge", {})
    if not (mf.get("hasSession") and mf.get("status") == class_111.const_264):
        print(f"[{session.addr}] No completed forge to collect")
        return

    primary   = int(mf.get("primary", 0))
    secondary = int(mf.get("secondary", 0))
    var_8     = int(mf.get("var_8", 0))
    charm_id  = (primary & 0x1FF) | ((secondary & 0x1F) << 9) | ((var_8 & 0x3) << 14)

    charms = char.setdefault("charms", [])
    for entry in charms:
        if entry.get("charmID") == charm_id:
            entry["count"] = entry.get("count", 0) + 1
            break
    else:
        charms.append({"charmID": charm_id, "count": 1})

    if primary not in (class_1.const_405, class_1.const_459):
        size = get_charm_size(primary)
        base_xp = class_8.const_1119[size - 1]

        bonus_points = 0
        ctp = char.get("craftTalentPoints", [0, 0, 0, 0, 0])
        if len(ctp) >= 5:
            bonus_points = ctp[4]
        xp_gain = math.ceil(base_xp * (1 + bonus_points * 0.01))

        old_xp = int(char.get("craftXP", 0))
        new_xp = old_xp + xp_gain
        new_level = get_forge_level_from_xp(new_xp)

        char["craftXP"] = new_xp
        char["craftLevel"] = new_level
        print(f"[{session.addr}] Forge XP +{xp_gain} (→ {new_xp}), Level={new_level}")

    mf.update({
        "hasSession": False,
        "primary": 0,
        "secondary": 0,
        "status": 0,
        "ReadyTime": 0,
        "var_8": 0,
        "usedlist": 0,
        "var_2675": 0,
        "var_2316": 0,
        "var_2434": False,
    })
    with open(SAVE_PATH_TEMPLATE.format(user_id=session.user_id), "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

def cancel_forge_packet(session, data):
    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c["name"] == session.current_character), None)
    if char is None:
        print(f"[{session.addr}] ERROR: character not found for cancel forge")
        return
    mf = char.setdefault("magicForge", {})
    mf["hasSession"] = False
    mf["status"]     = 0
    mf["ReadyTime"]   = 0
    mf["primary"]    = 0
    mf["secondary"]  = 0
    mf["var_8"]      = 0
    mf["usedlist"]   = 0
    mf["var_2675"]   = 0
    mf["var_2316"]   = 0
    mf["var_2434"]   = False
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

def use_forge_xp_consumable(session, data):
    payload = data[4:]
    br = BitReader(payload)
    cid = br.read_method_20(class_3.const_69)

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
    save_characters(session.user_id, session.char_list)
    send_consumable_update(session.conn, cid, new_count)

def allocate_talent_points(session, data):
    payload = data[4:]
    br = BitReader(payload)
    packed = br.read_method_9()

    points = [(packed >> (i * 4)) & 0xF for i in range(5)]
    chars = getattr(session, "char_list", [])
    current_name = getattr(session, "current_character", None)
    char = next((c for c in chars if c.get("name") == current_name), None)
    if not char:
        print(f"[{session.addr}] ERROR: character not found (current_character={current_name})")
        return

    char["craftTalentPoints"] = points
    save_characters(session.user_id, session.char_list)

def magic_forge_reroll(session, data):
    br = BitReader(data[4:])
    current_usedlist = br.read_method_20(class_111.const_432)
    print(f"[{session.addr}] Forge reroll request (usedlist={current_usedlist})")

    char = next((c for c in session.player_data.get("characters", [])
                 if c.get("name") == session.current_character), None)
    if not char:
        print(f"[{session.addr}] Character {session.current_character} not found")
        return

    mf = char.get("magicForge", {})
    if not (mf.get("hasSession") and mf.get("status") == class_111.const_264):
        print(f"[{session.addr}] No completed forge available for reroll")
        return

    primary = int(mf.get("primary", 0))
    var_8 = int(mf.get("var_8", 0))
    secondary = int(mf.get("secondary", 0))
    usedlist = int(mf.get("usedlist", 0))
    if usedlist >= class_111.const_1101:
        print(f"[{session.addr}] Reroll limit reached (usedlist={usedlist})")
        return

    cost = 20
    char["mammothIdols"] = max(0, int(char.get("mammothIdols", 0)) - cost)

    # Send currency update to client
    send_premium_purchase(session, "Forge Reroll", cost)

    # Increment usedlist
    usedlist += 1
    mf["usedlist"] = usedlist

    # Re-roll new secondary + rarity
    new_secondary, new_var8 = pick_secondary_rune(primary, [False] * 4, char)

    # Ensure rerolls always produce a valid secondary (client expects it)
    if not new_secondary or new_secondary <= 0:
        new_secondary = random.randint(1, 9)

    # Rare or Legendary tier must exist (1 or 2)
    if not new_var8 or new_var8 <= 0:
        new_var8 = random.choice([1, 2])

    mf["secondary"] = new_secondary
    mf["var_8"] = new_var8

    print(f"[{session.addr}] Forge rerolled → cost={cost} idols, new secondary={new_secondary}, var_8={new_var8}, usedlist={usedlist}")

    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

    bb = BitBuffer()
    bb.write_method_6(primary, class_1_const_254)
    bb.write_method_91(int(mf.get("var_2675", 0)))
    bb.write_method_91(int(mf.get("var_2316", 0)))
    bb.write_method_6(new_var8, class_64.const_499)
    if new_var8:
        bb.write_method_6(new_secondary, class_64.const_218)
        bb.write_method_6(usedlist, class_111.const_432)

    pkt = struct.pack(">HH", 0xCD, len(bb.to_bytes())) + bb.to_bytes()
    session.conn.sendall(pkt)
    print(f"[{session.addr}] Sent 0xCD forge reroll update")