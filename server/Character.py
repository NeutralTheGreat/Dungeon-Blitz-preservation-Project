import os
import json
import struct

from BitBuffer import BitBuffer
from bitreader import BitReader
from constants import GearType, GEARTYPE_BITS, Game

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

def load_class_template(class_name: str) -> dict:
    path = os.path.join("data", f"{class_name.lower()}_template.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_level_gears_packet(gears: list[tuple[int, int]]) -> bytes:
    buf = BitBuffer()
    buf.write_method_4(len(gears))

    for gear_id, tier in gears:
        buf.write_method_6(gear_id, GEARTYPE_BITS)      # 11 bits
        buf.write_method_6(tier, GearType.const_176)    # 2 bits

    payload = buf.to_bytes()
    return struct.pack(">HH", 0xF5, len(payload)) + payload

def handle_request_armory_gears(session, data, conn):
    br = BitReader(data[4:])
    player_token = br.read_method_9()

    char = session.current_char_dict

    # Build and send the 0xF5 packet
    gears = get_inventory_gears(char)
    pkt = build_level_gears_packet(gears)
    conn.sendall(pkt)


def get_inventory_gears(char: dict) -> list[tuple[int, int]]:
    inventory_gears = char.get("inventoryGears", [])
    return [(gear.get("gearID", 0), gear.get("tier", 0)) for gear in inventory_gears]

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

CHAR_SAVE_DIR = "saves"
SAVE_PATH_TEMPLATE = "saves/{user_id}.json"

def load_characters(user_id: str) -> list[dict]:
    """Load all characters for a given user_id (new format)."""
    path = os.path.join(CHAR_SAVE_DIR, f"{user_id}.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("characters", [])


def save_characters(user_id, chars):
    final_path = os.path.join(CHAR_SAVE_DIR, f"{user_id}.json")
    tmp_path = final_path + ".tmp"

    data = {
        "user_id": user_id,
        "characters": chars
    }

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    os.replace(tmp_path, final_path)


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

        buf.write_method_6(gear_id, GEARTYPE_BITS)

    return buf.to_bytes()


def PaperDoll_Request(session, data, conn):
    br = BitReader(data[4:])
    req_name = br.read_method_26()

    char = next((c for c in session.char_list if c["name"] == req_name), None)

    if char:
        payload = build_paperdoll_packet(char)
        conn.sendall(struct.pack(">HH", 0x1A, len(payload)) + payload)
    else:
        conn.sendall(struct.pack(">HH", 0x1A, 0))
        print(f"[0x19] Character '{req_name}' not found; sent empty 0x1A")

def build_login_character_list_bitpacked(characters):
    """
    Builds the 0x15 login-character-list packet.
    """
    buf = BitBuffer()
    user_id = 1  # you’ll overwrite this per-session
    max_chars = 8
    char_count = len(characters)

    buf.write_method_4(user_id)
    buf.write_method_393(max_chars)
    buf.write_method_393(char_count)

    for char in characters:
        buf.write_method_13(char["name"])
        buf.write_method_13(char["class"])
        buf.write_method_6(char["level"], 6)
    header = struct.pack(">HH", 0x15, len(buf.to_bytes()))
    return header + buf.to_bytes()


def handle_alert_state_update(session, data):
    br = BitReader(data[4:])
    state_id = br.read_method_20(Game.const_646)
    char = session.current_char_dict

    old = char.get("alertState", 0)
    new = old | state_id
    char["alertState"] = new

    save_characters(session.user_id, session.char_list)