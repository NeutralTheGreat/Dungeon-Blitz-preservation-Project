import json, struct
import random
import secrets

from Character import save_characters, build_paperdoll_packet, get_inventory_gears, \
    build_level_gears_packet, SAVE_PATH_TEMPLATE
from bitreader import BitReader
from constants import GearType, EntType, class_64, class_1, DyeType, class_118, method_277, \
    PowerType, Entity, Game
from BitBuffer import BitBuffer
from constants import get_dye_color
from globals import build_start_skit_packet, send_premium_purchase, _send_error, \
    level_players


def handle_request_armory_gears(session, data, conn):
    payload = data
    br = BitReader(payload[4:], debug=False)
    try:
        var_2744 = br.read_method_9()
        print(f"[0xF4] Client sent var_2744={var_2744}, raw={payload.hex()}")

        if session.current_character:
            char = next((c for c in session.char_list if c["name"] == session.current_character), None)
            if char:
                gears_list = get_inventory_gears(char)
                packet = build_level_gears_packet(gears_list)
                conn.sendall(packet)
                print(f"[0xF4] Sent 0xF5 Armory gear list ({len(gears_list)} items)")
    except Exception as e:
        print(f"[0xF4] Error parsing: {e}, raw={payload.hex()}")

#TODO...
def handle_talk_to_npc(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload)

    try:
        npc_id = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [PKT0x7A] Failed to parse NPC ID: {e}")
        return

    # Look up in session.entities (where NPCs are inserted on spawn)
    npc = session.entities.get(npc_id)
    if not npc:
        print(f"[{session.addr}] [PKT0x7A] Unknown NPC id={npc_id}")
        return

    npc_name = npc.get("name", f"NPC_{npc_id}")
    print(f"[{session.addr}] [PKT0x7A] Talked to NPC {npc_id} ({npc_name})")

    # Build and send the skit packet to the interacting client only
    skit_packet = build_start_skit_packet(npc_id, dialogue_id=0, mission_id=0)
    session.conn.sendall(skit_packet)

"""def handle_talk_to_npc(session, data, all_sessions):

    #Handles client packet 0x7A (talk-to-NPC request).
    #Reads the NPC ID, determines what dialogue/skit should play based on
    #current missions and NPC role, then sends the start-skit packet
    #back to the interacting client only.

    payload = data[4:]
    br = BitReader(payload)

    try:
        npc_id = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [PKT0x7A] Failed to parse NPC ID: {e}")
        return

    npc = session.entities.get(npc_id)
    if not npc:
        print(f"[{session.addr}] [PKT0x7A] Unknown NPC id={npc_id}")
        return

    npc_name = npc.get("name", f"NPC_{npc_id}")

    # Default values: generic dialogue (no mission involvement)
    dialogue_id = 0
    mission_id = 0

    # Get player's mission state
    char_data = getattr(session, "current_char_dict", None) or {}
    player_missions = char_data.get("missions", {})

    # Try to match a mission relevant to this NPC
    for mid_str, mdata in player_missions.items():
        try:
            mid = int(mid_str)
        except (ValueError, TypeError):
            continue

        mextra = get_mission_extra(mid)
        if not mextra:
            continue

        contact_name = (mextra.get("ContactName") or "").strip()
        return_name = (mextra.get("ReturnName") or "").strip()
        state = mdata.get("state", 2)

        if npc_name == contact_name:
            if state == 0:
                dialogue_id = 2  # OfferText
                mission_id = 0  # not yet acquired — do not send mission ID
            elif state == 1:
                dialogue_id = 3  # ActiveText
                mission_id = mid
            elif state == 2:
                dialogue_id = 5  # PraiseText
                mission_id = mid

        elif npc_name == return_name or state == 2:
            if state == 1:
                dialogue_id = 4
            elif state == 2:
                dialogue_id = 5
            mission_id = mid
            break
    # Build and send the start skit packet only to this client
    pkt = build_start_skit_packet(npc_id, dialogue_id, mission_id)
    session.conn.sendall(pkt)
    print(
        f"[{session.addr}] [PKT0x7A] Talked to NPC ID: {npc_id} ({npc_name}) → "
        f"sent skit (dialogue_id={dialogue_id}, mission_id={mission_id})"
    )
"""

#TODO...
def handle_collect_hatched_egg(conn, char):
      pass

REWARD_TYPES = ['gear', 'item', 'gold', 'chest', 'xp', 'potion']
GEARTYPE_BITS = GearType.GEARTYPE_BITSTOSEND  # e.g. 5

def build_loot_drop_packet(entity_id: int, x: int, y: int,
                           reward_type: str, value1: int=0, value2: int=0) -> bytes:
    """
    Packet 0x32: one bit per reward in order:
      [gear, item, gold, chest, xp, potion]
    """
    bb = BitBuffer(debug=True)

    # 1) Entity ID
    bb.write_method_4(entity_id)

    # 2) X,Y (signed)
    bb.write_signed_method_45(x)
    bb.write_signed_method_45(y)

    # 3) no-offset flag = 0
    bb.write_method_11(1, 1)

    # 4) six-type flags + payload
    for rt in REWARD_TYPES:
        bit = 1 if rt == reward_type else 0
        bb.write_method_11(bit, 1)
        if bit:
            if rt == 'gear':
                bb.write_method_6(value1, GEARTYPE_BITS)
                bb.write_method_6(value2, GEARTYPE_BITS)
            else:
                bb.write_method_4(value1)
            break

    payload = bb.to_bytes()
    header  = struct.pack('>HH', 0x32, len(payload))
    return header + payload

def handle_lockbox_reward(session):
    CAT_BITS = 3
    ID_BITS = 6
    PACK_ID = 1
    reward_map = {
        0: ("MountLockbox01L01", True),  # Mount
        1: ("Lockbox01L01", True),  # Pet
        # 2: ("GenericBrown", True),  # Egg
        # 3: ("CommonBrown", True),  # Egg
        # 4: ("OrdinaryBrown", True),  # Egg
        # 5: ("PlainBrown", True),  # Egg
        6: ("RarePetFood", True),  # Consumable
        7: ("PetFood", True),  # Consumable
        # 8: ("Lockbox01Gear", True),  # Gear (will crash if invalid)
        9: ("TripleFind", True),  # Charm
        10: ("DoubleFind1", True),  # Charm
        11: ("DoubleFind2", True),  # Charm
        12: ("DoubleFind3", True),  # Charm
        13: ("MajorLegendaryCatalyst", True),  # Consumable
        14: ("MajorRareCatalyst", True),  # Consumable
        15: ("MinorRareCatalyst", True),  # Consumable
        16: (None, False),  # Gold (3 000 000)
        17: (None, False),  # Gold (1 500 000)
        18: (None, False),  # Gold (750 000)
        19: ("DyePack01Legendary", True),  # Dye‐pack
    }

    idx, (name, needs_str) = random.choice(list(reward_map.items()))
    bb = BitBuffer()
    bb.write_method_6(PACK_ID, CAT_BITS)
    bb.write_method_6(idx, ID_BITS)
    bb.write_method_6(1 if needs_str else 0, 1)
    if needs_str:
        bb.write_method_13(name)

    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0x108, len(payload)) + payload
    session.conn.sendall(packet)

    print(f"Lockbox reward: idx={idx}, name={name}, needs_str={needs_str}")

def send_talent_tree_packet(session, entity_id):
    """
    Sends the talent tree for the player's current MasterClass.
    Uses the new 27-slot array structure.
    """
    mc = None
    nodes = [None] * class_118.NUM_TALENT_SLOTS

    for char in session.char_list:
        if char.get("name") == session.current_character:
            mc = char.get("MasterClass", 1)
            tree = char.get("TalentTree", {}).get(str(mc), {})
            nodes = tree.get("nodes", [None] * class_118.NUM_TALENT_SLOTS)
            break
    else:
        return  # no matching character

    session.player_data["characters"] = session.char_list

    # Build the packet
    bb = BitBuffer()
    bb.write_method_4(entity_id)

    for i, slot in enumerate(nodes):
        slot = slot or {"filled": False, "points": 0, "nodeID": i + 1}

        if slot.get("filled", False):
            bb.write_method_6(1, 1)  # has this node
            node_id = slot.get("nodeID", i + 1)
            bb.write_method_6(node_id, class_118.const_127)  # send nodeIdx (1-based)
            width = method_277(i)
            bb.write_method_6(slot["points"] - 1, width)  # points minus one
        else:
            bb.write_method_6(0, 1)  # no node present

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0xC1, len(payload)) + payload
    session.conn.sendall(pkt)
    print(f"[Reply 0xC1] TalentTree for class {mc}, total slots: {len(nodes)}")

def handle_masterclass_packet(session, raw_data):
    payload = raw_data[4:]
    br = BitReader(payload)
    entity_id       = br.read_method_4()
    master_class_id = br.read_method_6(Game.const_209)
    print(f"[MasterClass] Player {session.user_id} → classID={master_class_id}")

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
    print(f"[Reply 0xC3] entity={entity_id}, class={master_class_id}")

    send_talent_tree_packet(session, entity_id)


def handle_gear_packet(session, raw_data):
    payload = raw_data[4:]
    br = BitReader(payload)

    entity_id  = br.read_method_4()
    prefix     = br.read_method_20(3)
    nbits      = 2 * (prefix + 1)
    slot1      = br.read_method_20(nbits)
    gear_id    = br.read_method_6(GearType.GEARTYPE_BITSTOSEND)
    slot       = slot1 - 1

    print(f"[Gear] entity={entity_id}, slot={slot}, gear={gear_id}")
    # 1) Locate and update the character in session.char_list
    for char in session.char_list:
        if char.get("name") != session.current_character:
            continue

        inv = char.setdefault("inventoryGears", [])
        eq  = char.setdefault("equippedGears", [])

        # Ensure equipped list has enough slots
        while len(eq) < 6:
            eq.append({"gearID": 0, "tier": 0, "runes": [0, 0, 0], "colors": [0, 0]})

        # 1) Try to find gear in inventory
        for item in inv:
            if item.get("gearID") == gear_id:
                gear_data = item.copy()
                break
        else:
            # fallback default if not found (client will still fail visually, but we'll keep server consistent)
            gear_data = {
                "gearID": gear_id,
                "tier": 0,
                "runes": [0, 0, 0],
                "colors": [0, 0]
            }

        # 2) Set gear in equipped slot
        eq[slot] = gear_data

        # 3) Ensure gear also exists in inventory (add if missing)
        if not any(g.get("gearID") == gear_id for g in inv):
            inv.append(gear_data.copy())  # keep dye/rune info consistent

        break
    # 2) Sync into session.player_data if still used
    session.player_data["characters"] = session.char_list

    # 3) Persist via helper
    save_characters(session.user_id, session.char_list)
    print(f"[Save] slot {slot} updated with gear {gear_id}, inventory count = {len(inv)}")

def handle_equip_rune(session, raw_data):
    payload = raw_data[4:]
    br = BitReader(payload)
    entity_id = br.read_method_4()
    gear_id    = br.read_method_6(GearType.GEARTYPE_BITSTOSEND)
    gear_tier  = br.read_method_6(GearType.const_176)
    rune_id    = br.read_method_6(class_64.const_101)
    rune_slot  = br.read_method_6(class_1.const_765)
    print(f"[Rune] entity={entity_id}, gear={gear_id}, tier={gear_tier}, rune_id={rune_id}, rune_slot={rune_slot}")

    for char in session.char_list:
        if char.get("name") != session.current_character:
            continue

        eq     = char.setdefault("equippedGears", [])
        inv    = char.setdefault("inventoryGears", [])
        charms = char.setdefault("charms", [])

        # Ensure correct slot count
        desired_slots = EntType.MAX_SLOTS - 1
        while len(eq) < desired_slots:
            eq.append({
                "gearID": 0,
                "tier": 0,
                "runes": [0, 0, 0],
                "colors": [0, 0]
            })
        if len(eq) > desired_slots:
            eq[:] = eq[:desired_slots]

        gear_found = False
        for slot in range(len(eq)):
            if eq[slot]["gearID"] == gear_id and eq[slot]["tier"] == gear_tier:
                idx = rune_slot - 1
                if 1 <= rune_slot <= 3:
                    old_rune = eq[slot]["runes"][idx]

                    if rune_id == 96:
                        # 1) Clear the rune slot
                        eq[slot]["runes"][idx] = 0

                        # 2) Return old_rune to charms
                        if old_rune and old_rune != 96:
                            for charm in charms:
                                if charm["charmID"] == old_rune:
                                    charm["count"] += 1
                                    break
                            else:
                                charms.append({"charmID": old_rune, "count": 1})

                        # 3) Decrement remover (ID 96) count
                        for charm in charms:
                            if charm["charmID"] == 96:
                                charm["count"] -= 1
                                if charm["count"] <= 0:
                                    charms.remove(charm)
                                break
                        else:
                            print("[Warning] No rune‑removers found to consume")

                    else:
                        # Equip new rune → set slot & decrement its count
                        eq[slot]["runes"][idx] = rune_id
                        for charm in charms:
                            if charm["charmID"] == rune_id:
                                charm["count"] -= 1
                                if charm["count"] <= 0:
                                    charms.remove(charm)
                                break
                        else:
                            print(f"[Warning] Equipped rune {rune_id} not in charms")

                    gear_found = True

                    # Sync inventoryGears
                    for item in inv:
                        if item["gearID"] == gear_id and item["tier"] == gear_tier:
                            item["runes"][idx] = eq[slot]["runes"][idx]
                            break
                    else:
                        inv.append(eq[slot].copy())
                break

        if not gear_found:
            print(f"[Warning] Gear {gear_id} (tier {gear_tier}) not found for {session.current_character}")
            return

        break
    else:
        print(f"[Warning] Character {session.current_character} not found")
        return

    # Save updated data
    # 2) Sync session.player_data and persist
    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)
    print(f"[Save] Rune {rune_id} applied to slot {rune_slot} for gear {gear_id} (tier {gear_tier})")

    # Echo response to client
    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)
    bb.write_method_6(gear_tier, GearType.const_176)
    bb.write_method_6(rune_id, class_64.const_101)
    bb.write_method_6(rune_slot, class_1.const_765)
    resp = struct.pack(
        ">HH", 0xB0, len(bb.to_bytes())) + bb.to_bytes()
    session.conn.sendall(resp)
    print(
        f"[Reply 0xB0] Echoed rune update: entity={entity_id}, gear={gear_id}, tier={gear_tier}, rune={rune_id}, slot={rune_slot}")

def send_look_update_packet(session, entity_id, head, hair, mouth, face, gender, hair_color, skin_color):
    """
    Send the look update packet (const_941) to a client session.

    Args:
        session: The client session object with a connection (session.conn).
        entity_id: The ID of the entity being updated (uint).
        head: Head appearance string.
        hair: Hair appearance string.
        mouth: Mouth appearance string.
        face: Face appearance string.
        gender: Gender string.
        hair_color: Hair color value (24-bit uint).
        skin_color: Skin color value (24-bit uint).
    """
    # Create a BitBuffer to build the payload
    bb = BitBuffer()

    # Write data according to the packet structure
    bb.write_method_4(entity_id)  # Entity ID (variable-length uint)
    bb.write_method_13(head)  # Head string
    bb.write_method_13(hair)  # Hair string
    bb.write_method_13(mouth)  # Mouth string
    bb.write_method_13(face)  # Face string
    bb.write_method_13(gender)  # Gender string
    bb.write_method_6(hair_color, EntType.CHAR_COLOR_BITSTOSEND)  # Shirt color (24 bits)
    bb.write_method_6(skin_color, EntType.CHAR_COLOR_BITSTOSEND)  # Pant color (24 bits)

    payload = bb.to_bytes()
    packet_type = 0x8F
    session.conn.sendall(struct.pack(">HH", packet_type, len(payload)) + payload)

def handle_change_look(session, raw_data, all_sessions):
    """
    Handle the look change request from the client (packet 0x8E).
    Updates live entity, saved character data, persists, and broadcasts.
    """
    # ─── (1) Parse incoming packet ────────────────────────────────────────────────
    payload = raw_data[4:]  # skip type+length
    br = BitReader(payload)

    head       = br.read_method_26()
    hair       = br.read_method_26()
    mouth      = br.read_method_26()
    face       = br.read_method_26()
    gender     = br.read_method_26()
    hair_color = br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND)
    skin_color = br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND)

    entity_id = session.clientEntID

    # ─── (2) In-memory entity update ─────────────────────────────────────────────
    if entity_id in session.entities:
        ent = session.entities[entity_id]
        ent.update({
            "headSet": head,
            "hairSet": hair,
            "mouthSet": mouth,
            "faceSet": face,
            "gender": gender,
            "hairColor": hair_color,
            "skinColor": skin_color,
        })

    # ─── (3) Update per-character saved data ────────────────────────────────────
    updated = False
    for char in session.char_list:
        if char.get("name") == session.current_character:
            char.update({
                "headSet": head,
                "hairSet": hair,
                "mouthSet": mouth,
                "faceSet": face,
                "gender": gender,
                "hairColor": hair_color,
                "skinColor": skin_color,
            })
            updated = True
            break

    if not updated:
        print(f"[Look] ERROR: character {session.current_character} not found in char_list")
        return

    # ─── (4) Persist to disk ─────────────────────────────────────────────────────
    save_characters(session.user_id, session.char_list)
    print(f"[Save] Look updated for {session.current_character}")

    # ─── (5) Send update back to requester ──────────────────────────────────────
    send_look_update_packet(
        session,
        entity_id,
        head, hair, mouth, face,
        gender, hair_color, skin_color
    )

    # ─── (6) Broadcast to nearby clients ────────────────────────────────────────
    for other in all_sessions:
        if (other is not session and
            other.world_loaded and
            other.current_level == session.current_level):
            send_look_update_packet(
                other,
                entity_id,
                head, hair, mouth, face,
                gender, hair_color, skin_color
            )

def handle_create_gearset(session, raw_data):
    """
    Packet 0xC7: client wants to create a new gear-set slot.
    Payload is a single uint: the new slot index.
    """
    payload = raw_data[4:]
    br = BitReader(payload)
    slot_idx = br.read_method_20(GearType.const_348)
    print(f"[GearSet] Creating new slot #{slot_idx} for {session.current_character}")

    # update in-memory save
    pd = session.player_data
    chars = pd.get("characters", [])
    for char in chars:
        if char.get("name") != session.current_character:
            continue
        gs = char.setdefault("gearSets", [])
        # Insert a new gearset object with name and slots
        gearset = {
            "name": f"GearSet {slot_idx + 1}",
            "slots": [0] * (EntType.MAX_SLOTS - 1)  # 6 slots
        }
        if slot_idx < len(gs):
            gs[slot_idx] = gearset
        else:
            gs.append(gearset)
        break
    else:
        print(f"[WARNING] Character not found for create_gearset")
        return

    # persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(pd, f, indent=2)
    print(f"[Save] Created gearset slot {slot_idx} in {save_path}")

    # echo back so the client will show the "Enter name" popup
    session.conn.sendall(raw_data)

def handle_name_gearset(session, raw_data):
    """
    Packet 0xC8: client sends the chosen name for a gear-set.
    Payload is (slot_idx:3 bits, name:String with 16-bit length).
    """
    payload = raw_data[4:]
    print(f"[Debug] Payload: {payload.hex()}")
    br = BitReader(payload)
    slot_idx = br.read_method_20(3)
    print(f"[Debug] slot_idx: {slot_idx}, bit_index: {br.bit_index}")
    length = br.read_method_20(16)
    print(f"[Debug] String length: {length}")
    if length > br.remaining_bits() // 8:
        print(f"[Error] Invalid string length: {length}, remaining bytes: {br.remaining_bits() // 8}")
        return
    result_bytes = bytearray()
    for _ in range(length):
        result_bytes.append(br.read_method_20(8))
    try:
        name = result_bytes.decode('utf-8')
    except UnicodeDecodeError:
        name = result_bytes.decode('latin1')
    print(f"[GearSet] Naming slot #{slot_idx} → {name} for {session.current_character}")

    # Update in-memory save
    pd = session.player_data
    chars = pd.get("characters", [])
    for char in chars:
        if char.get("name") != session.current_character:
            continue
        gs = char.setdefault("gearSets", [])
        if slot_idx < len(gs):
            gs[slot_idx]["name"] = name
        else:
            print(f"[Error] Gearset slot {slot_idx} does not exist")
            return
        break
    else:
        print(f"[WARNING] Character not found for name_gearset")
        return

    # Persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(pd, f, indent=2)
    print(f"[Save] Renamed gearset slot {slot_idx} to “{name}” in {save_path}")

    # Echo back to client
    session.conn.sendall(raw_data)

def handle_apply_gearset(session, raw_data):
    """
    Packet 0xC6: client assigns currently equipped gears to a gearset slot.
    Payload is a single uint: the gearset slot index (3 bits).
    """
    payload = raw_data[4:]
    br = BitReader(payload)
    slot_idx = br.read_method_20(GearType.const_348)
    print(f"[GearSet] Assigning equipped gears to gearset #{slot_idx} for {session.current_character}")

    # Update in-memory save
    pd = session.player_data
    chars = pd.get("characters", [])
    for char in chars:
        if char.get("name") != session.current_character:
            continue
        gs = char.get("gearSets", [])
        if slot_idx >= len(gs):
            print(f"[Error] Gearset slot {slot_idx} does not exist")
            return
        eq = char.get("equippedGears", [])
        if len(eq) != EntType.MAX_SLOTS - 1:
            print(f"[Warning] equippedGears has {len(eq)} slots, expected {EntType.MAX_SLOTS - 1}")
            return
        # Copy gear IDs from equippedGears to gearSets[slot_idx]["slots"]
        gear_ids = [item.get("gearID", 0) for item in eq]
        gs[slot_idx]["slots"] = gear_ids
        print(f"[Debug] Assigned gear IDs to gearset #{slot_idx}: {gear_ids}")
        break
    else:
        print(f"[WARNING] Character not found for apply_gearset")
        return

    # Persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(pd, f, indent=2)
    print(f"[Save] Assigned equipped gears to gearset slot {slot_idx} in {save_path}")

    # Echo back to client
    session.conn.sendall(raw_data)

def handle_update_equipment(session, raw_data):
    """
    Packet 0x30: client updates equipped gears for a gearset.
    Payload is (entity_id, followed by 6 slots: 1-bit changed flag, optional gear_id).
    """
    payload = raw_data[4:]
    print(f"[Debug] Payload: {payload.hex()}")
    br = BitReader(payload)
    entity_id = br.read_method_4()
    print(f"[Equipment] Updating for entity={entity_id}, character={session.current_character}")

    # Update in-memory save
    pd = session.player_data
    chars = pd.get("characters", [])
    for char in chars:
        if char.get("name") != session.current_character:
            continue
        eq = char.setdefault("equippedGears", [])
        inv = char.setdefault("inventoryGears", [])
        # Ensure equippedGears has 6 slots
        while len(eq) < EntType.MAX_SLOTS - 1:
            eq.append({"gearID": 0, "tier": 0, "runes": [0, 0, 0], "colors": [0, 0]})
        if len(eq) > EntType.MAX_SLOTS - 1:
            eq[:] = eq[:EntType.MAX_SLOTS - 1]
        # Process 6 slots
        updates = {}
        for slot in range(EntType.MAX_SLOTS - 1):
            if br.remaining_bits() < 1:
                print(f"[Error] Not enough bits to read slot {slot} changed flag")
                return
            changed = br.read_method_20(1)
            if changed:
                if br.remaining_bits() < GearType.GEARTYPE_BITSTOSEND:
                    print(f"[Error] Not enough bits to read gear ID for slot {slot}")
                    return
                gear_id = br.read_method_6(GearType.GEARTYPE_BITSTOSEND)
                updates[slot] = gear_id
        # Apply updates
        for slot, gear_id in updates.items():
            for item in inv:
                if item.get("gearID") == gear_id:
                    eq[slot] = item.copy()
                    break
            else:
                print(f"[Warning] Gear ID {gear_id} not found in inventory for slot {slot}")
                eq[slot] = {"gearID": 0, "tier": 0, "runes": [0, 0, 0], "colors": [0, 0]}
        print(f"[Equipment] Updated slots: {updates}")
        break
    else:
        print(f"[WARNING] Character not found for update_equipment")
        return

    # Persist
    save_path = SAVE_PATH_TEMPLATE.format(user_id=session.user_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(pd, f, indent=2)
    print(f"[Save] Updated equippedGears for {session.current_character} in {save_path}")

    # Echo back to client
    session.conn.sendall(raw_data)

def handle_private_message(session, data, all_sessions):
    payload = data[4:]
    try:
        br = BitReader(payload)
        recipient_name = br.read_method_13()
        message = br.read_method_13()
        print(f"[{session.addr}] [PKT46] Private message from {session.current_character} to {recipient_name}: {message}")

        # Find recipient session
        recipient_session = next(
            (s for s in all_sessions
             if s.current_character
             and s.current_character.lower() == recipient_name.lower()
             and s.authenticated),
            None
        )

        # For recipient (0x47): senderName + message
        bb_recipient = BitBuffer()
        bb_recipient.write_method_13(session.current_character)  # Sender's name
        bb_recipient.write_method_13(message)
        payload_out_recipient = bb_recipient.to_bytes()
        pkt_recipient = struct.pack(">HH", 0x47, len(payload_out_recipient)) + payload_out_recipient

        # For sender (0x48): recipientName + message
        bb_sender = BitBuffer()
        bb_sender.write_method_13(recipient_name)  # Recipient's name
        bb_sender.write_method_13(message)
        payload_out_sender = bb_sender.to_bytes()
        pkt_sender = struct.pack(">HH", 0x48, len(payload_out_sender)) + payload_out_sender

        if recipient_session:
            # Send to recipient
            recipient_session.conn.sendall(pkt_recipient)
            print(
                f"[{session.addr}] [PKT47] Sent private message to {recipient_session.addr} ({recipient_session.current_character})")

            # Send confirmation to sender
            session.conn.sendall(pkt_sender)
            print(
                f"[{session.addr}] [PKT48] Sent private message confirmation to sender {session.addr} ({session.current_character})")

        else:
            print(f"[{session.addr}] [PKT46] Recipient {recipient_name} not found")
            err = f"Player {recipient_name} not found".encode("utf-8")
            pl = struct.pack(">H", len(err)) + err
            session.conn.sendall(struct.pack(">HH", 0x44, len(pl)) + pl)

    except Exception as e:
        print(f"[{session.addr}] [PKT46] Parse error: {e}, raw payload = {payload.hex()}")

def Client_Crash_Reports(session, data):
    """
    Read a CLIENT ERROR (0x7C) packet and log it.
    No response is sent back.
    """
    # unpack the two‐byte packet ID and two‐byte length
    _, length = struct.unpack_from(">HH", data, 0)
    # extract exactly `length` bytes of payload
    payload = data[4:4 + length]
    try:
        msg = payload.decode("utf-8", errors="replace")
    except Exception:
        msg = repr(payload)
    print(f"[{session.addr}] CLIENT ERROR (0x7C): {msg}")


def handle_hp_increase_notice(session, data):
       pass

def handle_char_regen(session, data):
      pass

def handle_volume_enter(session, data):
     pass

def handle_change_offset_y(session, data):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        ent_id = br.read_method_9()
        offset_y = br.read_method_706()

        print(f"[PKT125] ent_id={ent_id}, offset_y={offset_y}")

        entity = session.get_entity(ent_id)
        if entity:
            entity.target_offset_y = offset_y
        else:
            print(f"[PKT125] Unknown entity ID: {ent_id}")

    except Exception as e:
        print(f"[{session.addr}] [PKT125] Error parsing packet: {e}")

#handled
#############################################

def handle_apply_dyes(session, payload, all_sessions):
    br = BitReader(payload)
    try:
        entity_id = br.read_method_4()
        dyes_by_slot = {}
        for slot in range(1, EntType.MAX_SLOTS):
            if br.read_method_20(1):
                d1 = br.read_method_20(DyeType.BITS)
                d2 = br.read_method_20(DyeType.BITS)
                dyes_by_slot[slot - 1] = (d1, d2)

        pay_with_idols = bool(br.read_method_20(1))

        primary_dye = br.read_method_20(DyeType.BITS) if br.read_method_20(1) else None
        secondary_dye = br.read_method_20(DyeType.BITS) if br.read_method_20(1) else None
    except Exception as e:
        print(f"[Dyes] ERROR parsing dye packet: {e}")
        return

    print(f"[Dyes] entity={entity_id}, dyes_by_slot={dyes_by_slot}, "
          f"pay_with_idols={pay_with_idols}, shirt={primary_dye}, pants={secondary_dye}")

    # ─── Work directly with the current character ───
    char = session.current_char_dict
    if not char:
        print(f"[Dyes] ERROR: current_char_dict is None for {session.addr}")
        return

    eq = char.setdefault("equippedGears", [])
    inv = char.setdefault("inventoryGears", [])

    # Cost tables
    level = int(char.get("level", char.get("mExpLevel", 1)) or 1)
    g_idx = min(max(level, 0), len(Entity.Dye_Gold_Cost) - 1)
    i_idx = min(max(level, 0), len(Entity.Dye_Idols_Cost) - 1)
    per_gold = Entity.Dye_Gold_Cost[g_idx]
    per_idol = Entity.Dye_Idols_Cost[i_idx]

    # Detect gear dye changes
    current_dyes_by_slot = {idx: tuple(gear.get("colors", [0, 0])) for idx, gear in enumerate(eq)}

    slots_changed = 0
    individual_dyes_changed = 0
    for slot, (new_d1, new_d2) in dyes_by_slot.items():
        if slot >= len(eq):
            continue
        gear = eq[slot]
        if not gear or gear.get("gearID", 0) == 0:
            continue
        old_d1, old_d2 = current_dyes_by_slot.get(slot, (0, 0))
        changed = 0
        if new_d1 != old_d1:
            individual_dyes_changed += 1
            changed = 1
        if new_d2 != old_d2:
            individual_dyes_changed += 1
            changed = 1
        slots_changed += changed

    charge_units = individual_dyes_changed
    gold_cost = per_gold * charge_units
    idol_cost = per_idol * charge_units

    print(f"[Dyes] Level={level}, per-dye={per_gold}g/{per_idol}i  units={charge_units}  "
          f"total_gold={gold_cost}  total_idols={idol_cost}")
    print(f"[Dyes] Bal before: gold={char.get('gold',0)} idols={char.get('mammothIdols',0)}")

    # --- Shirt/pants are always free ---
    shirt_changed = False
    pants_changed = False
    if primary_dye is not None:
        c = get_dye_color(primary_dye)
        if c is not None and c != char.get("shirtColor"):
            char["shirtColor"] = c
            shirt_changed = True
    if secondary_dye is not None:
        c = get_dye_color(secondary_dye)
        if c is not None and c != char.get("pantColor"):
            char["pantColor"] = c
            pants_changed = True

    # No changes at all?
    if charge_units == 0 and not shirt_changed and not pants_changed:
        print("[Dyes] No changes detected — nothing to charge")
        send_dye_sync_packet(session, entity_id, dyes_by_slot,
                             char.get("shirtColor"), char.get("pantColor"))
        return

    # Charge if needed
    if charge_units > 0:
        if pay_with_idols:
            if char.get("mammothIdols", 0) < idol_cost:
                print(f"[Dyes] ERROR: Not enough idols")
                return
            char["mammothIdols"] -= idol_cost
            print(f"[Dyes] Charged {idol_cost} idols")
            send_premium_purchase(session, "Dye", idol_cost)
        else:
            if char.get("gold", 0) < gold_cost:
                print(f"[Dyes] ERROR: Not enough gold")
                return
            char["gold"] -= gold_cost
            print(f"[Dyes] Charged {gold_cost} gold")

    # Apply dyes to equipment
    for slot, (d1, d2) in dyes_by_slot.items():
        if slot < len(eq):
            eq_slot = eq[slot]
            if not eq_slot or eq_slot.get("gearID", 0) == 0:
                continue
            eq_slot["colors"] = [d1, d2]
            gear_id = eq_slot.get("gearID")
            for g in inv:
                if g.get("gearID") == gear_id:
                    g["colors"] = [d1, d2]
                    break
            else:
                inv.append(eq_slot.copy())

    # Persist
    save_characters(session.user_id, session.char_list)
    session.player_data["characters"] = session.char_list

    print(f"[Save] Dyes saved. New balances: gold={char.get('gold',0)} idols={char.get('mammothIdols',0)}")

    # Sync to self + broadcast
    for target in [session] + [
        o for o in all_sessions
        if o is not session and o.world_loaded and o.current_level == session.current_level
    ]:
        send_dye_sync_packet(
            target,
            entity_id,
            dyes_by_slot,
            char.get("shirtColor"),
            char.get("pantColor"),
        )

def send_dye_sync_packet(session, entity_id, dyes_by_slot, shirt_color=None, pant_color=None):
        bb = BitBuffer()
        bb.write_method_4(entity_id)

        eq = []
        for char in session.player_data.get("characters", []):
            if char.get("name") == session.current_character:
                eq = char.get("equippedGears", [])
                break

        for slot in range(1, EntType.MAX_SLOTS):
            gear = eq[slot - 1] if slot - 1 < len(eq) else None
            if gear and "colors" in gear:
                d1, d2 = gear["colors"]
                bb.write_method_6(1, 1)  # has dye pair
                bb.write_method_6(d1, DyeType.BITS)
                bb.write_method_6(d2, DyeType.BITS)
            else:
                bb.write_method_6(0, 1)  # no dye pair

        # Write shirt color
        if shirt_color is not None:
            bb.write_method_6(1, 1)
            bb.write_method_6(shirt_color, EntType.CHAR_COLOR_BITSTOSEND)
        else:
            bb.write_method_6(0, 1)

        # Write pant color
        if pant_color is not None:
            bb.write_method_6(1, 1)
            bb.write_method_6(pant_color, EntType.CHAR_COLOR_BITSTOSEND)
        else:
            bb.write_method_6(0, 1)

        payload = bb.to_bytes()
        pkt = struct.pack(">HH", 0x111, len(payload)) + payload
        session.conn.sendall(pkt)
        print(f"[Sync] Sent dye update (0x111) to client for entity {entity_id}")

def PaperDoll_Request(session, data, conn):
    """
    Handles paperdoll request (0x19). Reads character name,
    finds the character in session.char_list, and sends back
    a 0x1A response with their paperdoll or empty if not found.
    """
    name = BitReader(data[4:]).read_method_26()
    #print(f"[{session.addr}] [PKT0x19] Request for paperdoll: {name}")

    for c in session.char_list:
        if c["name"] == name:
            pd = build_paperdoll_packet(c)
            conn.sendall(struct.pack(">HH", 0x1A, len(pd)) + pd)
            #print(f"[{session.addr}] [PKT0x19] Found and sent paperdoll for '{name}'")
            break
    else:
        # Character not found, send empty packet
        conn.sendall(struct.pack(">HH", 0x1A, 0))
        #print(f"[{session.addr}] [PKT0x19] Character '{name}' not found. Sent empty paperdoll.")

def handle_pet_info_packet(session, data, all_sessions):
    """
    Handle packet type 0xB3 (SendPetInfoToServer).
    Updates the active pet (equippedPetID) and the restingPets list in the save file.
    """
    payload = data[4:]
    reader = BitReader(payload, debug=True)

    try:
        pets = []
        for _ in range(4):  # 1 active + 3 resting
            pet_type_id = reader.read_method_6(7)  # 7-bit pet type ID
            value = reader.read_method_4()         # Variable-length value
            pets.append((pet_type_id, value))

        active_pet_type, active_pet_value = pets[0]
        resting_pets_data = [
            {"typeID": pets[1][0]},
            {"typeID": pets[2][0]},
            {"typeID": pets[3][0]}
        ]

        # Log for debug
        print(f"[{session.addr}] [PKT0xB3] Active pet: type={active_pet_type}, value={active_pet_value}")
        for i, pet in enumerate(resting_pets_data, 1):
            print(f"[{session.addr}] [PKT0xB3] Resting pet {i}: type={pet['typeID']}, value={pets[i][1]}")

        # --- Update save file ---
        for char in session.char_list:
            if char.get("name") != session.current_character:
                continue

            # Update equippedPetID
            char["equippedPetID"] = active_pet_type

            # Update restingPets list
            char["restingPets"] = resting_pets_data

            # Persist changes
            save_characters(session.user_id, session.char_list)
            print(f"[Save] Updated pets for {session.current_character} → activePetID={active_pet_type}, resting={resting_pets_data}")
            break
        else:
            print(f"[{session.addr}] [PKT0xB3] ERROR: character {session.current_character} not found")

    except Exception as e:
        print(f"[{session.addr}] [PKT0xB3] Error parsing packet: {e}")
        for line in reader.get_debug_log():
            print(line)

def handle_mount_equip_packet(session, data, all_sessions):
    """
    Handle packet type 0xB2 for equipping a mount on an entity.
    Parses the payload to extract Entity ID and Mount ID, prints them,
    and updates the character's equipped mount.
    """

    payload = data[4:]
    reader = BitReader(payload, debug=True)

    try:
        # Read Entity ID (method_4)
        entity_id = reader.read_method_4()
        # Read Mount ID (7 bits, as per class_20.const_297)
        mount_id = reader.read_method_6(7)

        print(f"[{session.addr}] [PKT0xB2] Entity ID: {entity_id}, Mount ID: {mount_id}")

        # Validate and update character's equipped mount
        for char in session.char_list:
            if char.get("name") == session.current_character:
                # Check if the mount is owned
                owned_mounts = char.get("mounts", [])
                if mount_id not in owned_mounts and mount_id != 0:  # 0 might mean unequip
                    print(f"[{session.addr}] [PKT0xB2] Invalid mount ID {mount_id} for {session.current_character}")
                    return
                # Update equipped mount
                char["equippedMount"] = mount_id
                session.player_data["characters"] = session.char_list
                save_characters(session.user_id, session.char_list)
                print(f"[{session.addr}] [PKT0xB2] Equipped mount ID {mount_id} for {session.current_character}")
                break
        else:
            print(f"[{session.addr}] [WARNING] Character {session.current_character} not found for PKT0xB2")

        # Broadcast to other sessions (optional, based on game design)
        for other in all_sessions:
            if other is not session and other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(data)
                print(f"[{session.addr}] [PKT0xB2] Broadcasted mount update to {other.addr}")

    except Exception as e:
        print(f"[{session.addr}] [PKT0xB2] Error parsing packet: {e}")
        for line in reader.get_debug_log():
            print(line)


def handle_emote_begin(session, data, all_sessions):
    """
    Packet 0x7E: an entity starts an emote.
    Client sends:
      method_9(entityID) -> var-int via write_method_4
      method_26(emoteString)
    Other clients read:
      method_4() for ID, method_13() for the string.
    """



    # 1) Parse the emote packet
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        entity_id = br.read_method_4()
        emote     = br.read_method_13()
    except Exception as e:
        print(f"[{session.addr}] [PKT7E] Parse error: {e}, raw={payload.hex()}")
        return

    print(f"[{session.addr}] [PKT7E] Entity {entity_id} began emote \"{emote}\"")

    # 2) Broadcast unchanged packet to all other clients in the same level
    for other in all_sessions:
        if (other is not session
            and other.world_loaded
            and other.current_level == session.current_level):
            try:
                other.conn.sendall(data)
            except Exception as e:
                print(f"[{session.addr}] [PKT7E] Error forwarding to {other.addr}: {e}")




def handle_group_invite(session, data, all_sessions):
    """
    Packet 0x65: /invite <player>
    Only the invitee gets the 0x58 invite packet.
    No confirmation packet is sent back to the inviter.
    """


    # 1) Parse invitee name
    payload = data[4:]
    try:
        br = BitReader(payload, debug=False)
        invitee_name = br.read_method_13()
    except Exception as e:
        print(f"[{session.addr}] [PKT65] Parse error: {e}, raw={payload.hex()}")
        return

    print(f"[{session.addr}] [PKT65] Group invite from {session.current_character} to {invitee_name}")


    # 2) Find the invitee’s session
    invitee = next((
        s for s in all_sessions
        if s.authenticated
           and s.current_character
           and s.current_character.lower() == invitee_name.lower()
    ), None)

    if not invitee:
        _send_error(session.conn, f"Player {invitee_name} not found")
        print(f"[{session.addr}] [PKT65] Invitee {invitee_name} not found")
        return

    # 3) Ensure inviter has a group_id
    if not getattr(session, 'group_id', None):
        session.group_id = secrets.randbits(16)
        session.group_members = [session]
        print(f"[{session.addr}] [PKT65] Created group {session.group_id}")

    # 4) Reject if invitee already in a group
    if getattr(invitee, 'group_id', None):
        _send_error(session.conn, f"{invitee_name} is already in a group")
        print(f"[{session.addr}] [PKT65] {invitee_name} already in group {invitee.group_id}")
        return

    # 5) Send the invite (0x58) to the invitee only
    bb = BitBuffer()
    inviter_id   = session.clientEntID or 0
    inviter_name = session.current_character
    invite_text  = f"{inviter_name} has invited you to join a party"

    bb.write_method_9(inviter_id)
    bb.write_method_26(inviter_name)
    bb.write_method_26(invite_text)
    body = bb.to_bytes()
    invite_packet = struct.pack(">HH", 0x58, len(body)) + body
    invitee.conn.sendall(invite_packet)
    print(f"[{session.addr}] [PKT65] Sent 0x58 invite to {invitee.current_character}")


def handle_public_chat(session, data, all_sessions):
    """
    Packet 0x2C: global (level-wide) chat.
    Client sends: method_9(entity_id), method_26(message)
    Server rebroadcasts same format.
    """


    # 1) Parse incoming packet
    payload = data[4:]
    try:
        br = BitReader(payload, debug=False)
        entity_id = br.read_method_9()    # client used method_9
        message   = br.read_method_13()   # readMethod13 pairs with writer method_26

    except Exception as e:
        print(f"[{session.addr}] [PKT2C] Error parsing chat: {e}, raw={payload.hex()}")
        return

    print(f"[{session.addr}] [PKT2C] Chat from {entity_id} ({session.current_character}): {message}")

    # 2) Build the rebroadcast packet
    bb = BitBuffer()
    bb.write_method_9(entity_id)
    bb.write_method_26(message)
    body = bb.to_bytes()
    header = struct.pack(">HH", 0x2C, len(body))
    packet = header + body

    # 3) Send to everyone else in the same level
    for other in all_sessions:
        if other is session:
            continue
        if not other.world_loaded or other.current_level != session.current_level:
            continue
        try:
            other.conn.sendall(packet)
            print(f"[{session.addr}] [PKT2C] → \"{message}\" to {other.addr} ({other.current_character})")
        except Exception as e:
            print(f"[{session.addr}] [PKT2C] Error sending to {other.addr}: {e}")

def handle_power_cast(session, data, all_sessions):


    payload = data[4:]
    br = BitReader(payload, debug=False)

    try:
        ent_id   = br.read_method_9()
        power_id = br.read_method_9()

        # ← CORRECTED TARGET‐POINT HANDSHAKE
        _ = br.read_method_15()                        # discard hasTargetEntity
        has_target_pos = bool(br.read_method_15())     # var_2846: does this power type support coords?
        target_pt = None
        if has_target_pos:
            target_x = br.read_method_24()
            target_y = br.read_method_24()
            target_pt = (target_x, target_y)

        # projectile
        has_proj = bool(br.read_method_15())
        proj_id  = br.read_method_9() if has_proj else None

        # charged flag
        is_charged = bool(br.read_method_15())

        # melee‐combo / var_674 branch
        has_extra = bool(br.read_method_15())
        secondary_id = tertiary_id = None
        if has_extra:
            is_secondary = bool(br.read_method_15())
            if is_secondary:
                secondary_id = br.read_method_9()
            else:
                tertiary_id = br.read_method_9()

        # cooldown & mana
        has_flags = bool(br.read_method_15())
        cooldown_tick = mana_cost = None
        if has_flags:
            if bool(br.read_method_15()):
                cooldown_tick = br.read_method_9()
            if bool(br.read_method_15()):
                MANA_BITS = PowerType.const_423
                mana_cost = br.read_method_6(MANA_BITS)

        props = {
            #'caster_ent_id': ent_id,
            'power_id':      power_id,
            #'target_pt':     target_pt,
            #'projectile_id': proj_id,
            #'is_charged':    is_charged,
            #'secondary_id':  secondary_id,
            #'tertiary_id':   tertiary_id,
            #'cooldown_tick': cooldown_tick,
            #'mana_cost':     mana_cost,
        }
        #print(f"[{session.addr}] [PKT09] Parsed power-cast:")
        #pprint.pprint(props, indent=4)

        # broadcast to peers
        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)

    except Exception as e:
        print(f"[{session.addr}] [PKT09] Error parsing power-cast: {e}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)

def handle_linkupdater(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        client_time = br.read_method_24()
        is_desync   = bool(br.read_method_15())
        server_time = br.read_method_24()

        # Update our session’s clock‐sync info
        session.client_elapsed  = client_time
        session.server_elapsed  = server_time
        session.clock_desynced  = is_desync
        session.clock_offset_ms = server_time - client_time

        #print(f"[{session.addr}] [PKTA2] Sync: client={client_time}ms "
        #      f"server={server_time}ms desync={is_desync} offset={session.clock_offset_ms}ms")

        #TODO...
        # If the client thinks we’re badly out of sync, we can reply here
        # response = build_clock_correction_packet(...)
        # session.conn.sendall(response)

    except Exception as e:
        print(f"[{session.addr}] [PKTA2] Error parsing link-sync: {e}")

def handle_entity_incremental_update(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload)

    try:
        entity_id = br.read_method_4()
        is_self = (entity_id == session.clientEntID)
        if not is_self and entity_id not in session.entities:
            print(f"[{session.addr}] [PKT07] Unknown entity {entity_id} movement dropped")
            return

        delta_x = br.read_method_45()
        delta_y = br.read_method_45()
        delta_vx = br.read_method_45()

        STATE_BITS = Entity.const_316
        ent_state = br.read_method_6(STATE_BITS)
        flags = {
            'b_left':      bool(br.read_method_15()),
            'b_running':   bool(br.read_method_15()),
            'b_jumping':   bool(br.read_method_15()),
            'b_dropping':  bool(br.read_method_15()),
            'b_backpedal': bool(br.read_method_15()),
        }
        is_airborne = bool(br.read_method_15())
        velocity_y = br.read_method_24() if is_airborne else 0
        ent = session.entities.get(entity_id, {})
        old_x = ent.get('pos_x', 0)
        old_y = ent.get('pos_y', 0)
        new_x = old_x + delta_x
        new_y = old_y + delta_y
        ent.update({
            'pos_x': new_x,
            'pos_y': new_y,
            'velocity_x': ent.get('velocity_x', 0) + delta_vx,
            'velocity_y': velocity_y,
            'ent_state': ent_state,
            **flags
        })
        session.entities[entity_id] = ent

        if is_self:
            players = level_players.setdefault(session.current_level, [])
            players[:] = [p for p in players if p["id"] != entity_id]
            players.append({"id": entity_id, "pos_x": new_x, "pos_y": new_y, "session": session})

        if ent.get('is_player'):
            for char in session.char_list:
                if char['name'] == session.current_character:
                    char['CurrentLevel'] = {
                        'name': session.current_level,
                        'x': new_x,
                        'y': new_y
                    }
                    break

        for other in all_sessions:
            if other is not session and other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(data)
    except Exception as e:
        print(f"[{session.addr}] [PKT07] Error parsing packet: {e}")
        for line in br.get_debug_log():
            print(line)

def handle_start_skit(session, data, all_sessions):
    """
    Handle packet 0xC5: Client requests to start or stop a skit for an entity.
    - Reads entity ID, boolean flag, and text.
    - Sends PKT_ROOM_THOUGHT (0x76) only if flag is True.
    """
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        entity_id = br.read_method_9()
        flag = bool(br.read_method_15())
        text = br.read_method_26()
    except Exception as e:
        print(f"[{session.addr}] [PKT0xC5] Error parsing packet: {e}")
        return

    if flag:
        bb = BitBuffer()
        bb.write_method_4(entity_id)
        bb.write_method_13(text)
        payload = bb.to_bytes()
        packet = struct.pack(">HH", 0x76, len(payload)) + payload

        for other_session in all_sessions:
            if other_session.world_loaded and other_session.current_level == session.current_level:
                other_session.conn.sendall(packet)

        print(f"[{session.addr}] [PKT0xC5] Sent skit message from entity {entity_id}: '{text}'")
    else:
        print(f"[{session.addr}] [PKT0xC5] Skit flag is False for entity {entity_id}, message suppressed")


