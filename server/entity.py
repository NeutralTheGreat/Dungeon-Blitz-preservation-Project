import json
import os

from BitBuffer import BitBuffer
from constants import Entity, class_7, class_20, class_3, Game, LinkUpdater, EntType, GearType, class_64, class_21
from typing import Dict, Any
npc_cache = {}
"""
Hints NPCs data 
[
    {
      "id": 3,
      "name": "NPCRuggedVillager02",
      "x": 3317,
      "y": 461,
      "v": 0,
      "team": 3,
      "untargetable": false,
      "render_depth_offset": -15,
      "behavior_speed": 0.0,
      "Linked_Mission": "NR_Mayor01", 
      "DramaAnim": "",
      "SleepAnim": "",
      "summonerId": 0,
      "power_id": 0,
      "entState": 0,
      "facing_left": true,
      "health_delta": 0,
      "buffs": []
    }
]

======== Intercatible NPCs Tips =====================
- how to make the NPC interactable by the player
- NPC will only become interactable if they have a "Linked_Mission" set and  "team" set to 3 

- look at the "MissionTypes.Json" for these 2 lines on each mission : 

"ContactName": "CaptainFink",
"ReturnName": "NR_Mayor01", 

For example the NPC with the "Linked_Mission": "NR_Mayor01",  will be linked to all the missions that have "ReturnName": "NR_Mayor01",  OR "ContactName": "NR_Mayor01",

- this will also show the NPCs name under his feet "NR_Mayor01" is "Mayor Ristas"

===============

Team Types : 

 const_531:uint = 0; # team type will be automatically chosen  its  used for a entity called "EmberBush" :/ but it will also give any other NPC team 2 (enemies)
      
 GOODGUY:uint = 1; #  players 
      
 BADGUY:uint = 2; # Enemies 
      
 NEUTRAL:uint = 3; # Friendly NPC
 
entState : 
 
 0 = Active State
 
 1 = Sleep State
 
 2 = Drama State (used during cutscenes most likely) this will put the entity to sleep also make them untargetable 
 
 3 = Entity Dies when the game loads 
 
 =============== how to use "DramaAnim" and "SleepAnim" ===============
 
 for "DramaAnim" to activate you have to set the "entState" to 2  
 
 for "SleepAnim" to activate you have to set the "entState" to 1 
 
 you can find which entity uses "DramaAnim" and "SleepAnim" at EntTypes.json some entities have "DramaAnim" or "SleepAnim" defined 
 
 Example : 
      
     # goblin will spawn in the boarding ship animation 
     {
      "name": "IntroGoblinJumper",
      "DramaAnim": "board",
      "SleepAnim": "",
      "entState": 2,
    }
    
    # the eye will spawn closed 
    {
      "name": "NephitCrownEye",
      "DramaAnim": "Sleep",
      "SleepAnim": "",
      "entState": 1,
    }
"""

def load_npc_data_for_level(level_name: str) -> list:
    json_path = os.path.join("world_npcs", f"{level_name}.json")
    try:
        with open(json_path, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading NPC data for {level_name}: {e}")
        return []

def Send_Entity_Data(entity: Dict[str, Any]) -> bytes:
    bb = BitBuffer(debug=True)
    bb.write_method_4(entity['id'])
    bb.write_method_13(entity['name'])
    if entity.get("is_player", False):
        bb.write_method_6(1, 1)
        bb.write_method_13(entity.get("class", ""))
        bb.write_method_13(entity.get("gender", ""))
        bb.write_method_13(entity.get("headSet", ""))
        bb.write_method_13(entity.get("hairSet", ""))
        bb.write_method_13(entity.get("mouthSet", ""))
        bb.write_method_13(entity.get("faceSet", ""))
        bb.write_method_6(entity.get("hairColor", 0), 24)
        bb.write_method_6(entity.get("skinColor", 0), 24)
        bb.write_method_6(entity.get("shirtColor", 0), 24)
        bb.write_method_6(entity.get("pantColor", 0), 24)
        equipped = entity.get('equippedGears', [])
        for slot in range(1, EntType.MAX_SLOTS):
            idx = slot - 1
            if idx < len(equipped) and equipped[idx] is not None:
                gear = equipped[idx]
                bb.write_method_6(1, 1)
                bb.write_method_6(gear['gearID'], GearType.GEARTYPE_BITSTOSEND)
                bb.write_method_6(gear['tier'], GearType.const_176)
                runes = gear.get('runes', [0, 0, 0])
                bb.write_method_6(runes[0], class_64.const_101)
                bb.write_method_6(runes[1], class_64.const_101)
                bb.write_method_6(runes[2], class_64.const_101)
                colors = gear.get('colors', [0, 0])
                bb.write_method_6(colors[0], class_21.const_50)
                bb.write_method_6(colors[1], class_21.const_50)
            else:
                bb.write_method_6(0, 1)
    else:
        bb.write_method_6(0, 1)

    bb.write_signed_method_45(int(entity['x']))  # x
    bb.write_signed_method_45(int(entity['y']))  # y
    bb.write_signed_method_45(int(entity['v']))  # Velocity

    bb.write_method_6(entity.get('team', 0), Entity.TEAM_BITS)

    # ── Player OR NPC branch ──
    if entity.get("is_player", False):
        bb.write_method_6(1, 1)

        timing_flag = entity.get("set_timing_flag", False)
        bb.write_method_6(1 if timing_flag else 0, 1)
        if bb.debug:
            bb.debug_log.append(f"timing_flag={timing_flag}")

        appearance_flag = entity.get("show_appearance_effect", False)  # True for new player  spawns if the player is already in the level then it is False
        bb.write_method_6(1 if appearance_flag else 0, 1)
        if bb.debug:
            bb.debug_log.append(f"appearance_flag={appearance_flag}")

        #the actual purpose of these 4 lines  are currently unknown but the client reads the data properly
        # ====================================
        bb.write_method_6(entity.get("PetTypeID", 0), class_7.const_19)
        bb.write_method_6(entity.get("PetLevel", 0), class_7.const_75)
        bb.write_method_6(entity.get("MountID", 0), class_20.const_297)
        bb.write_method_6(entity.get("Emote_ID", 0), class_3.const_69)
        # ====================================
        abilities = entity.get("abilities", [])
        has_abilities = len(abilities) > 0
        bb.write_method_6(1 if has_abilities else 0, 1)
        if bb.debug:
            bb.debug_log.append(f"has_abilities={has_abilities}")
        if has_abilities:
            for i in range(3):
                ability = abilities[i] if i < len(abilities) and abilities[i] is not None else {"abilityID": 0, "rank": 0}
                bb.write_method_6(ability.get("abilityID", 0), class_7.const_19)
                bb.write_method_6(ability.get("rank", 0), class_7.const_75)
                if bb.debug:
                    bb.debug_log.append(
                        f"ability_{i + 1}_abilityID={ability.get('abilityID', 0)}, rank={ability.get('rank', 0)}")
    else:
        bb.write_method_6(0, 1)
        bb.write_method_6(1 if entity.get("untargetable", False) else 0, 1)
        bb.write_method_739(entity.get("render_depth_offset", 0))

        # used to set the current entity's moving speed if he has any
        speed = entity.get("behavior_speed", 0)
        if speed > 0:
            bb.write_method_6(1, 1)
            bb.write_method_4(int(speed * LinkUpdater.VELOCITY_INFLATE))
        else:
            bb.write_method_6(0, 1)

    for key in ("Linked_Mission", "DramaAnim", "SleepAnim"):
        val = entity.get(key, "")
        bb.write_method_6(1 if val else 0, 1)
        if val:
            bb.write_method_13(val)

    summoner_id = entity.get("summonerId", 0)
    if summoner_id:
        bb.write_method_6(1, 1)
        bb.write_method_4(summoner_id)
        if bb.debug:
            bb.debug_log.append(f"summonerId = {summoner_id}")
    else:
        bb.write_method_6(0, 1)

    power_id = entity.get("power_id", 0)

    if power_id > 0:
        bb.write_method_6(1, 1)
        bb.write_method_4(power_id)
        if bb.debug:
            bb.debug_log.append(f"powerTypeID = {power_id}")
    else:
        bb.write_method_6(0, 1)

    bb.write_method_6(entity.get("entState", 0), Entity.const_316)
    bb.write_method_6(1 if entity.get("facing_left", False) else 0, 1)
    if entity.get('is_player', False):

        level = entity.get("level", 0)
        bb.write_method_6(level, Entity.MAX_CHAR_LEVEL_BITS)
        if bb.debug:
            bb.debug_log.append(f"level={level}")

        class_id = entity.get("Talent_id", Game.const_526)
        bb.write_method_6(class_id, Game.const_209)
        if bb.debug:
            bb.debug_log.append(f"Talent_id={class_id}")

        # we are not sending any Talent Data
        bb.write_method_6( 0, 1)
        #TODO...
        # this will crash the game not sure why the game seems to read the bitstream properly
        # after this is fixed the bitstream should be fully in sync with the client
        """ 
        # 5f) Talent Nodes / Upgrades
        talents = entity.get("talents", [])
        has_talents = any(t for t in talents if t)  # at least one slot filled
        bb.write_method_6(1 if has_talents else 0, 1)

        if has_talents:
            for slot in range(NUM_TALENT_SLOTS):  # always 27 slots
                t = talents[slot] if slot < len(talents) and talents[slot] else None
                if t and t.get("nodeID", 0) > 0 and t.get("points", 0) > 0:
                    node_id = t["nodeID"]
                    points = t["points"]
                    bb.write_method_6(1, 1)  # slot filled
                    bb.write_method_6(node_id, CLASS_118_CONST_127)  # 6 bits for nodeID
                    bb.write_method_6(points - 1, method_277(slot))  # N bits for points

                else:
                    bb.write_method_6(0, 1)  # empty slot
        """
    else:
        bb.write_method_6(0, 1)

    # updates the entity's Health if that specific entity has lost any amount of health
    value = int(round(entity.get("health_delta", 0)))
    bb.write_signed_method_45(value)

    # Updates the entities buffs if he has any
    buffs = entity.get("buffs", [])
    bb.write_method_4(len(buffs))
    for buff in buffs:
        bb.write_method_4(buff.get("type_id", 0))
        bb.write_method_4(buff.get("param1", 0))
        bb.write_method_4(buff.get("param2", 0))
        bb.write_method_4(buff.get("param3", 0))
        bb.write_method_4(buff.get("param4", 0))
        extra = buff.get("extra_data", [])
        bb.write_method_6(1 if extra else 0, 1)
        if extra:
            bb.write_method_4(len(extra))
            for ed in extra:
                bb.write_method_4(ed.get("id", 0))
                vals = ed.get("values", [])
                bb.write_method_4(len(vals))
                for v in vals:
                    bb.write_float(v)
    return bb.to_bytes()