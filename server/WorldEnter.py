from typing import Dict

from BitBuffer import BitBuffer
import struct
import time

from Forge import resolve_magic_forge_state
from constants import GearType, CLASS_NAME_TO_ID, class_64, NEWS_EVENTS, SLOT_BIT_WIDTHS, class_119, class_111, class_9, class_66, MASTERCLASS_TO_BUILDING, class_21, Game, Mission, Entity, class_7, class_16, class_118, class_1, class_10
from globals import all_sessions
from missions import get_total_mission_defs, get_mission_def
from socials import find_online_session, find_char_data_from_server_memory, get_live_friend_info

CLASS_BUILD_ORDER = {
    "paladin": [2, 12, 3, 4, 5, 1, 13],
    "mage":    [2, 12, 6, 7, 8, 1, 13],
    "rogue":   [2, 12, 9, 10,11, 1, 13],
}
def Player_Data_Packet(char: dict,
                       event_index: int = 5,
                       transfer_token: int = 0,
                       hp_scaling: int = 0,  #  increases the total HP for all entities in that level => game.const_790 = [1, 1.7, 2.4, 3.1] 4 values in total from 0 to 3
                                             #  this likely was meant to go up by 1 for every party member
                       bonus_levels: int = 0,  # this is to scale the players Level on dungeons if the player joins a friends dungeon who is higher level or lower level
                       target_level: str = None,
                       new_x: int = None,
                       new_y: int = None,
                       new_has_coord: bool = True,
                       send_extended: bool = False) -> bytes:
    
    now = int(time.time())

    def is_in_progress(ready_ts: int) -> bool:
        return ready_ts > now

    buf = BitBuffer()

    # ──────────────(Preamble)──────────────
    buf.write_method_4(transfer_token)
    current_game_time = int(time.time())
    buf.write_method_4(current_game_time)
    hp_scaling = max(0, min(hp_scaling, 3)) # Clamp to 0–3 (2-bit range)
    buf.write_method_6(hp_scaling, Game.const_813)
    bonus_levels = max(0, min(bonus_levels, 0xFFFFFFFF))
    buf.write_method_4(bonus_levels)

    # ──────────────(Customization)──────────────
    buf.write_method_13(char.get("name", "") or "")
    buf.write_method_11(1, 1)  # hasCustomization
    buf.write_method_13(char.get("class", "") or "")
    buf.write_method_13(char.get("gender", "") or "")
    buf.write_method_13(char.get("headSet", "") or "")
    buf.write_method_13(char.get("hairSet", "") or "")
    buf.write_method_13(char.get("mouthSet", "") or "")
    buf.write_method_13(char.get("faceSet", "") or "")
    buf.write_method_11(char.get("hairColor", 0), 24)
    buf.write_method_11(char.get("skinColor", 0), 24)
    buf.write_method_11(char.get("shirtColor", 0), 24)
    buf.write_method_11(char.get("pantColor", 0), 24)

    # ──────────────(Gear Slots)──────────────
    gear_list = char.get("equippedGears", [])
    # Ensure we always write exactly 6 gear slots
    for slot_idx in range(6):
        gear = gear_list[slot_idx] if slot_idx < len(gear_list) else {}
        gear_id = gear.get("gearID", 0) if isinstance(gear, dict) else 0
        
        if gear_id:
            rune1, rune2, rune3 = gear.get("runes", [0, 0, 0])
            color1, color2 = gear.get("colors", [0, 0])
            buf.write_method_11(1, 1)  # presence bit
            buf.write_method_11(gear_id, 11)
            buf.write_method_11(0, 2)
            buf.write_method_11(rune1, 16)
            buf.write_method_11(rune2, 16)
            buf.write_method_11(rune3, 16)
            buf.write_method_11(color1, 8)
            buf.write_method_11(color2, 8)
        else:
            buf.write_method_11(0, 1)  # no item in this slot

    # ──────────────(Numeric fields)──────────────
    char_level = char.get("level", 1) or 1
    buf.write_method_6(char_level, Entity.MAX_CHAR_LEVEL_BITS)
    buf.write_method_4(int(char.get("xp", 0)))
    buf.write_method_4(int(char.get("gold", 0)))
    buf.write_method_4(int(char.get("craftXP", 0)))
    buf.write_method_4(int(char.get("DragonOre", 0)))
    buf.write_method_4(int(char.get("mammothIdols", 0)))



    buf.write_method_11(int(char.get("showHigher", False)), 1)# Unknown

    # ──────────────(Quest-tracker)──────────────
    # updates the current percentage of the current Dungeon this was likely used when the player join a in progress dungeon
    quest_val = char.get("questTrackerState", 0)
    if quest_val is not None:
        buf.write_method_11(1, 1)
        buf.write_method_4(quest_val)
    else:
        buf.write_method_11(0, 1)

    # ──────────────(Position‐presence)──────────────
    if new_has_coord and target_level and new_x is not None and new_y is not None:
        buf.write_method_11(1, 1)
        buf.write_method_45(new_x)
        buf.write_method_45(new_y)
    else:
        buf.write_method_11(0, 1)

    # ──────────────(Extended‐data‐presence)──────────────
    # only send extended data once when the player loads in the game world
    # do not send the extended data when the player is transferring to another level
    # because the game saves it in memory sending a second time will cause inventory items to duplicate
    if send_extended:
        buf.write_method_6(1, 1)

    # ──────────────(Extended data block)──────────────


        # ──────────────(Inventory Gears)──────────────
        inventory_gears = char.get("inventoryGears", [])
        buf.write_method_6(len(inventory_gears), GearType.GEARTYPE_BITSTOSEND)
        for gear in inventory_gears:
            gear_id = gear.get("gearID", 0)
            tier = gear.get("tier", 0)
            runes = gear.get("runes", [0, 0, 0])
            colors = gear.get("colors", [0, 0])

            buf.write_method_11(gear_id, 11)
            buf.write_method_11(tier, GearType.const_176)

            has_modifiers = any(rune != 0 for rune in runes) or any(color != 0 for color in colors)
            buf.write_method_11(1 if has_modifiers else 0, 1)

            if has_modifiers:
                for i in range(3):
                    rune = runes[i]
                    rune_present = rune != 0
                    buf.write_method_11(1 if rune_present else 0, 1)
                    if rune_present:
                        buf.write_method_11(rune, 16)  # Rune ID (16 bits)
                for i in range(2):
                    color = colors[i]
                    color_present = color != 0
                    buf.write_method_11(1 if color_present else 0, 1)
                    if color_present:
                        buf.write_method_11(color, 8)


        # ──────────────(Gear Sets)──────────────
        gear_sets = char.get("gearSets", [])
        buf.write_method_6(len(gear_sets), GearType.const_348)
        for gs in gear_sets:
            buf.write_method_13(gs.get("name", ""))
            slots = gs.get("slots", [])

            # index 0 is not used
            if len(slots) < 7:
                slots = slots + [0] * (7 - len(slots))
            elif len(slots) > 7:
                slots = slots[:7]

            buf.write_method_11(slots[1], GearType.GEARTYPE_BITSTOSEND)  # armor
            buf.write_method_11(slots[2], GearType.GEARTYPE_BITSTOSEND)  # gloves
            buf.write_method_11(slots[3], GearType.GEARTYPE_BITSTOSEND)  # boots
            buf.write_method_11(slots[4], GearType.GEARTYPE_BITSTOSEND)  # hat
            buf.write_method_11(slots[5], GearType.GEARTYPE_BITSTOSEND)  # sword
            buf.write_method_11(slots[6], GearType.GEARTYPE_BITSTOSEND)  # shield

        # ──────────────(Keybinds)──────────────
        buf.write_method_11(0, 1)  # no keybinds

        # ──────────────(Mounts)──────────────
        mounts = char.get("mounts", [])
        buf.write_method_4(len(mounts))
        for mount_id in mounts:
            buf.write_method_4(mount_id)

        # ──────────────(Pets)──────────────
        pets = char.get("pets", [])
        buf.write_method_4(len(pets))
        for pet in pets:
            type_id = pet.get("typeID", 0)
            iteration = pet.get("level", 0)
            attr1 = pet.get("xp", 0)
            attr2 = pet.get("special_id", 0)
            type_id = max(0, min(type_id, 127))
            iteration = max(0, min(iteration, 63))
            buf.write_method_6(type_id, 7)
            buf.write_method_6(iteration, 6)
            buf.write_method_4(attr1)
            buf.write_method_4(attr2)


        # ──────────────(Charms)──────────────
        charms = char.get("charms", [])
        for charm in charms:
            charm_id = charm.get("charmID", 0)
            count = charm.get("count", 1)
            buf.write_method_11(1, 1)
            buf.write_method_11(charm_id, class_64.const_101)
            if count != 1:
                buf.write_method_11(1, 1)
                buf.write_method_4(count)
            else:
                buf.write_method_11(0, 1)
        buf.write_method_11(0, 1)

        # ──────────────(Materials)──────────────
        materials = char.get("materials", [])
        for mat in materials:
            mat_id = mat.get("materialID", 0)
            count = mat.get("count", 1)
            buf.write_method_11(1, 1)
            buf.write_method_4(mat_id)
            if count != 1:
                buf.write_method_11(1, 1)
                buf.write_method_4(count)
            else:
                buf.write_method_11(0, 1)
        buf.write_method_11(0, 1)


        # ──────────────(Lockboxes)──────────────
        lockboxes = char.get("lockboxes", [])
        for box in lockboxes:
            box_id = box.get("lockboxID", 0)
            count = box.get("count", 1)
            buf.write_method_11(1, 1)
            buf.write_method_4(box_id)
            buf.write_method_4(count)
        buf.write_method_11(0, 1)

        # ──────────────(lockboxKeys) and (royalSigils)──────────────
        buf.write_method_4(int(char.get("DragonKeys", 0)))
        buf.write_method_4(int(char.get("SilverSigils", 0)))

        alert_state = char.get("alertState", 0)
        buf.write_method_6(alert_state, Game.const_646)

        # ──────────────(dyes)──────────────
        owned_dyes = set(char.get("OwnedDyes", []))

        for dye_id in range(1, class_21.const_763 + 1):
            has_dye = 1 if dye_id in owned_dyes else 0
            buf.write_method_11(has_dye, 1)

        # ──────────────(consumables)──────────────
        consumables = char.get("consumables", [])
        for item in consumables:
            cid = item.get("consumableID", 0)
            count = item.get("count", 1)
            buf.write_method_11(1, 1)
            buf.write_method_4(cid)
            buf.write_method_4(count)
        buf.write_method_11(0, 1)

        # ──────────────(Missions)──────────────
        missions_state: Dict[str, dict] = char.get("missions", {}) or {}

        total_defs = get_total_mission_defs()
        buf.write_method_4(total_defs)

        for mid in range(1, total_defs + 1):
            mdef = get_mission_def(mid)
            mstate = missions_state.get(str(mid))
            if mdef["Tier"]:
                # Achievement/special → exactly one bit: 1 means create Mission(id, READY, 0)
                ready = (mstate is not None) and (mstate.get("state") == Mission.const_72)
                buf.write_method_11(1 if ready else 0, 1)
                continue
            # Regular missions
            has_entry = mstate is not None
            buf.write_method_11(1 if has_entry else 0, 1)  # presence bit
            if not has_entry:
                continue

            state = mstate.get("state", Mission.const_213)

            # Second bit: ready vs. not-ready
            is_ready = (state == Mission.const_72)
            buf.write_method_11(1 if is_ready else 0, 1)

            if not is_ready:
                # In-progress path: if CompleteCount > 1, send currCount
                if mdef["highscore"] > 1:
                    buf.write_method_4(int(mstate.get("currCount", 0)))
            else:
                # Third bit: 1 → READY (turn-in), 0 → CLAIMED (already collected)
                # (client uses this to choose const_72 vs const_58)
                is_turnin = 1 if state == Mission.const_72 else 0
                buf.write_method_11(is_turnin, 1)

                # Timed/Ranked extras — only if the *client’s* def has Time set (we mirror that here)
                if mdef["Time"]:
                    # Tier 1 to 7 is bronze tier 8 to 9 is silver tier 10 is gold tier
                    buf.write_method_11(int(mstate.get("Tier", 0)), class_119.const_228)
                    buf.write_method_4(int(mstate.get("highscore", 0)))
                    buf.write_method_4(int(mstate.get("Time", 0)))

        # ──────────────(Friends)──────────────
        friends = char.get("friends", [])

        #  Friend count
        buf.write_method_4(len(friends))

        #  Friend entries
        for entry in friends:
            fname = entry["name"]
            is_request = entry.get("isRequest", False)

            friend_sess = find_online_session(all_sessions, fname)
            friend_char = find_char_data_from_server_memory(fname)

            info = get_live_friend_info(fname, friend_sess, friend_char)
            online = info["isOnline"]
            class_name = info["className"]
            level = info["level"]

            #  Write protocol data
            buf.write_method_13(fname)  # name
            buf.write_method_11(1 if is_request else 0, 1)  # isRequest
            buf.write_method_11(1 if online else 0, 1)  # isOnline

            if online:
                buf.write_method_11(0, 1)  # hasCustomName = false
                class_id = CLASS_NAME_TO_ID.get(class_name, 0)
                buf.write_method_11(class_id, Entity.const_244)  # class
                buf.write_method_11(level, Entity.MAX_CHAR_LEVEL_BITS)  # level


        # ──────────────(Abilities)──────────────
        learned_abilities = char.get("learnedAbilities", [])
        buf.write_method_6(len(learned_abilities), class_10.const_83)
        for ability in learned_abilities:
            ability_id = ability.get("abilityID", 0)
            rank = ability.get("rank", 0)
            buf.write_method_6(ability_id, class_10.const_83)
            buf.write_method_6(rank, class_10.const_665)

        # ──────────────(activeAbilities)──────────────
        active_slots = char.get("activeAbilities", [0, 0, 0])
        while len(active_slots) < 3:
            active_slots.append(0)
        for slot_id in active_slots[:3]:
            buf.write_method_6(slot_id, class_10.const_83)

        # ──────────────(craftTalentPoints)──────────────
        craft_talent_points = char.get("craftTalentPoints", [0, 0, 0, 0, 0])  # List of 5 values, each 0-15
        packed_value = 0
        for i in range(5):
            packed_value |= (craft_talent_points[i] & 0xF) << (i * 4)
        buf.write_method_4(packed_value)

        # ──────────────(talentPoints)──────────────
        tp_dict = char.get("talentPoints", {})
        for class_idx in (1, 2, 3):
            val = tp_dict.get(str(class_idx), 0)
            buf.write_method_6(val, 6)

        # ──────────────(magicForge)──────────────
        mf = char.get("magicForge", {})

        stats_dict = mf.get("stats_by_building", {})
        has_stats = bool(stats_dict)
        buf.write_method_11(1 if has_stats else 0, 1)

        if has_stats:
            cls = char.get("class", "").lower()
            seq = CLASS_BUILD_ORDER.get(cls, CLASS_BUILD_ORDER["paladin"])
            for bid in seq:
                val = stats_dict.get(str(bid), 0)
                buf.write_method_6(val, class_9.const_28)

        forge = resolve_magic_forge_state(mf, now)

        buf.write_method_11(1 if forge["has_session"] else 0, 1)

        if forge["has_session"]:
            primary = mf.get("primary", 0)
            buf.write_method_6(primary, class_1.const_254)

            if forge["in_progress"]:
                buf.write_method_11(1, 1)  # crafting
                buf.write_method_4(forge["ready_time"])  # end timestamp
            else:
                buf.write_method_11(0, 1)  # finished

                tier = mf.get("secondary_tier", 0)
                buf.write_method_6(tier, class_64.const_499)

                if tier > 0:
                    buf.write_method_6(mf.get("secondary", 0), class_64.const_218)
                    buf.write_method_6(mf.get("usedlist", 0), class_111.const_432)

            # always sent when a session exists
            buf.write_method_91(min(mf.get("forge_roll_a", 0), 65535))
            buf.write_method_91(min(mf.get("forge_roll_b", 0), 65535))

        # Extended forge flag
        buf.write_method_11(1 if mf.get("is_extended_forge", False) else 0, 1)

        # ──────────────(Skill Research)──────────────
        research = char.get("SkillResearch")
        if research:
            buf.write_method_11(1, 1)
            buf.write_method_6(int(research["abilityID"]), class_10.const_83)
            end_sec = int(research.get("ReadyTime", 0))
            if end_sec and end_sec <= now:
                buf.write_method_4(0)
            else:
                buf.write_method_4(end_sec)
        else:
            buf.write_method_11(0, 1)

        # ──────────────(buildingResearch)──────────────
        bu = char.get("buildingUpgrade", {})
        ready_ts = int(bu.get("ReadyTime", 0))
        has_building_upgrade = (isinstance(bu, dict) and int(bu.get("buildingID", 0)) != 0 and is_in_progress(ready_ts))
        buf.write_method_11(1 if has_building_upgrade else 0, 1)
        if has_building_upgrade:
            buf.write_method_6(int(bu["buildingID"]), class_9.const_129)
            buf.write_method_4(ready_ts)

        # ──────────────(towerResearch)──────────────
        tr = char.get("talentResearch", {})
        ready_ts = int(tr.get("ReadyTime", 0))
        has_tr = (isinstance(tr, dict) and ready_ts > 0 and is_in_progress(ready_ts))
        buf.write_method_11(1 if has_tr else 0, 1)
        if has_tr:
            buf.write_method_6(int(tr.get("classIndex", 0)), class_66.const_571)
            buf.write_method_4(ready_ts)

        # ──────────────(EggHachery)──────────────
        egg_data = char.get("EggHachery", {})

        if egg_data and egg_data.get("EggID", 0) != 0:
            egg_id = int(egg_data.get("EggID", 0))
            ready_time = int(egg_data.get("ReadyTime", 0))
            now = int(time.time())

            buf.write_method_11(1, 1)  # EggHachery exists
            buf.write_method_6(egg_id, class_16.const_167)

            # If hatch time has passed, send 0 so client moves to "Ready to collect"
            if ready_time != 0 and ready_time <= now:
                buf.write_method_4(0)
            else:
                buf.write_method_4(ready_time)
        else:
            buf.write_method_11(0, 1)

        # ──────────────(Owned Eggs)──────────────
        MAX_SLOTS = class_16.const_1290

        eggs = char.get("OwnedEggsID", [])
        trimmed = eggs[:MAX_SLOTS]
        padded = trimmed + [0] * (MAX_SLOTS - len(trimmed))

        buf.write_method_6(MAX_SLOTS, class_16.const_167)
        for eid in padded:
            buf.write_method_6(eid, class_16.const_167)

        # ──────────────(Active Egg Count)──────────────
        activeEggCount = char.get("activeEggCount", 0)
        buf.write_method_4(activeEggCount)

        # ──────────────(Resting pets)──────────────
        rest = char.get("restingPets", [])[:3]

        for i in range(3):
            if i < len(rest):
                r = rest[i]
                buf.write_method_11(1, 1)
                buf.write_method_6(r["typeID"], class_7.const_19)
                buf.write_method_4(r["special_id"])
            else:
                buf.write_method_11(0, 1)

        # ──────────────(Training pets)──────────────
        tp_list = char.get("trainingPet", [])
        if tp_list:
            tp = tp_list[0]
            type_id = tp["typeID"]
            special_id = tp["special_id"]
            ready_ts = int(tp.get("trainingTime", 0))
            now = int(time.time())

            buf.write_method_11(1, 1)  # training exists
            buf.write_method_6(type_id, class_7.const_19)
            buf.write_method_4(special_id)

            if ready_ts <= now:
                buf.write_method_4(0)# training complete
            else:
                buf.write_method_4(ready_ts)
        else:
            buf.write_method_11(0, 1)

        # ──────────────(Event News)──────────────
        icon, url, body, tooltip, start_ts = NEWS_EVENTS.get(
            event_index,
                ["", "", "", "", 0]
        )

        buf.write_method_13(icon)  # a_NewsGoldIcon,
        buf.write_method_13(url)  # e.g. "http://www.dungeonblitz.com/"
        buf.write_method_13(body)  # "Double Gold Event"
        buf.write_method_13(tooltip)  # "While this event is in place ..."
        buf.write_method_4(start_ts)  # Epoch timestamp
    # This is where the extended data branch stops
    else:
        buf.write_method_6(0, 1)

    # ──────────────(MasterClass)──────────────
    selected = int(char.get("MasterClass", 0) or 0)
    buf.write_method_6(selected, Game.const_209)

    if selected > 0:
        buf.write_method_11(1, 1)
        talent_tree = char.get("TalentTree", {}).get(str(selected), {"nodes": [None] * class_118.NUM_TALENT_SLOTS})
        nodes = talent_tree.get("nodes", [None] * class_118.NUM_TALENT_SLOTS)
        for i in range(class_118.NUM_TALENT_SLOTS):
            node = nodes[i] or {"filled": False, "points": 0, "nodeID": i + 1}
            if node.get("filled", False):
                buf.write_method_11(1, 1)
                node_id = node.get("nodeID", i + 1)
                buf.write_method_6(node_id, class_118.const_127)
                bits = SLOT_BIT_WIDTHS[i]
                buf.write_method_6(node["points"] - 1, bits)
            else:
                buf.write_method_11(0, 1)
    else:
        buf.write_method_11(0, 1)

    # ──────────────(Equipped Gears)──────────────
    equip = char.get("equippedGears", [])
    for slot_id in range(1, 7):  # Slots 1 to 6
        gear = equip[slot_id - 1] if slot_id - 1 < len(equip) else {}
        gear_id = gear.get("gearID", 0)
        if gear_id:
            buf.write_method_11(1, 1)
            buf.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)
        else:
            buf.write_method_11(0, 1)

    # ──────────────(Equipped Mount)──────────────
    equipped = char.get("equippedMount", 0)
    buf.write_method_4(equipped)

    # ──────────────(activePet)──────────────
    active = char.get("activePet", {})
    pet_type_id = active.get("typeID", 0)
    pet_iter_id = active.get("special_id", 0)
    buf.write_method_4(pet_type_id)  # typeID
    buf.write_method_4(pet_iter_id)  # unique pet id

    # ──────────────(activeConsumableID and queuedConsumableID)──────────────
    active_consumable_id = char.get("activeConsumableID", 0)
    queued_consumable_id = char.get("queuedConsumableID", 0)
    buf.write_method_4(active_consumable_id)
    buf.write_method_4(queued_consumable_id)

    # ──────────────(Guild‐panel data)──────────────
    guild = char.get("guild", None)
    in_guild = guild is not None
    buf.write_method_11(1 if in_guild else 0, 1)

    if in_guild:
       buf.write_method_13(guild["name"])
       buf.write_method_6(guild.get("rank", 0), 3)  # your own rank in guild

       members = guild.get("onlineMembers", [])
       buf.write_method_4(len(members))

       for m in members:
           buf.write_method_13(m["name"])  # name
           buf.write_method_6(m["classID"],
                              Entity.const_244)  # class → client maps via Entity.method_244()
           buf.write_method_6(m["level"], Entity.MAX_CHAR_LEVEL_BITS)
           buf.write_method_6(m.get("rank", 0), Entity.const_172)  # rank, not status

   # Level updates
    level_updates = char.get("completed_levels",[])
    buf.write_method_4(len(level_updates))
    for update in level_updates:
       composite = f"{update['id']}^{update['internal']}^{update['variant']}"
       buf.write_method_13(composite)
       buf.write_method_13(update["state"])

   # Room updates
    room_updates = char.get("updated_rooms", [])
    buf.write_method_4(len(room_updates))
    for update in room_updates:
       buf.write_method_4(update["id"])
       buf.write_method_13(update["action"])
       buf.write_method_13(update["state"])

    payload = buf.to_bytes()
    return struct.pack(">HH", 0x10, len(payload)) + payload

def send_building_update(session, char):
    mf_stats = char.get("magicForge", {}).get("stats_by_building", {})

    def _stat(bid):
        return int(mf_stats.get(str(bid), mf_stats.get(bid, 0) or 0))

    master_class_id = int(char.get("MasterClass", 0))
    tower_building_id = MASTERCLASS_TO_BUILDING.get(master_class_id, 3)

    # First building: current tower building type & its level
    first_building_id = tower_building_id
    first_building_level = _stat(tower_building_id)

    # Second building: maybe same as first but with target upgrade level
    second_building_id = tower_building_id
    second_building_level = first_building_level

    scaffolding_id = int(char.get("buildingUpgrade", {}).get("buildingID", 0) or 0)

    buf = BitBuffer()
    buf.write_method_6(first_building_id, class_9.const_129)
    buf.write_method_6(first_building_level, class_9.const_28)
    buf.write_method_6(second_building_id, class_9.const_129)
    buf.write_method_6(second_building_level, class_9.const_28)
    buf.write_method_6(scaffolding_id, class_9.const_129)

    pkt = struct.pack(">HH", 0xDA, len(buf.to_bytes())) + buf.to_bytes()
    session.conn.sendall(pkt)

def build_enter_world_packet(
    transfer_token: int,
    old_level_id: int,
    old_swf: str,
    has_old_coord: bool,
    old_x: int,
    old_y: int,
    host: str,
    port: int,
    new_level_swf: str,
    new_map_lvl: int,
    new_base_lvl: int,
    new_internal: str,
    new_moment: str,
    new_alter: str,
    new_is_dungeon: bool,
    new_has_coord: bool = False,
    new_x: int = 0,
    new_y: int = 0,
    char: dict = None,
) -> bytes:
    buf = BitBuffer()

    # 1) transferToken (_loc4_)
    buf.write_method_4(transfer_token)

    # 2) oldLevelId (_loc5_)
    buf.write_method_4(old_level_id)

    # 3) old SWF path (_loc6_)
    buf.write_method_13(old_swf)

    # 4) old coords? + values (_loc8_, _loc2_, _loc3_)
    buf.write_method_11(1 if has_old_coord else 0, 1)
    if has_old_coord:
        buf.write_method_4(old_x)
        buf.write_method_4(old_y)

    # 5) host (_loc9_)
    buf.write_method_13(host)

    # 6) port (_loc10_)
    buf.write_method_4(port)

    # 7) new SWF path (_loc11_)
    buf.write_method_13(new_level_swf)

    # 8) new_map_lvl, new_base_lvl (_loc12_, _loc13_, 6 bits each)
    buf.write_method_6(new_map_lvl, Entity.MAX_CHAR_LEVEL_BITS)
    buf.write_method_6(new_base_lvl, Entity.MAX_CHAR_LEVEL_BITS)

    # 9) new strings (_loc14_, _loc15_, _loc16_)
    buf.write_method_13(new_internal)
    buf.write_method_13(new_moment)
    buf.write_method_13(new_alter)

    # 10) new_is_dungeonanced flag (_loc17_)
    buf.write_method_11(1 if new_is_dungeon else 0, 1)

    # 11) spawn-point flag (_loc18_) + coords (_loc20_, _loc21_)
    buf.write_method_11(1 if new_has_coord else 0, 1)
    if new_has_coord:
        buf.write_method_45(new_x)
        buf.write_method_45(new_y)

    # --- SPECIAL CASE: only send building data when player loads/visits "CraftTown" ---
    # determine if we are entering CraftTown
    _is_crafttown = False
    if new_level_swf and "crafttown" in new_level_swf.lower():
        _is_crafttown = True
    if new_internal and "crafttown" in new_internal.lower():
        _is_crafttown = True

    # 12) Extended data presence (_loc19_) -> only set when CraftTown
    buf.write_method_11(1 if _is_crafttown else 0, 1)

    if _is_crafttown:
        # 13) Buildings data block
        # New level ID (_loc22_, same as transfer_token)
        new_level_id = transfer_token
        buf.write_method_4(new_level_id)

        # --- WRITE master class id so the client parses the following fields correctly ---
        master_class_id = int(char.get("MasterClass", 0) if char else 0)
        buf.write_method_6(master_class_id, Game.const_209)

        # Map MasterClass -> building id for tower lookup (ensure MASTERCLASS_TO_BUILDING exists)
        tower_building_id = MASTERCLASS_TO_BUILDING.get(master_class_id, 0)

        # Get building stats from the new save structure
        stats_by_building = {}
        if char:
            mf = char.get("magicForge", {})
            if isinstance(mf, dict):
                stats_by_building = mf.get("stats_by_building", {}) or {}
            else:
                stats_by_building = {}

        stats_by_building = char.get("magicForge", {}).get("stats_by_building", {}) if char else {}

        def _stat(bid):
            return int(stats_by_building.get(str(bid), stats_by_building.get(bid, 0) or 0))

        tome_level = _stat(1)
        forge_level = _stat(2)
        # Tower: choose the tower matching master_class_id if in tower range, fallback to first tower id 3
        stats_by_building = char.get("magicForge", {}).get("stats_by_building", {})
        tower_level = _stat(tower_building_id)
        keep_level = _stat(12)
        barn_level = _stat(13)
        # scaffolding_level: use buildingUpgrade.buildingID if present (0 otherwise)
        scaffolding_level = 0
        if char:
            bu = char.get("buildingUpgrade", {}) or {}
            scaffolding_level = int(bu.get("buildingID", 0) or 0)

        buf.write_method_6(forge_level, class_9.const_28)
        buf.write_method_6(keep_level, class_9.const_28)
        buf.write_method_6(tower_level, class_9.const_28)
        buf.write_method_6(tome_level, class_9.const_28)
        buf.write_method_6(barn_level, class_9.const_28)
        buf.write_method_6(scaffolding_level, class_9.const_129)

    payload = buf.to_bytes()
    return struct.pack(">HH", 0x21, len(payload)) + payload