import struct

from BitBuffer import BitBuffer
from accounts import save_characters
from bitreader import BitReader
from constants import Entity, PowerType, GearType, class_64, class_1, EntType, class_21, Game
from globals import send_consumable_update, build_change_offset_y_packet, GS


                # Helpers
    #####################################

def get_base_hp_for_level(level):
    if level < 1:
        level = 1
    if level >= len(Entity.PLAYER_HITPOINTS):
        level = len(Entity.PLAYER_HITPOINTS) - 1
    return Entity.PLAYER_HITPOINTS[level]

def write_enttype_gear(bb, gear):
    """
    gear dict format:
    {
        gearID, tier,
        rune1, rune2, rune3,
        color1, color2
    }
    """
    bb.write_method_6(gear["gearID"], GearType.GEARTYPE_BITSTOSEND)
    bb.write_method_6(gear["tier"], GearType.const_176)

    bb.write_method_6(gear.get("rune1", 0), class_64.const_101)
    bb.write_method_6(gear.get("rune2", 0), class_64.const_101)
    bb.write_method_6(gear.get("rune3", 0), class_64.const_101)

    bb.write_method_6(gear.get("color1", 0), class_21.const_50)
    bb.write_method_6(gear.get("color2", 0), class_21.const_50)

def build_gear_change_packet(entity_id: int, equipped_gears: list[dict]) -> bytes:
    """
    equipped gears = list of 6 gear dicts (slots 1–6)
    """
    bb = BitBuffer()
    bb.write_method_4(entity_id)

    # Slots 1..6 (skip slot 0)
    for slot in range(6):
        gear = equipped_gears[slot] if slot < len(equipped_gears) else None

        if gear and gear.get("gearID", 0) > 0:
            bb.write_method_15(True)  # slot exists
            bb.write_method_15(True)  # gear exists
            write_enttype_gear(bb, gear)
        else:
            bb.write_method_15(True)  # slot exists
            bb.write_method_15(False)  # empty slot → client builds No<Class><Slot>

    payload = bb.to_bytes()
    return struct.pack(">HH", 0xAF, len(payload)) + payload

def broadcast_gear_change(session, all_sessions):
    char = session.current_char_dict
    if not char:
        return

    entity_id = session.clientEntID
    equipped = char.get("equippedGears", [])

    pkt = build_gear_change_packet(entity_id, equipped)

    for other in all_sessions:
        if (
                other is not session
                and other.player_spawned
                and other.current_level == session.current_level
        ):
            other.conn.sendall(pkt)

def apply_and_broadcast_hp_delta(
    *,
    source_session,
    ent_id: int,
    delta: int,
    all_sessions,
    source_name: str,
):
    ent = source_session.entities.get(ent_id)
    ent["hp"] = max(0, ent.get("hp", 0) + delta)

    bb = BitBuffer()
    bb.write_method_4(ent_id)
    bb.write_method_45(delta)

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x3A, len(payload)) + payload

    for other in all_sessions:
        if (
            other is not source_session
            and other.player_spawned
            and other.current_level == source_session.current_level
        ):
            other.conn.sendall(pkt)


        # game client function handlers
       #####################################

def handle_entity_destroy(session, data):
    br = BitReader(data[4:])
    entity_id = br.read_method_9()

    # Remove the entity from this session's view
    session.entities.pop(entity_id, None)

    # If this was the client’s own entity, clear reference
    if session.clientEntID == entity_id:
        session.clientEntID = None

    # Broadcast unchanged packet to other players in same level
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_buff_tick_dot(session, data):
    br = BitReader(data[4:])
    target_id = br.read_method_9()
    source_id = br.read_method_9()
    power_type_id = br.read_method_9()
    amount = br.read_method_24()

    # Broadcast unchanged packet to other players in same level
    for other in GS.all_sessions:
        if (
                other is not session
                and other.player_spawned
                and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_respawn_broadcast(session, data):
    br = BitReader(data[4:])

    ent_id = br.read_method_9()
    heal_amount = br.read_method_24()
    used_potion = br.read_method_15()
    ent = session.entities.get(ent_id)

    ent["dead"] = False
    ent["entState"] = 1

    char = next((c for c in session.char_list if c.get("name") == session.current_character), None)
    if char:
        level = char.get("level", 1)
        max_hp = get_base_hp_for_level(level)
    else:
        max_hp = heal_amount

    ent["hp"] = min(heal_amount, max_hp)

    bb = BitBuffer()
    bb.write_method_4(ent_id)
    bb.write_method_45(heal_amount)
    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x82, len(payload)) + payload

    for other in GS.all_sessions:
        if other is not session and other.player_spawned and other.current_level == session.current_level:
            other.conn.sendall(pkt)

def handle_request_respawn(session, data):
    br = BitReader(data[4:])
    use_potion = br.read_method_15()

    if use_potion:
        char = next((c for c in session.char_list
                     if c.get("name") == session.current_character), None)
        if char:
            for itm in char.get("consumables", []):
                if itm.get("consumableID") == 9 and itm.get("count", 0) > 0:
                    itm["count"] -= 1
                    save_characters(session.user_id, session.char_list)
                    send_consumable_update(session.conn, 9, itm["count"])
                    break
    else:
        char = next((c for c in session.char_list
                     if c.get("name") == session.current_character), None)

    # Compute heal amount based on level
    level = char.get("level", 1)
    heal_amount = get_base_hp_for_level(level)

    # Send RespawnComplete
    bb = BitBuffer()
    bb.write_method_24(heal_amount)
    bb.write_method_15(use_potion)
    payload = bb.to_bytes()

    session.conn.sendall(struct.pack(">HH", 0x80, len(payload)) + payload)

def handle_power_hit(session, data):
    br = BitReader(data[4:])
    target_entity_id = br.read_method_9()
    source_entity_id = br.read_method_9()
    damage_value     = br.read_method_24()
    power_type_id    = br.read_method_9()

    # Animation override
    has_animation_override = br.read_method_15()
    animation_override_id = br.read_method_9() if has_animation_override  else None

    # Hit effect override (projectile/effect index)
    has_effect_override = br.read_method_15()
    effect_override_id = br.read_method_9() if has_effect_override else None

    # Critical hit or special-flag
    is_critical = br.read_method_15()

    # Forward packet unchanged to other clients in same level
    for other in GS.all_sessions:
        if (
                other is not session
                and other.player_spawned
                and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_projectile_explode(session, data):
    br = BitReader(data[4:])
    entity_id      = br.read_method_9()
    remote_missile = br.read_method_9()
    coordinate_x   = br.read_method_24()
    coordinate_y   = br.read_method_24()
    is_crit        = br.read_method_15()

    # Broadcast unchanged packet to all other players in same level
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)
# TODO:
#   Buffs are currently not stored or simulated server-side.
#   The client fully handles buff logic, but it STILL depends on the
#   server to send buff removal events.
#
#   For server-spawned entities :
#       - Without server-side buff tracking,
#         buffs applied by players become permanent.
#       - The server must eventually track:
#           • buff start time
#           • buff duration
#           • stack count
#           • modifier nodes (powerNodeTypeID + modValues)
#           • unique sequence IDs
#
#   In the future, server must store these values to correctly
#   handle timed buff removal and expiration logic.
def handle_add_buff(session, data):
    br = BitReader(data[4:])
    entity_id    = br.read_method_9()
    caster_id    = br.read_method_9()
    buff_type_id = br.read_method_9()
    duration     = br.read_method_9()
    stack_count  = br.read_method_9()
    sequence_id  = br.read_method_9()
    has_modifier_nodes = br.read_method_15()

    if has_modifier_nodes:
        node_count = br.read_method_9()

        for _ in range(node_count):
            power_node_type_id = br.read_method_9()
            mod_value_count    = br.read_method_9()

            mod_values = []
            for _ in range(mod_value_count):
                mod_value = br.read_method_560()
                mod_values.append(mod_value)

    # Broadcast unchanged packet to other clients in same level
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

"""
TODO:
    The server does NOT currently track buff timers or stacks.
    For server-spawned entities, buffs never expire unless the
    server sends this packet. In the future, the server must
    store:
        • buff_type_id
        • instance_id
        • duration
        • stack count
        • start time
    so it can send timed buff removals correctly.
"""
def handle_remove_buff(session, data):
    br = BitReader(data[4:])
    entity_id      = br.read_method_9()
    buff_type_id   = br.read_method_9()
    instance_id    = br.read_method_9()

    # Broadcast packet unchanged to other players in the same level
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_change_max_speed(session, data):
    br = BitReader(data[4:])
    entity_id     = br.read_method_9()
    speed_mod_int = br.read_method_9()
    for other in GS.all_sessions:
        if (
            other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)


def handle_power_cast(session, data):
    br = BitReader(data[4:])

    ent_id   = br.read_method_9()
    power_id = br.read_method_9()

    # Skip has-target-entity flag (unused by client)
    has_target_entity = br.read_method_15()

    # Target position if ranged/projectile attacks
    has_target_pos = br.read_method_15()
    if has_target_pos:
        target_x = br.read_method_24()
        target_y = br.read_method_24()

    has_projectile = br.read_method_15()
    if has_projectile:
        projectile_id = br.read_method_9()

    # Charged variant
    is_charged = br.read_method_15()

    # Combo / alternate variant
    has_extra = br.read_method_15()
    if has_extra:
        is_secondary = br.read_method_15()
        if is_secondary:
            secondary_id = br.read_method_9()
        else:
            tertiary_id = br.read_method_9()

    # Cooldown & mana flags
    has_flags = br.read_method_15()
    if has_flags:
        has_cooldown_tick = br.read_method_15()
        if has_cooldown_tick:
            cooldown_tick = br.read_method_9()

        has_mana_cost = br.read_method_15()
        if has_mana_cost:
            MANA_BITS = PowerType.const_423
            mana_cost = br.read_method_6(MANA_BITS)

    # Broadcast unchanged packet
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_change_offset_y(session, data):
    br = BitReader(data[4:])
    entity_id = br.read_method_9()
    offset_y  = br.read_method_739()

    pkt = build_change_offset_y_packet(entity_id, offset_y)

    for s in GS.all_sessions:
        if s is not session and s.player_spawned and s.current_level == session.current_level:
            try:
                s.conn.sendall(pkt)
            except:
                pass


# Sent when equipment, runes, or stats change and HP
def handle_char_regen(session, data):
    br = BitReader(data[4:])
    ent_id = br.read_method_9()
    delta  = br.read_method_24()

    apply_and_broadcast_hp_delta(
        source_session=session,
        ent_id=ent_id,
        delta=delta,
        all_sessions=GS.all_sessions,
        source_name="GEAR/STAT",
    )


# Sent periodically by the client when passive regeneration occurs.
def handle_char_regen_tick(session, data):
    br = BitReader(data[4:])
    ent_id = br.read_method_9()
    delta  = br.read_method_24()

    apply_and_broadcast_hp_delta(
        source_session=session,
        ent_id=ent_id,
        delta=delta,
        all_sessions=GS.all_sessions,
        source_name="REGEN",
    )


def handle_equip_rune(session,  data):
    br = BitReader(data[4:])

    entity_id = br.read_method_4()
    gear_id   = br.read_method_6(GearType.GEARTYPE_BITSTOSEND)
    gear_tier = br.read_method_6(GearType.const_176)
    rune_id   = br.read_method_6(class_64.const_101)
    rune_slot = br.read_method_6(class_1.const_765)  # 1–3

    # Validate rune slot
    if rune_slot not in (1, 2, 3):
        print(f" Warning : Invalid rune slot: {rune_slot}")
        return

    rune_idx = rune_slot - 1

    char = next(
        (c for c in session.char_list if c.get("name") == session.current_character),
        None
    )

    equipped = char.setdefault("equippedGears", [])
    inventory = char.setdefault("inventoryGears", [])
    charms = char.setdefault("charms", [])

    # Normalize equipped gear slots
    required_slots = EntType.MAX_SLOTS - 1
    while len(equipped) < required_slots:
        equipped.append({
            "gearID": 0,
            "tier": 0,
            "runes": [0, 0, 0],
            "colors": [0, 0],
        })
    if len(equipped) > required_slots:
        equipped[:] = equipped[:required_slots]

    # Locate target gear
    gear = next(
        (g for g in equipped if g["gearID"] == gear_id and g["tier"] == gear_tier),
        None
    )

    old_rune = gear["runes"][rune_idx]

    def add_charm(charm_id, amount=1):
        for c in charms:
            if c["charmID"] == charm_id:
                c["count"] += amount
                return
        charms.append({"charmID": charm_id, "count": amount})

    def consume_charm(charm_id):
        for c in charms:
            if c["charmID"] == charm_id:
                c["count"] -= 1
                if c["count"] <= 0:
                    charms.remove(c)
                return True
        return False

    # Rune removal (ID 96)
    if rune_id == 96:
        gear["runes"][rune_idx] = 0

        if old_rune and old_rune != 96:
            add_charm(old_rune)

        if not consume_charm(96):
            print(" Warning : Rune remover (96) missing from charms")

    # Equip new rune
    else:
        gear["runes"][rune_idx] = rune_id

    inv_gear = next(
        (i for i in inventory if i["gearID"] == gear_id and i["tier"] == gear_tier),
        None
    )
    if inv_gear:
        inv_gear["runes"][rune_idx] = gear["runes"][rune_idx]
    else:
        inventory.append(gear.copy())

    save_characters(session.user_id, session.char_list)

    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)
    bb.write_method_6(gear_tier, GearType.const_176)
    bb.write_method_6(rune_id, class_64.const_101)
    bb.write_method_6(rune_slot, class_1.const_765)

    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0xB0, len(payload)) + payload
    session.conn.sendall(packet)

def handle_update_single_gear(session, data):
    br = BitReader(data[4:])

    entity_id = br.read_method_4()
    slot_raw  = br.read_method_236()        # 1-based
    gear_id   = br.read_method_6(GearType.GEARTYPE_BITSTOSEND)

    slot = slot_raw - 1  # convert to 0-based

    # Locate active character
    char = next(
        (c for c in session.char_list if c.get("name") == session.current_character),
        None
    )

    inv = char.setdefault("inventoryGears", [])
    eq  = char.setdefault("equippedGears", [])

    # Normalize equipped slots (6)
    while len(eq) < 6:
        eq.append({
            "gearID": 0,
            "tier": 0,
            "runes": [0, 0, 0],
            "colors": [0, 0],
        })

    # Find gear in inventory
    gear_data = next(
        (g for g in inv if g.get("gearID") == gear_id),
        None
    )

    if gear_data:
        gear_data = gear_data.copy()
    else:
        gear_data = {
            "gearID": gear_id,
            "tier": 0,
            "runes": [0, 0, 0],
            "colors": [0, 0],
        }
        inv.append(gear_data.copy())

    # Apply to equipped slot
    eq[slot] = gear_data

    save_characters(session.user_id, session.char_list)
    broadcast_gear_change(session, GS.all_sessions)


def handle_update_equipment(session, data):
    br = BitReader(data[4:])
    entity_id = br.read_method_9()

    char = session.current_char_dict
    equipped = char.setdefault("equippedGears", [])
    inventory = char.setdefault("inventoryGears", [])
    SLOT_COUNT = EntType.MAX_SLOTS - 1

    def empty_gear():
        return {
            "gearID": 0,
            "tier": 0,
            "runes": [0, 0, 0],
            "colors": [0, 0],
        }

    while len(equipped) < SLOT_COUNT:
        equipped.append(empty_gear())

    for slot in range(SLOT_COUNT):
        changed = br.read_method_15()

        if not changed:
            continue

        gear_id = br.read_method_20(GearType.GEARTYPE_BITSTOSEND)

        item = next(
            (g for g in inventory if g.get("gearID") == gear_id),
            None
        )

        equipped[slot] = item.copy() if item else {
            "gearID": gear_id,
            "tier": 0,
            "runes": [0, 0, 0],
            "colors": [0, 0],
        }

    save_characters(session.user_id, session.char_list)
    broadcast_gear_change(session, GS.all_sessions)


def handle_create_gearset(session, data):
    br = BitReader(data[4:])
    slot_idx = br.read_method_20(GearType.const_348)

    char = next(
        (c for c in session.char_list
         if c.get("name") == session.current_character),
        None
    )
    gearsets = char.setdefault("gearSets", [])

    while len(gearsets) <= slot_idx:
        if len(gearsets) >= Game.const_1057:
            return

        gearsets.append({
            "name": f"GearSet {len(gearsets) + 1}",
            "slots": [0] * EntType.MAX_SLOTS
        })

    save_characters(session.user_id, session.char_list)


def handle_name_gearset(session, data):
    br = BitReader(data[4:])
    slot_idx = br.read_method_20(GearType.const_348)
    name = br.read_method_26()

    char = next(
        (c for c in session.char_list
         if c.get("name") == session.current_character),
        None
    )

    gearsets = char.get("gearSets", [])
    if slot_idx >= len(gearsets):
        print("ERROR: gearset does not exist")
        return

    gearsets[slot_idx]["name"] = name

    save_characters(session.user_id, session.char_list)


def handle_update_gearset(session, data):
    br = BitReader(data[4:])
    gearset_index = br.read_method_20(GearType.const_348)
    char = session.current_char_dict

    gearsets = char.setdefault("gearSets", [])
    if gearset_index >= len(gearsets):
        print("[0xC6] Invalid gearset index", gearset_index)
        return

    equipped = char.get("equippedGears", [])

    gs = gearsets[gearset_index]
    slots = gs.setdefault("slots", [0] * 7)

    if len(slots) < 7:
        slots.extend([0] * (7 - len(slots)))
    elif len(slots) > 7:
        del slots[7:]

    for i in range(6):
        gear_id = int(equipped[i].get("gearID", 0)) if i < len(equipped) else 0
        slots[i + 1] = gear_id

    save_characters(session.user_id, session.char_list)


