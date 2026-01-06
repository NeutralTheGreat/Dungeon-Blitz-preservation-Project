import struct

from BitBuffer import BitBuffer
from accounts import save_characters
from bitreader import BitReader
from constants import GearType, Game, EntType, DyeType, Entity, get_dye_color
from globals import GS, send_premium_purchase

# Hints Do not delete
"""
  "gearSets": [
    {
      "name": "PvP Build",    
        "slots": [4 1181, (ChestPlate)
                  5 1180, (Gloves)
                  6 1182, (Boots)
                  3 1181, (Hat)
                  1 1177, (Sword)
                  2 1178  (Shield)
        ]
    }
  ]
"""

# ──────────────── Default full gear definitions ────────────────
# Each sub-list is [GearID, Rune1, Rune2, Rune3, Color1, Color2]
DEFAULT_GEAR = {
    "paladin": [
        [1, 0, 0, 0, 0, 0],  # Shield
        [13, 0, 0, 0, 0, 0],  # Sword
        [0, 0, 0, 0, 0, 0],  # Gloves
        [0, 0, 0, 0, 0, 0],  # Hat
        [0, 0, 0, 0, 0, 0],  # Armor
        [0, 0, 0, 0, 0, 0],  # Boots
    ],
    "rogue": [
        [39, 0, 0, 0, 0, 0],  # Off Hand/Shield
        [27, 0, 0, 0, 0, 0],  # Sword
        [0, 0, 0, 0, 0, 0],  # Gloves
        [0, 0, 0, 0, 0, 0],  # Hat
        [0, 0, 0, 0, 0, 0],  # Armor
        [0, 0, 0, 0, 0, 0],  # Boots
    ],
    "mage": [
        [53, 0, 0, 0, 0, 0],  # Staff
        [65, 0, 0, 0, 0, 0],  # Focus/Shield
        [0, 0, 0, 0, 0, 0],  # Gloves
        [0, 0, 0, 0, 0, 0],  # Hat
        [0, 0, 0, 0, 0, 0],  # Robe
        [0, 0, 0, 0, 0, 0],  # Boots
    ],
}

def build_paperdoll_packet(char):
    buf = BitBuffer()

    # Basic appearance fields
    for key in ("name", "class", "gender", "headSet", "hairSet", "mouthSet", "faceSet"):
        buf.write_method_13(char.get(key, ""))

    # Colors (24-bit each)
    for key in ("hairColor", "skinColor", "shirtColor", "pantColor"):
        buf.write_method_6(int(char.get(key, 0)), 24)

    # Build 6 gear slots
    cls = char.get("class", "").lower()
    gear_list = char.get("equippedGears", DEFAULT_GEAR.get(cls, []))

    for i in range(6):
        gear_id = 0
        if i < len(gear_list):
            slot = gear_list[i]

            if isinstance(slot, dict):
                gear_id = int(slot.get("gearID", 0))
            elif isinstance(slot, (list, tuple)):
                gear_id = int(slot[0]) if slot else 0

        buf.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)

    return buf.to_bytes()


def PaperDoll_Request(session, data):
    br = BitReader(data[4:])
    req_name = br.read_method_26()

    char = next((c for c in session.char_list if c["name"] == req_name), None)

    if char:
        payload = build_paperdoll_packet(char)
        session.conn.sendall(struct.pack(">HH", 0x1A, len(payload)) + payload)
    else:
        session.conn.sendall(struct.pack(">HH", 0x1A, 0))
        print(f"[0x19] Character '{req_name}' not found; sent empty 0x1A")

def build_login_character_list_bitpacked(user_id: int, characters):
    buf = BitBuffer()
    max_chars = 8
    char_count = len(characters)

    buf.write_method_4(int(user_id))
    buf.write_method_393(max_chars)
    buf.write_method_393(char_count)

    for char in characters:
        buf.write_method_13(char["name"])
        buf.write_method_13(char["class"])
        buf.write_method_6(char["level"], 6)
    payload = buf.to_bytes()
    header = struct.pack(">HH", 0x15, len(payload))
    return header + payload


def handle_alert_state_update(session, data):
    br = BitReader(data[4:])
    state_id = br.read_method_20(Game.const_646)
    char = session.current_char_dict

    old = char.get("alertState", 0)
    new = old | state_id
    char["alertState"] = new

    save_characters(session.user_id, session.char_list)

def build_level_gears_packet(gears: list[tuple[int, int]]) -> bytes:
    buf = BitBuffer()
    buf.write_method_4(len(gears))

    for gear_id, tier in gears:
        buf.write_method_6(gear_id, GearType.GEARTYPE_BITSTOSEND)      # 11 bits
        buf.write_method_6(tier, GearType.const_176)    # 2 bits

    payload = buf.to_bytes()
    return struct.pack(">HH", 0xF5, len(payload)) + payload

def handle_request_armory_gears(session, data):
    br = BitReader(data[4:])
    player_token = br.read_method_9()

    char = session.current_char_dict

    # Build and send the 0xF5 packet
    gears = get_inventory_gears(char)
    pkt = build_level_gears_packet(gears)
    session.conn.sendall(pkt)


def get_inventory_gears(char: dict) -> list[tuple[int, int]]:
    inventory_gears = char.get("inventoryGears", [])
    return [(gear.get("gearID", 0), gear.get("tier", 0)) for gear in inventory_gears]


LOOK_FIELDS = (
    "headSet",
    "hairSet",
    "mouthSet",
    "faceSet",
    "gender",
    "hairColor",
    "skinColor",
)


def _apply_look_update(target: dict, values: dict) -> None:
    for key in LOOK_FIELDS:
        if key in values:
            target[key] = values[key]


def send_look_update_packet(
    session,
    *,
    entity_id: int,
    head: str,
    hair: str,
    mouth: str,
    face: str,
    gender: str,
    hair_color: int,
    skin_color: int,
) -> None:
    if not session or not session.conn:
        return

    bb = BitBuffer(debug=False)

    bb.write_method_4(entity_id)
    bb.write_method_13(head)
    bb.write_method_13(hair)
    bb.write_method_13(mouth)
    bb.write_method_13(face)
    bb.write_method_13(gender)
    bb.write_method_6(hair_color, EntType.CHAR_COLOR_BITSTOSEND)
    bb.write_method_6(skin_color, EntType.CHAR_COLOR_BITSTOSEND)

    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0x8F, len(payload)) + payload

    try:
        session.conn.sendall(packet)
    except OSError:
        pass


def handle_change_look(session, data: bytes) -> None:
    if not session or not session.clientEntID:
        return

    br = BitReader(data[4:])

    look = {
        "headSet":  br.read_method_26(),
        "hairSet":  br.read_method_26(),
        "mouthSet": br.read_method_26(),
        "faceSet":  br.read_method_26(),
        "gender":   br.read_method_26(),
        "hairColor": br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND),
        "skinColor": br.read_method_20(EntType.CHAR_COLOR_BITSTOSEND),
    }

    entity_id = session.clientEntID

    ent = session.entities.get(entity_id)
    if ent:
        _apply_look_update(ent, look)

    char = next(
        (c for c in session.char_list if c.get("name") == session.current_character),
        None
    )

    if not char:
        print(f"[Look] ERROR: active character '{session.current_character}' not found")
        return

    _apply_look_update(char, look)
    save_characters(session.user_id, session.char_list)

    pkt_args = dict(
        entity_id=entity_id,
        head=look["headSet"],
        hair=look["hairSet"],
        mouth=look["mouthSet"],
        face=look["faceSet"],
        gender=look["gender"],
        hair_color=look["hairColor"],
        skin_color=look["skinColor"],
    )

    send_look_update_packet(session, **pkt_args)

    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            send_look_update_packet(other, **pkt_args)


def _parse_apply_dyes_payload(data: bytes) -> tuple[int, dict[int, tuple[int, int]], bool, int | None, int | None]:
    br = BitReader(data[4:])

    entity_id = br.read_method_4()

    dyes_by_slot: dict[int, tuple[int, int]] = {}
    for slot in range(1, EntType.MAX_SLOTS):
        has_pair = bool(br.read_method_20(1))
        if not has_pair:
            continue
        d1 = br.read_method_20(DyeType.BITS)
        d2 = br.read_method_20(DyeType.BITS)
        dyes_by_slot[slot] = (d1, d2)

    pay_with_idols = bool(br.read_method_20(1))

    shirt_dye = br.read_method_20(DyeType.BITS) if br.read_method_20(1) else None
    pants_dye = br.read_method_20(DyeType.BITS) if br.read_method_20(1) else None

    return entity_id, dyes_by_slot, pay_with_idols, shirt_dye, pants_dye


def _count_dye_units_changed(eq_gears: list[dict], dyes_by_slot: dict[int, tuple[int, int]]) -> int:
    """
    Returns the number of *individual dye channels* changed (0..2 per slot),
    matching client var_955 behavior.
    """
    units = 0

    for slot, (new1, new2) in dyes_by_slot.items():
        eq_index = slot - 1
        if eq_index < 0 or eq_index >= len(eq_gears):
            continue

        gear = eq_gears[eq_index]
        if not gear or gear.get("gearID", 0) == 0:
            continue

        old1, old2 = (gear.get("colors") or [0, 0])[:2]

        if new1 and new1 != old1:
            units += 1
        if new2 and new2 != old2:
            units += 1

    return units


def handle_apply_dyes(session, data: bytes) -> None:
    entity_id, dyes_by_slot, pay_with_idols, shirt_dye, pants_dye = _parse_apply_dyes_payload(data)

    char = session.current_char_dict
    eq  = char.setdefault("equippedGears", [])
    inv = char.setdefault("inventoryGears", [])

    level = int(char.get("level", char.get("mExpLevel", 1)) or 1)
    g_idx = min(max(level, 0), len(Entity.Dye_Gold_Cost) - 1)
    i_idx = min(max(level, 0), len(Entity.Dye_Idols_Cost) - 1)
    per_gold = int(Entity.Dye_Gold_Cost[g_idx])
    per_idol = int(Entity.Dye_Idols_Cost[i_idx])

    units = _count_dye_units_changed(eq, dyes_by_slot)
    gold_cost = per_gold * units
    idol_cost = per_idol * units

    # Shirt/pants are always free, but must convert dye id to 24 bit color
    shirt_changed = False
    pants_changed = False

    if shirt_dye is not None:
        c = get_dye_color(shirt_dye)
        if c is not None and c != char.get("shirtColor"):
            char["shirtColor"] = c
            shirt_changed = True

    if pants_dye is not None:
        c = get_dye_color(pants_dye)
        if c is not None and c != char.get("pantColor"):
            char["pantColor"] = c
            pants_changed = True

    # Charge only for gear dye changes
    if units > 0:
        if pay_with_idols:

            char["mammothIdols"] = int(char.get("mammothIdols", 0)) - idol_cost
            send_premium_purchase(session, "Dye", idol_cost)
        else:

            char["gold"] = int(char.get("gold", 0)) - gold_cost

    gear_ids_touched: set[int] = set()

    for slot, (d1, d2) in dyes_by_slot.items():
        eq_index = slot - 1
        if eq_index < 0 or eq_index >= len(eq):
            continue

        gear = eq[eq_index]
        if not gear or gear.get("gearID", 0) == 0:
            continue

        gear["colors"] = [int(d1), int(d2)]
        gid = int(gear.get("gearID", 0))
        if gid:
            gear_ids_touched.add(gid)

    if gear_ids_touched:
        by_id = {int(g.get("gearID", 0)): g for g in inv if isinstance(g, dict)}
        for eq_item in eq:
            if not isinstance(eq_item, dict):
                continue
            gid = int(eq_item.get("gearID", 0))
            if gid in gear_ids_touched:
                if gid in by_id:
                    by_id[gid]["colors"] = list(eq_item.get("colors", [0, 0]))
                else:
                    inv.append(eq_item.copy())

    save_characters(session.user_id, session.char_list)
    send_dye_sync_packet_to_level(session, entity_id)


def build_dye_sync_payload(char: dict, entity_id: int) -> bytes:
    bb = BitBuffer(debug=False)
    bb.write_method_4(entity_id)

    eq = char.get("equippedGears", []) or []

    for slot in range(1, EntType.MAX_SLOTS):
        eq_index = slot - 1
        gear = eq[eq_index] if 0 <= eq_index < len(eq) else None

        if isinstance(gear, dict) and "colors" in gear:
            d1, d2 = (gear.get("colors") or [0, 0])[:2]
            bb.write_method_6(1, 1)
            bb.write_method_6(int(d1), DyeType.BITS)
            bb.write_method_6(int(d2), DyeType.BITS)
        else:
            bb.write_method_6(0, 1)

    shirt_color = char.get("shirtColor")
    if shirt_color is not None:
        bb.write_method_6(1, 1)
        bb.write_method_6(int(shirt_color), EntType.CHAR_COLOR_BITSTOSEND)
    else:
        bb.write_method_6(0, 1)


    pant_color = char.get("pantColor")
    if pant_color is not None:
        bb.write_method_6(1, 1)
        bb.write_method_6(int(pant_color), EntType.CHAR_COLOR_BITSTOSEND)
    else:
        bb.write_method_6(0, 1)

    return bb.to_bytes()


def send_dye_sync_packet(session, payload: bytes) -> None:
    if not session or not session.conn:
        return
    pkt = struct.pack(">HH", 0x111, len(payload)) + payload
    try:
        session.conn.sendall(pkt)
    except OSError:
        pass


def send_dye_sync_packet_to_level(session, entity_id: int) -> None:
    char = session.current_char_dict
    if not char:
        return

    payload = build_dye_sync_payload(char, entity_id)

    for other in GS.all_sessions:
        if other.player_spawned and other.current_level == session.current_level:
            send_dye_sync_packet(other, payload)
