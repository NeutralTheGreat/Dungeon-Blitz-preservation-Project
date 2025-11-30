import pprint
import struct

from BitBuffer import BitBuffer
from Character import save_characters
from Commands import build_loot_drop_packet
from bitreader import BitReader
from constants import LinkUpdater, Entity, PowerType
from globals import send_consumable_update, build_change_offset_y_packet

                # Helpers
    #####################################

def get_base_hp_for_level(level):
    if level < 1:
        level = 1
    if level >= len(Entity.PLAYER_HITPOINTS):
        level = len(Entity.PLAYER_HITPOINTS) - 1
    return Entity.PLAYER_HITPOINTS[level]

        # game client function handlers
       #####################################

def handle_entity_destroy(session, data, all_sessions):
    br = BitReader(data[4:])
    entity_id = br.read_method_9()

    # Remove the entity from this session's view
    session.entities.pop(entity_id, None)

    # If this was the client’s own entity, clear reference
    if session.clientEntID == entity_id:
        session.clientEntID = None

    # Broadcast unchanged packet to other players in same level
    for other in all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_buff_tick_dot(session, data, all_sessions):
    br = BitReader(data[4:])
    target_id = br.read_method_9()
    source_id = br.read_method_9()
    power_type_id = br.read_method_9()
    amount = br.read_method_24()

    # Broadcast unchanged packet to other players in same level
    for other in all_sessions:
        if (
                other is not session
                and other.player_spawned
                and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_respawn_broadcast(session, data, all_sessions):
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
    bb.write_signed_method_45(heal_amount)
    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x82, len(payload)) + payload

    for other in all_sessions:
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

def handle_power_hit(session, data, all_sessions):
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
    for other in all_sessions:
        if (
                other is not session
                and other.player_spawned
                and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_projectile_explode(session, data, all_sessions):
    br = BitReader(data[4:])
    entity_id      = br.read_method_9()
    remote_missile = br.read_method_9()
    coordinate_x   = br.read_method_24()
    coordinate_y   = br.read_method_24()
    is_crit        = br.read_method_15()

    # Broadcast unchanged packet to all other players in same level
    for other in all_sessions:
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
def handle_add_buff(session, data, all_sessions):
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
    for other in all_sessions:
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
def handle_remove_buff(session, data, all_sessions):
    br = BitReader(data[4:])
    entity_id      = br.read_method_9()
    buff_type_id   = br.read_method_9()
    instance_id    = br.read_method_9()

    # Broadcast packet unchanged to other players in the same level
    for other in all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_change_max_speed(session, data, all_sessions):
    br = BitReader(data[4:])
    entity_id     = br.read_method_9()
    speed_mod_int = br.read_method_9()
    for other in all_sessions:
        if (
            other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

#TODO... this is just for testing
def handle_grant_reward(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        grantor_id    = br.read_method_9()
        target_id     = br.read_method_9()

        flag_showXP   = bool(br.read_method_15())
        xp_rate       = br.read_float()

        flag_showGold = bool(br.read_method_15())
        gold_rate     = br.read_float()

        flag_showHeal = bool(br.read_method_15())
        flag_showMana = bool(br.read_method_15())

        code_xpType   = br.read_method_9()
        code_goldType = br.read_method_9()
        code_manaType = br.read_method_9()
        code_healType = br.read_method_9()

        # **NOW** read the drop coordinates:
        drop_x = br.read_method_24()   # signed 24-bit
        drop_y = br.read_method_24()   # signed 24-bit

        has_extra     = bool(br.read_method_15())
        extra_id      = br.read_method_9() if has_extra else None

    except Exception as e:
        print("…parsing error…")
        return

    # now build loot_drops using the true drop_x, drop_y:
    loot_drops = []
    if flag_showXP:
        loot_drops.append(('xp', code_xpType, int(xp_rate)))
    if flag_showGold:
        loot_drops.append(('gold', code_goldType, int(gold_rate)))
    if flag_showHeal:
        loot_drops.append(('healing', code_healType, 0))
    if flag_showMana:
        loot_drops.append(('mana', code_manaType, 0))
    if extra_id:
        # the client expects two fixed‐width values for gear:
        loot_drops.append(('gear', extra_id, extra_id))

    # broadcast one 0x32 per drop:
    for rtype, v1, v2 in loot_drops:
        pkt = build_loot_drop_packet(
            entity_id=target_id,
            x=drop_x,
            y=drop_y,
            reward_type=rtype,
            value1=v1,
            value2=v2
        )
        for other in all_sessions:
            if other.player_spawned and other.current_level == session.current_level:
                other.conn.sendall(pkt)

def handle_power_cast(session, data, all_sessions):
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
    for other in all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_change_offset_y(session, data, all_sessions):
    br = BitReader(data[4:])
    entity_id = br.read_method_9()
    offset_y  = br.read_method_739()

    pkt = build_change_offset_y_packet(entity_id, offset_y)

    for s in all_sessions:
        if s is not session and s.player_spawned and s.current_level == session.current_level:
            try:
                s.conn.sendall(pkt)
            except:
                pass