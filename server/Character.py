

import os
import json
import struct

from BitBuffer import BitBuffer
from constants import GearType, GEARTYPE_BITS

def load_class_template(class_name: str) -> dict:
    path = os.path.join("data", f"{class_name.lower()}_template.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_level_gears_packet(gears_list: list[tuple[int, int]]) -> bytes:
    buf = BitBuffer()
    buf.write_method_4(len(gears_list))  # Write number of gears
    for gear_id, tier in gears_list:
        buf.write_method_6(gear_id, GEARTYPE_BITS)  # 11 bits for gearID
        buf.write_method_6(tier, GearType.const_176)  # 2 bits for tier
    payload = buf.to_bytes()
    return struct.pack(">HH", 0xF5, len(payload)) + payload

def get_inventory_gears(char: dict) -> list[tuple[int, int]]:
    inventory_gears = char.get("inventoryGears", [])
    return [(gear.get("gearID", 0), gear.get("tier", 0)) for gear in inventory_gears]
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
  "magicForge": {
  "stats_by_building": {
          "1": 10, # "Tome"
          "2": 10, # "Forge"
          
          "3": 10, # "JusticarTower"
          "4": 10, # "SentinelTower"
          "5": 10, # "TemplarTower"
          
          "6": 10, # "FrostwardenTower"
          "7": 10, # "FlameseerTower"
          "8": 10, # "NecromancerTower"
          
          "9": 10, # "ExecutionerTower"
          "10": 10, # "ShadowwalkerTower"
          "11": 10, # "SoulthiefTower"
          
          "12": 0, # "Keep"
          "13": 10 # "Barn"
        },
  "hasSession": true,    // 1bit: whether a forge session exists (controls reading the session block)
  "primary": 90,         // primary gem/charm type ID (6 bits)
  "secondary": 5,        // secondary buff ID (only read if status==2 and var_8==1)
  "status": 1,           // 1=in‑progress (timer), 2=completed (secondary buffs)
  "duration": 900000,    // remaining time in ms (used to compute endtime when status==1)
  "var_8": 1,            // flag for “secondary present” (1 bit, read only when status!=1)
  "usedlist": 2,         // number of items/idols used or buff count (read if var_8==1)
  "var_2675": 2,         // extra small stat #1 (16 bits, always read)
  "var_2316": 2,         // extra small stat #2 (16 bits, always read)
  "var_2434": true       // final continuation flag (1 bit; often used to toggle UI)
}
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

CHAR_SAVE_DIR = "saves"
SAVE_PATH_TEMPLATE = "saves/{user_id}.json"

def load_characters(user_id: str) -> list[dict]:
    """Load the list of characters for a given user_id."""
    path = os.path.join(CHAR_SAVE_DIR, f"{user_id}.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("characters", [])

def save_characters(user_id: str, char_list: list[dict]):
    """Save the list of characters for a given user_id, preserving other fields."""
    os.makedirs(CHAR_SAVE_DIR, exist_ok=True)
    path = os.path.join(CHAR_SAVE_DIR, f"{user_id}.json")
    # Load existing to preserve email and other fields
    if user_id is None:
        print("Warning: Attempted to save characters with user_id=None")
        return
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"email": None, "characters": []}
    data["characters"] = char_list
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def build_paperdoll_packet(character_dict):
    buf = BitBuffer(debug=True)  # Enable debug for tracing
    buf.write_method_13(character_dict["name"])
    buf.write_method_13(character_dict["class"])
    buf.write_method_13(character_dict["gender"])
    buf.write_method_13(character_dict["headSet"])
    buf.write_method_13(character_dict["hairSet"])
    buf.write_method_13(character_dict["mouthSet"])
    buf.write_method_13(character_dict["faceSet"])
    buf.write_method_6(character_dict["hairColor"], 24)
    buf.write_method_6(character_dict["skinColor"], 24)
    buf.write_method_6(character_dict["shirtColor"], 24)
    buf.write_method_6(character_dict["pantColor"], 24)

    # Add gear slots (slots 1 to 6, as slot 0 is skipped)
    cls = character_dict["class"].lower()
    # Prefer equippedGears if available, else fall back to DEFAULT_GEAR
    gear_list = character_dict.get("equippedGears", DEFAULT_GEAR.get(cls, [[0] * 6] * 6))

    for i in range(6):  # Process exactly 6 slots (1 to 6)
        if i < len(gear_list):
            slot = gear_list[i]
            # Handle both dictionary (equippedGears) and list (DEFAULT_GEAR) formats
            if isinstance(slot, dict):
                gear_id = slot.get("gearID", 0)
            elif isinstance(slot, (list, tuple)) and len(slot) > 0:
                gear_id = slot[0]
            else:
                gear_id = 0
        else:
            gear_id = 0
        buf.write_method_6(gear_id, 11)  # GearType.GEARTYPE_BITSTOSEND = 11
        if buf.debug:
            buf.debug_log.append(f"gear_slot_{i + 1}_gearID={gear_id}")
    return buf.to_bytes()

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