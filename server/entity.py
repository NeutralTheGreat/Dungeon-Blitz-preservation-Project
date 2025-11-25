import json
import os
import struct

from typing import Dict, Any
from BitBuffer import BitBuffer
from bitreader import BitReader
from constants import Entity, class_7, class_20, class_3, Game, LinkUpdater, EntType, GearType, class_64, class_21
from globals import level_npcs, level_players

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
            "Talent_id": char.get("MasterClass", 0),
            "equippedMount": char.get("equippedMount", 0),
        })

    return ent_dict


def send_existing_entities_to_joiner(joiner, all_sessions):
    """
    Send spawn packets (Send_Entity_Data) ONLY for players in the same level
    to the joining player.
    NPCs are skipped and should be spawned separately by the level loader.
    """
    for other in all_sessions:
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
                print(f"[JOIN] Sent player {ent_dict['name']} (eid={other.clientEntID}) → {joiner.addr}")
            except Exception as ex:
                print(f"[JOIN] Error sending player {ent_dict['name']} to {joiner.addr}: {ex}")

def handle_entity_full_update(session, data, all_sessions):
    """
    Handle a full entity spawn/update (packet type 0x08)
    - Parses and stores entity info.
    - Marks player entity IDs.
    - Sends 0x0F spawn packets so players see each other.
    - Broadcasts raw 0x08 packets for movement/state sync.
    """
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        # ── Parse fields ──
        entity_id  = br.read_method_9()
        pos_x      = br.read_method_24()
        pos_y      = br.read_method_24()
        velocity_x = br.read_method_24()
        ent_name   = br.read_method_26()

        team       = br.read_method_20(Entity.TEAM_BITS)
        is_player  = bool(br.read_method_15())
        y_offset   = br.read_method_706()

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
        power_id  = br.read_method_9() if has_power else None

        ent_state   = br.read_method_20(Entity.const_316)
        b_left      = bool(br.read_method_15())
        b_running   = bool(br.read_method_15())
        b_jumping   = bool(br.read_method_15())
        b_dropping  = bool(br.read_method_15())
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
            "y_offset": y_offset,
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

        #print(f"[{session.addr}] [PKT08] Parsed entity {entity_id}:")
        #pprint.pprint(props, indent=4)

        # Update server-side map
        session.entities[entity_id] = props

        # add player to level_players
        if is_player:
            players = level_players.setdefault(session.current_level, [])
            players[:] = [p for p in players if p["id"] != entity_id]
            players.append({
                "id": entity_id,
                "pos_x": pos_x,
                "pos_y": pos_y,
                "session": session
            })

        # First-time world load for this player
        if not session.player_spawned:
            session.player_spawned = True
            send_existing_entities_to_joiner(session, all_sessions)

            # Broadcast THIS player’s spawn to others
            char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
            if char:
                ent_dict = build_entity_dict(entity_id, char, props)
                try:
                    pkt = Send_Entity_Data(ent_dict)
                    framed = struct.pack(">HH", 0x0F, len(pkt)) + pkt
                    for other in all_sessions:
                        if other is not session and other.player_spawned and other.current_level == session.current_level:
                            other.conn.sendall(framed)
                            print(f"[JOIN] Broadcasted Send_Entity_Data for {ent_dict['name']} → {other.addr}")
                except Exception as e:
                    print(f"[JOIN] Failed to build/broadcast Send_Entity_Data for new player: {e}")

        # Always forward raw 0x08 packet for movement sync
        for other in all_sessions:
            if other is not session and other.player_spawned and other.current_level == session.current_level:
                other.conn.sendall(data)
                print(f"[{session.addr}] [PKT08] Broadcasted raw packet to {other.addr}")

    except Exception as e:
        print(f"[{session.addr}] [PKT08] Error parsing packet: {e}")
        if br.debug:
            for log_line in br.get_debug_log():
                print(log_line)

def ensure_level_npcs(level_name):
    """
    Ensure NPCs for this level are loaded/spawned once.
    Returns the dict of NPCs for this level.
    """
    if level_name not in level_npcs:
        try:
            npcs = load_npc_data_for_level(level_name)
            npc_map = {}
            for npc in npcs:
                npc_map[npc["id"]] = npc
            level_npcs[level_name] = npc_map
            print(f"[LEVEL] Spawned {len(npc_map)} NPCs for {level_name}")
        except Exception as e:
            print(f"[LEVEL] Error loading NPCs for {level_name}: {e}")
            level_npcs[level_name] = {}
    return level_npcs[level_name]