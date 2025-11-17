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
    CHARM_DB, CONSUMABLE_BOOSTS, class_86, MATERIALS_DATA
from globals import send_consumable_update, send_premium_purchase
from scheduler import scheduler, schedule_forge

# Hints
"""

Magic Forge : 

"hasSession": true,          # (1 bit) True if the player currently has an active forge slot.
                             #   This controls whether the client reads the forge data block.

"primary": 90,               # (6 bits) ID of the primary charm being forged.

"secondary": 5,              # (5 bits) ID of the secondary bonus effect.
                             #   Only read when the forge status == 2 (completed)
                             #   and secondary_tier > 0.

"status": 1,                 # (1 bit) Forge state:
                             #   1 = In progress (timer running)
                             #   2 = Completed (ready to collect)

"ReadyTime": 1762825798,     # (uint32) Absolute UNIX timestamp (seconds) when the forge completes.
                             #   The client converts this to remaining milliseconds when status == 1.

"secondary_tier": 1,         # (2 bits) Rarity tier of the secondary effect:
                             #   0 = None, 1 = Rare (uses const_1278), 2 = Legendary (uses const_1155).

"usedlist": 2,               # (9 bits) Number of times the player has rerolled this forge's secondary bonus.
                             #   Max value 511 (class_111.const_1101). Sent only if secondary_tier > 0.

"forge_roll_a": 235,         # (16 bits) Randomized stat seed A. Used for small internal stat variations.

"forge_roll_b": 914,         # (16 bits) Randomized stat seed B. Used for secondary internal variations.

"is_extended_forge": false,  # (1 bit) True for special long-duration crafts (e.g., charmID 91 “Special Stone”).
                             #   This flag also toggles some client UI behaviors.

craftTalentPoints layout:
  [0] = Crafting time reduction
  [1] = Rare / Legendary chance
  [2] = Bonus material efficiency
  [3] = Material yield
  [4] = Craft XP gain speed
"""

#              Forge Function Helpers
#########################################################

def get_forge_level(mf: dict) -> int:
    stats = mf.get("stats_by_building", {})
    lvl = stats.get("2", 1)
    try:
        lvl = int(lvl)
    except (ValueError, TypeError):
        lvl = 1
    return max(1, min(lvl, 10))

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
        return class_64.const_1073 if forge_flags.get("is_extended_forge") else Game.const_181
    if primary_id == class_1.const_459:
        return class_64.const_1166
    size = max(1, min(10, int(get_charm_size(primary_id))))
    base = class_8.const_1055[size - 1]
    bonus_percent = float(get_craft_time_bonus_percent(char))  # ← now 5.0
    result = math.ceil(base * (1 - bonus_percent * class_8.const_1299))
    return int(result)

#TODO... the percentage chance is wrong in the server when using materials
def pick_secondary_rune(
    primary_id: int,
    consumable_flags: list[bool],
    char: dict | None = None,
    materials_used: list[int] | None = None,
) -> tuple[int, int]:
    base_chance_any = 0.0
    base_chance_legendary = 0.0

    # --- Catalysts ---
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

    base_chance_any += total_rare_boost
    base_chance_legendary += total_legend_boost

    craft_talents = char.get("craftTalentPoints", [0, 0, 0, 0, 0])
    craft_level = craft_talents[1]
    rare_bonus = craft_level * 0.9
    legend_bonus = craft_level * 0.4

    total_points = 0
    if materials_used:
        for mat_id in materials_used:
            mat = MATERIALS_DATA.get(mat_id)
            if not mat:
                continue
            rarity = mat.get("Rarity", "M")
            if rarity == "M":
                total_points += 1
            elif rarity == "R":
                total_points += 1.5
            elif rarity == "L":
                total_points += 2

        rare_bonus += total_points * 0.99
        legend_bonus += total_points * 0.44

    chance_any = base_chance_any + rare_bonus
    chance_legendary = base_chance_legendary + legend_bonus

    # Clamp to 100%
    chance_any = min(chance_any, 100.0)
    chance_legendary = min(chance_legendary, 100.0)

    #print(f"[Forge RNG] mats={materials_used} → pts={total_points}, "
    #      f"Anvil Points+{craft_level} → chance_any={chance_any:.1f}%, "
    #      f"chance_legendary={chance_legendary:.1f}%")

    has_secondary = (random.random() * 100) < chance_any
    if not has_secondary:
        return 0, 0

    var_8 = 2 if (random.random() * 100) < chance_legendary else 1
    secondary_id = random.randint(1, 9)
    return secondary_id, var_8

#             Forge Function Handlers
#########################################################

def handle_start_forge(session, data):
    br = BitReader(data[4:])
    primary = br.read_method_20(class_1.const_254)

    materials_used = {}
    while br.read_method_15():
        mat_id = br.read_method_20(class_8.const_658)
        cnt = br.read_method_20(class_8.const_731)
        materials_used[mat_id] = materials_used.get(mat_id, 0) + cnt
    #print(f"[{session.addr}] Forge materials: {materials_used}")

    consumable_flags = [br.read_method_15() for _ in range(4)]
    #print(f"[{session.addr}] Forge consumables flags: {consumable_flags}")

    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)

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

    forge_flags = {"is_extended_forge": (primary == class_1.const_405)}

    duration_sec = compute_forge_duration_seconds(char, primary, forge_flags)
    now_ts = int(time.time())
    end_ts = now_ts + duration_sec
    secondary, var_8 = pick_secondary_rune(
        primary,
        consumable_flags,
        char,
        list(materials_used.keys())  # <-- pass material IDs to the RNG
    )

    mf = char.setdefault("magicForge", {})
    mf.update({
        "hasSession": True,
        "primary": primary,
        "secondary": secondary,
        "status": class_111.const_286,  # in progress
        "ReadyTime": end_ts,
        "secondary_tier": var_8,
        "usedlist": 0,
        "forge_roll_a": 0,
        "forge_roll_b": 0,
        "is_extended_forge": bool(forge_flags.get("is_extended_forge", False)),
    })
    save_characters(session.user_id, session.char_list)
    schedule_forge(session.user_id, session.current_character, end_ts, primary, secondary)
    #print(
    #    f"[{session.addr}] Forge started → ReadyTime={end_ts} "
    #    f"({duration_sec}s), primary={primary}, secondary={secondary}, var_8={var_8}"
    #)

def handle_forge_speed_up_packet(session, data):
    br = BitReader(data[4:])
    idols_to_spend = br.read_method_9()
    char = next((c for c in session.player_data.get("characters", [])if c.get("name") == session.current_character), None)

    mf = char.setdefault("magicForge", {})
    if not mf.get("hasSession") or mf.get("status") != class_111.const_286:
        print(f"[{session.addr}] No active forge session to speed-up")
        return

    char["mammothIdols"] = max(0, int(char.get("mammothIdols", 0)) - idols_to_spend)
    send_premium_purchase(session, "Forge Speed-Up", idols_to_spend)
    if "schedule_id" in mf:
        try:
            scheduler.cancel(mf["schedule_id"])
        except Exception:
            pass
        mf.pop("schedule_id", None)

    mf.update({
        "status": class_111.const_264,   # completed
        "hasSession": True,              # waiting to collect
        "ReadyTime": 0,
        "forge_roll_a": random.randint(0, 65535),
        "forge_roll_b": random.randint(0, 65535),
    })

    primary   = mf.get("primary", 0)
    var_8     = mf.get("secondary_tier", 0)
    secondary = mf.get("secondary", 0)
    usedlist  = mf.get("usedlist", 0)

    with open(SAVE_PATH_TEMPLATE.format(user_id=session.user_id), "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

    bb = BitBuffer()
    bb.write_method_6(primary, class_1_const_254)
    bb.write_method_91(int(mf["forge_roll_a"]))
    bb.write_method_91(int(mf["forge_roll_b"]))
    bb.write_method_6(var_8, class_64.const_499)
    if var_8:
        bb.write_method_6(secondary, class_64.const_218)
        bb.write_method_6(usedlist, class_111.const_432)

    pkt = struct.pack(">HH", 0xCD, len(bb.to_bytes())) + bb.to_bytes()
    session.conn.sendall(pkt)

def handle_collect_forge_charm(session, data):
    char = next((c for c in session.player_data.get("characters", [])if c.get("name") == session.current_character), None)

    mf = char.get("magicForge", {})
    primary   = int(mf.get("primary", 0))
    secondary = int(mf.get("secondary", 0))
    var_8     = int(mf.get("secondary_tier", 0))
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
            bonus_points = ctp[4]  # Coals: craft XP gain speed
        xp_gain = math.ceil(base_xp * (1 + bonus_points * class_8.CRAFT_XP_MULTIPLIER))

        old_xp = int(char.get("craftXP", 0))
        new_xp = old_xp + xp_gain
        char["craftXP"] = new_xp

    mf.update({
        "hasSession": False,
        "primary": 0,
        "secondary": 0,
        "status": 0,
        "ReadyTime": 0,
        "secondary_tier": 0,
        "usedlist": 0,
        "forge_roll_a": 0,
        "forge_roll_b": 0,
        "is_extended_forge": False,
    })
    with open(SAVE_PATH_TEMPLATE.format(user_id=session.user_id), "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

def handle_cancel_forge(session, data):
    chars = session.player_data.get("characters", [])
    char = next((c for c in chars if c["name"] == session.current_character), None)

    mf = char.setdefault("magicForge", {})
    mf["hasSession"] = False
    mf["status"]     = 0
    mf["ReadyTime"]   = 0
    mf["primary"]    = 0
    mf["secondary"]  = 0
    mf["secondary_tier"] = 0
    mf["usedlist"]   = 0
    mf["forge_roll_a"]   = 0
    mf["forge_roll_b"]   = 0
    mf["is_extended_forge"]   = False
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

def handle_use_forge_xp_consumable(session, data):
    payload = data[4:]
    br = BitReader(payload)
    cid = br.read_method_20(class_3.const_69)

    chars = getattr(session, "char_list", [])
    current_name = getattr(session, "current_character", None)
    char = next((c for c in chars if c.get("name") == current_name), None)

    new_count = 0
    for entry in char.get("consumables", []):
        if entry.get("consumableID") == cid:
            entry["count"] = max(0, entry.get("count", 0) - 1)
            new_count = entry["count"]
            break
    cap = 159_948# going above this value, it will crash the server
    gain = 4000
    
    before = int(char.get("craftXP", 0))
    char["craftXP"] = min(before + gain, cap)
    save_characters(session.user_id, session.char_list)
    send_consumable_update(session.conn, cid, new_count)

def handle_allocate_magic_forge_artisan_skill_points(session, data):
    payload = data[4:]
    br = BitReader(payload)
    packed = br.read_method_9()
    points = [(packed >> (i * 4)) & 0xF for i in range(5)]
    chars = getattr(session, "char_list", [])
    current_name = getattr(session, "current_character", None)
    char = next((c for c in chars if c.get("name") == current_name), None)
    char["craftTalentPoints"] = points
    save_characters(session.user_id, session.char_list)

def pick_unused_property(client_usedlist: int) -> int:
    """Return a random property ID (1-9) that is NOT in usedlist."""
    available = [i for i in range(1, 10)
                 if not (client_usedlist & (1 << (i - 1)))]
    if not available:
        return None
    return random.choice(available)

def handle_magic_forge_reroll(session, data):
    br = BitReader(data[4:])
    client_usedlist = br.read_method_20(class_111.const_432)

    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)
    mf = char.setdefault("magicForge", {})
    primary = int(mf.get("primary", 0))

    #  Deduct idols
    forge_level = get_forge_level(mf)
    cost = class_8.FORGE_REROLL_COSTS[forge_level - 1]
    current_idols = int(char.get("mammothIdols", 0))
    char["mammothIdols"] = current_idols - cost
    send_premium_purchase(session, "Forge Reroll", cost)

    new_secondary = pick_unused_property(client_usedlist)
    if not new_secondary:
        print("[Forge] ERROR: No unused properties but usedlist < 511")
        return

    new_tier = random.choice([1, 2])

    # Update server state
    new_usedlist = client_usedlist | (1 << (new_secondary - 1))

    mf["secondary"] = new_secondary
    mf["secondary_tier"] = new_tier
    mf["usedlist"] = new_usedlist

    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(session.player_data, f, indent=2)

    bb = BitBuffer()
    bb.write_method_6(primary, class_1_const_254)
    bb.write_method_91(int(mf.get("forge_roll_a", 0)))
    bb.write_method_91(int(mf.get("forge_roll_b", 0)))
    bb.write_method_6(new_tier, class_64.const_499)
    bb.write_method_6(new_secondary, class_64.const_218)
    bb.write_method_6(new_usedlist, class_111.const_432)

    payload = bb.to_bytes()
    session.conn.sendall(struct.pack(">HH", 0xCD, len(payload)) + payload)