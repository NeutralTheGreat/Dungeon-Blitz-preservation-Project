import json, struct
import random
import time

from Character import save_characters, build_paperdoll_packet, get_inventory_gears, \
    build_level_gears_packet, SAVE_PATH_TEMPLATE
from bitreader import BitReader
from constants import GearType, EntType, class_64, class_1, DyeType, Entity, class_3, Game
from BitBuffer import BitBuffer
from constants import get_dye_color
from globals import build_start_skit_packet, send_premium_purchase
from missions import get_mission_extra


#TODO...
def handle_queue_potion(session, data):
    br = BitReader(data[4:])
    queued_potion_id = br.read_method_20(class_3.const_69)
    #print(f"queued potion ID : {queued_potion_id}")

#TODO...
def handle_alert_state_update(session, data):
    br = BitReader(data[4:])
    state_id = br.read_method_20(Game.const_646)
    #print(f"state_id : {state_id}")

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
def handle_talk_to_npc(session, data):

    br = BitReader(data[4:])
    npc_id = br.read_method_9()

    npc = session.entities.get(npc_id)
    if not npc:
        print(f"[{session.addr}] [PKT0x7A] Unknown NPC ID {npc_id}")
        return

    # NPC internal type name:
    # This is the ONLY correct name to compare missions with.
    ent_type = npc.get("Linked_Mission") or npc.get("entType") or npc.get("name")

    # Normalize
    def norm(x):
        return (x or "").replace(" ", "").replace("_", "").lower()

    npc_type_norm = norm(ent_type)

    # Default values
    dialogue_id = 0
    mission_id = 0

    # Player mission data
    char_data = session.current_char_dict or {}
    player_missions = char_data.get("missions", {})

    # Check mission matches
    for mid_str, mdata in player_missions.items():
        try:
            mid = int(mid_str)
        except:
            continue

        mextra = get_mission_extra(mid)
        if not mextra:
            continue

        # Mission-side names
        contact = norm(mextra.get("ContactName"))
        ret     = norm(mextra.get("ReturnName"))

        # Normalize them BEFORE matching (auto-map via Linked_Mission)
        if contact and contact != npc_type_norm:
            # Allow Linked_Mission to solve mismatches
            if norm(mextra.get("ContactName")) == norm(npc.get("Linked_Mission")):
                contact = npc_type_norm
        if ret and ret != npc_type_norm:
            if norm(mextra.get("ReturnName")) == norm(npc.get("Linked_Mission")):
                ret = npc_type_norm

        # Mission state
        state = mdata.get("state", 0)  # 0=not accepted, 1=active, 2=completed

        # Match: Offering the mission
        if npc_type_norm == contact:
            if state == 0:
                dialogue_id = 2  # OfferText
                mission_id = 0
                break
            elif state == 1:
                dialogue_id = 3  # ActiveText
                mission_id = mid
                break
            elif state == 2:
                dialogue_id = 5  # PraiseText
                mission_id = mid
                break

        # Returning the mission
        if npc_type_norm == ret:
            if state == 1:
                dialogue_id = 4  # ReturnText
                mission_id = mid
                break
            elif state == 2:
                dialogue_id = 5  # PraiseText
                mission_id = mid
                break

    pkt = build_start_skit_packet(npc_id, dialogue_id, mission_id)
    session.conn.sendall(pkt)

    print(
        f"[{session.addr}] [PKT0x7A] TalkToNPC id={npc_id} entType={ent_type} → "
        f"dialogue_id={dialogue_id}, mission_id={mission_id}"
    )

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

def handle_lockbox_reward(session, data):
    _=data[4:]
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
            other.player_spawned and
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


def handle_hp_increase_notice(session, data):
       pass

def handle_char_regen(session, data):
      pass

def handle_volume_enter(session, data):
     pass


#handled
#############################################

def handle_apply_dyes(session, data, all_sessions):
    br = BitReader(data[4:])
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
        if o is not session and o.player_spawned and o.current_level == session.current_level
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


#TODO...
def handle_linkupdater(session, data):
    return  # return here no point doing anything here for now at least

    br = BitReader(data[4:])

    client_elapsed = br.read_method_24()
    client_desync  = br.read_method_15()
    server_echo    = br.read_method_24()

    now_ms = int(time.time() * 1000)

    # First update → establish baseline
    if not hasattr(session, "clock_base"):
        session.clock_base = now_ms
        session.clock_offset_ms = 0
        session.last_desync_time = None

    session.client_elapsed = client_elapsed
    session.server_elapsed = server_echo

    # Compute offset (server_time - expected_client_time)
    session.clock_offset_ms = now_ms - (session.clock_base + client_elapsed)
    offset = abs(session.clock_offset_ms)

    DESYNC_THRESHOLD = 2500     # ms allowed before warning
    DESYNC_KICK_TIME = 2.0      # seconds of continuous desync before kick

    if offset > DESYNC_THRESHOLD or client_desync:
        # First time detecting desync
        if session.last_desync_time is None:
            session.last_desync_time = time.time()
            print(f"[{session.addr}] Desync detected offset={offset}ms (timer started)")
        else:
            elapsed = time.time() - session.last_desync_time
            if elapsed >= DESYNC_KICK_TIME:
                print(f"[{session.addr}] Kicking player for severe desync (offset={offset}ms)")
                session.conn.close()
                session.stop()
                return

    props = {
        "client_elapsed": client_elapsed,
        "client_desync": client_desync,
        "server_echo": server_echo,
        "clock_base": getattr(session, "clock_base", None),
        "server_now_ms": now_ms,
        "client_offset_ms": session.clock_offset_ms,
    }

    #print(f"Player [{get_active_character_name(session)}]")
    #pprint.pprint(props, indent=4)


