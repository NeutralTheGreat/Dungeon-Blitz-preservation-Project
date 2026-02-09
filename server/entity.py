import json
import os
import struct
import time

from typing import Dict, Any
from BitBuffer import BitBuffer
from bitreader import BitReader
from constants import Entity, class_7, class_20, class_3, Game, LinkUpdater, EntType, GearType, class_64, class_21, class_118, method_277
from globals import GS, init_dungeon_run

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
      "character_name": "NR_Mayor01", 
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
- NPC will only become interactable if they have a "character_name" set and  "team" set to 3 

- look at the "MissionTypes.Json" for these 2 lines on each mission : 

"ContactName": "CaptainFink",
"ReturnName": "NR_Mayor01", 

For example the NPC with the "character_name": "NR_Mayor01",  will be linked to all the missions that have "ReturnName": "NR_Mayor01",  OR "ContactName": "NR_Mayor01",

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
            data = json.load(file)

        # Filter out hostile enemies (team 2) for tutorial levels only
        # Other dungeons use server-side AI (enabled in ai_logic.py)
        CLIENT_AI_LEVELS = (
            "TutorialDungeon", 
            "TutorialBoat",
        )
        if level_name in CLIENT_AI_LEVELS:
            data = [npc for npc in data if npc.get("team") != 2]


        return data
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

    bb.write_method_45(int(entity['x']))  # x
    bb.write_method_45(int(entity['y']))  # y
    bb.write_method_45(int(entity.get('v', 0)))  # Velocity

    bb.write_method_6(entity.get('team', 0), Entity.TEAM_BITS)

    # ── Player OR NPC branch ──
    if entity.get("is_player", False):
        bb.write_method_6(1, 1)

        timing_flag = entity.get("idle_reset", False)
        bb.write_method_6(1 if timing_flag else 0, 1)

        appearance_flag = entity.get("spawn_fx", False)  # True for new player  spawns if the player is already in the level then it is False
        bb.write_method_6(1 if appearance_flag else 0, 1)

        active_pet = entity.get("activePet", {})
        bb.write_method_6(active_pet.get("petID",      0), class_7.const_19)
        bb.write_method_6(active_pet.get("special_id", 0), class_7.const_75)
        bb.write_method_6(entity.get("equippedMount",  0), class_20.const_297)
        bb.write_method_6(entity.get("activeConsumableID",        0), class_3.const_69)

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

    cue = entity.get("cue_data", {})
    for key in ("character_name", "DramaAnim", "SleepAnim"):
        val = cue.get(key, "")
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

        class_id = entity.get("MasterClass", Game.const_526)
        bb.write_method_6(class_id, Game.const_209)

        # Talent data is ONLY allowed if a MasterClass has been equipped
        has_talent_tree = (
                class_id != Game.const_526 and
                any(
                    t and t.get("nodeID", 0) > 0 and t.get("points", 0) > 0
                    for t in entity.get("talents", [])
                )
        )

        bb.write_method_6(1 if has_talent_tree else 0, 1)

        if has_talent_tree:
            for slot in range(class_118.NUM_TALENT_SLOTS):  # ALWAYS 27
                t = entity["talents"][slot] if slot < len(entity["talents"]) else None

                if t and t.get("nodeID", 0) > 0 and t.get("points", 0) > 0:
                    bb.write_method_6(1, 1)
                    bb.write_method_6(t["nodeID"], class_118.const_127)
                    bb.write_method_6(t["points"] - 1, method_277(slot))
                else:
                    bb.write_method_6(0, 1)


    else:
        bb.write_method_6(0, 1)

    # updates the entity's Health if that specific entity has lost any amount of health
    value = int(round(entity.get("health_delta", 0)))
    bb.write_method_45(value)

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

def build_entity_dict(eid, char, props):
    """
    Build a dictionary for Send_Entity_Data packet.
    Works for both joiner (new spawn) and existing entities.
    """
    ent_dict = {
        "id": eid,
        "name": char.get("name", props.get("ent_name", "")) if char else props.get("ent_name", ""),
        "is_player": True if char else bool(props.get("is_player", False)),
        "x": int(props.get("pos_x", 0)),
        "y": int(props.get("pos_y", 0)),
        "v": int(props.get("velocity_x", 0)),
        "team": int(props.get("team", 1)),
        "buffs": list(props.get("buffs", [])),
        "facing_left": bool(props.get("b_left", False)),
    }
    if char:
        ent_dict.update({
            "class": char.get("class", ""),
            "gender": char.get("gender", ""),
            "headSet": char.get("headSet", ""),
            "hairSet": char.get("hairSet", ""),
            "mouthSet": char.get("mouthSet", ""),
            "faceSet": char.get("faceSet", ""),
            "hairColor": char.get("hairColor", 0),
            "skinColor": char.get("skinColor", 0),
            "shirtColor": char.get("shirtColor", 0),
            "pantColor": char.get("pantColor", 0),
            "equippedGears": char.get("equippedGears", []),
            "abilities": char.get("learnedAbilities", []),
            "level": char.get("level", 1),
            "MasterClass": char.get("MasterClass", 0),
            "talents": build_talent_slots(char),
            "equippedMount": char.get("equippedMount", 0)
        })

    return ent_dict

def build_talent_slots(char: dict) -> list:
    slots = [None] * class_118.NUM_TALENT_SLOTS

    master_class = char.get("MasterClass", 0)
    if master_class == 0:
        return slots

    tree = char.get("TalentTree", {})
    class_tree = tree.get(str(master_class))
    if not class_tree:
        return slots

    for node in class_tree.get("nodes", []):
        if not node.get("filled"):
            continue

        node_id = node.get("nodeID", 0)
        points  = node.get("points", 0)
        if node_id <= 0 or points <= 0:
            continue

        slot = node_id - 1
        if slot < 0 or slot >= class_118.NUM_TALENT_SLOTS:
            continue

        slots[slot] = {
            "nodeID": node_id,
            "points": points
        }

    return slots

def send_existing_entities_to_joiner(joiner):
    """
    Send spawn packets (Send_Entity_Data) ONLY for players in the same level
    to the joining player.
    NPCs are skipped and should be spawned separately by the level loader.
    """
    for other in GS.all_sessions:
        if other is joiner:
            continue
        if not other.player_spawned or other.current_level != joiner.current_level:
            continue

        # Only send the entity that belongs to the player's character
        if other.clientEntID and other.clientEntID in other.entities:
            eprops = other.entities[other.clientEntID]

            char = next((c for c in other.char_list if c.get("name") == other.current_character), None)
            ent_dict = build_entity_dict(other.clientEntID, char, eprops)

            try:
                pkt = Send_Entity_Data(ent_dict)
                framed = struct.pack(">HH", 0x0F, len(pkt)) + pkt
                joiner.conn.sendall(framed)
                #print(f"[JOIN] Sent player {ent_dict['name']} (eid={other.clientEntID}) → {joiner.addr}")
            except Exception as ex:
                print(f"[JOIN] Error sending player {ent_dict['name']} to {joiner.addr}: {ex}")

def handle_entity_full_update(session, data):
    """
    Handle a full entity spawn/update (packet type 0x08)
    - Parses and stores entity info.
    - Marks player entity IDs.
    - Sends 0x0F spawn packets so players see each other.
    - Broadcasts raw 0x08 packets for movement/state sync.
    - sends 0x0F for newly-seen non-player entities (pets/minions).
    """
    br = BitReader(data[4:])

    entity_id = br.read_method_9()
    pos_x = br.read_method_24()
    pos_y = br.read_method_24()
    velocity_x = br.read_method_24()
    ent_name = br.read_method_26()

    team = br.read_method_20(Entity.TEAM_BITS)
    is_player = bool(br.read_method_15())
    y_offset = br.read_method_706()

    # Optional cue data
    has_cue = bool(br.read_method_15())
    cue_data = {}
    if has_cue:
        if bool(br.read_method_15()):
            cue_data["character_name"] = br.read_method_13()
        if bool(br.read_method_15()):
            cue_data["DramaAnim"] = br.read_method_13()
        if bool(br.read_method_15()):
            cue_data["SleepAnim"] = br.read_method_13()

    has_summoner = bool(br.read_method_15())
    summoner_id = br.read_method_9() if has_summoner else None

    has_power = bool(br.read_method_15())
    power_id = br.read_method_9() if has_power else None

    ent_state = br.read_method_20(Entity.const_316)
    b_left = bool(br.read_method_15())
    b_running = bool(br.read_method_15())
    b_jumping = bool(br.read_method_15())
    b_dropping = bool(br.read_method_15())
    b_backpedal = bool(br.read_method_15())

    # Track client’s entity ID
    if is_player and session.clientEntID is None:
        session.clientEntID = entity_id
        print(f"[{session.addr}] [PKT08] Learned clientEntID = {entity_id}")

    # Build props
    props = {
        "pos_x": pos_x,
        "pos_y": pos_y,
        "velocity_x": velocity_x,
        "ent_name": ent_name,
        "team": team,
        "is_player": is_player,
        "render_depth_offset": y_offset,
        "cue_data": cue_data,
        "summoner_id": summoner_id,
        "power_id": power_id,
        "ent_state": ent_state,
        "b_left": b_left,
        "b_running": b_running,
        "b_jumping": b_jumping,
        "b_dropping": b_dropping,
        "b_backpedal": b_backpedal,
    }

    # Was this entity already known in this session?
    is_new_entity = entity_id not in session.entities

    # Update server-side map
    session.entities[entity_id] = props

    level = session.current_level
    level_map = GS.level_entities.setdefault(level, {})

    level_map[entity_id] = {
        "id": entity_id,
        "kind": "player" if is_player else "npc",
        "session": session if is_player else None,
        "props": {
            "id": entity_id,
            "name": ent_name,
            "is_player": is_player,
            "x": int(pos_x),
            "y": int(pos_y),
            "v": int(velocity_x),
            "team": int(team),
            "untargetable": False,
            "render_depth_offset": y_offset,
            "behavior_speed": 0.0,
            "cue_data": cue_data,
            "summonerId": summoner_id or 0,
            "power_id": power_id or 0,
            "entState": ent_state,
            "facing_left": b_left,
            "health_delta": 0,
            "buffs": [],
        },
    }

    # ─────────────────────────────
    # spawn non-player entities (pets / minions) for other clients
    # ─────────────────────────────
    if is_new_entity and not is_player:

        ent_dict = {
            "id": entity_id,
            "name": ent_name,
            "is_player": False,
            "x": int(pos_x),
            "y": int(pos_y),
            "v": int(velocity_x),
            "render_depth_offset": y_offset,
            "team": int(team),
            "cue_data": cue_data,
            "summonerId": summoner_id or 0,
            "power_id": power_id or 0,
            "entState": ent_state,
            "facing_left": b_left,
            "health_delta": 0,
            "buffs": [],
        }

        flat_ent = normalize_entity_for_send(ent_dict)
        pkt = Send_Entity_Data(flat_ent)
        framed = struct.pack(">HH", 0x0F, len(pkt)) + pkt

        for other in GS.all_sessions:
            if (
                    other is not session
                    and other.player_spawned
                    and other.current_level == session.current_level
            ):
                other.conn.sendall(framed)
                print(f"[SPAWN] Broadcasted new entity {entity_id} ({ent_name}) → {other.addr}")

    # First-time world load for this player
    if not session.player_spawned:
        session.player_spawned = True
        send_existing_entities_to_joiner(session)
        
        # Re-sync gear to self so client recalculates find stats from runes
        from combat import send_gear_to_self
        send_gear_to_self(session)


        # Broadcast THIS player’s spawn to others
        char = next(
            (c for c in session.char_list if c.get("name") == session.current_character),
            None
        )
        if char:
            ent_dict = build_entity_dict(entity_id, char, props)
            flat_ent = normalize_entity_for_send(ent_dict)
            pkt = Send_Entity_Data(flat_ent)
            framed = struct.pack(">HH", 0x0F, len(pkt)) + pkt
            for other in GS.all_sessions:
                if (
                        other is not session
                        and other.player_spawned
                        and other.current_level == session.current_level
                ):
                    other.conn.sendall(framed)
                    #print(f"[JOIN] Broadcasted Send_Entity_Data for {ent_dict['name']} → {other.addr}")

def ensure_level_npcs(level_name: str) -> None:
    if level_name in GS.level_entities:
        return

    npcs = load_npc_data_for_level(level_name)
    try:
        from level_config import is_dungeon_level  # local import to avoid circulars
    except Exception:
        is_dungeon_level = lambda _: False

    if is_dungeon_level(level_name):
        total_enemies = sum(1 for npc in npcs if npc.get("team") == 2)
        init_dungeon_run(level_name, total_enemies)

    level_map = GS.level_entities.setdefault(level_name, {})

    for npc_template in npcs:
        npc_id = allocate_entity_id()

        npc = dict(npc_template)
        npc["id"] = npc_id
        # Seed position fields consistently
        npc.setdefault("x", npc.get("pos_x", npc.get("x", 0.0)))
        npc.setdefault("y", npc.get("pos_y", npc.get("y", 0.0)))
        npc["pos_x"] = npc.get("x", 0.0)
        npc["pos_y"] = npc.get("y", 0.0)

        level_map[npc_id] = {
            "id": npc_id,
            "kind": "npc",
            "session": None,
            "props": npc,
        }




def normalize_entity_for_send(entity: dict) -> dict:
    out = dict(entity)

    cue = entity.get("cue_data", {})
    if cue:
        for key in ("character_name", "DramaAnim", "SleepAnim"):
            if key in cue and cue[key]:
                out[key] = cue[key]

    out.setdefault("character_name", "")
    out.setdefault("DramaAnim", "")
    out.setdefault("SleepAnim", "")
    return out


def npc_container_to_entity(container: dict) -> dict:
    props = container["props"]
    out = dict(props)
    out["id"] = container["id"]
    out.setdefault("health_delta", 0)
    out.setdefault("buffs", [])
    return out


def allocate_entity_id():
    eid = GS.next_entity_id
    GS.next_entity_id += 1
    return eid
