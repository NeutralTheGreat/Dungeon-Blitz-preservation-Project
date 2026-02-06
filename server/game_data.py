import json
import os
import random

# Game constants from ActionScript/Entity.txt
MONSTER_HP_TABLE = [100, 4920, 5580, 6020, 6520, 7040, 7580, 8180, 8800, 9480, 10180, 10960, 11740, 12640, 13540, 14540, 15560, 16660, 17860, 19120, 20440, 21860, 23360, 24960, 26680, 28460, 30380, 32420, 34580, 36900, 39320, 41920, 44660, 47560, 50660, 53940, 57420, 61080, 64980, 69120, 73520, 78160, 83100, 88300, 93820, 99700, 105880, 112460, 119400, 126760, 134560]
MONSTER_GOLD_TABLE = [0, 43, 46, 49, 53, 57, 61, 65, 70, 75, 80, 86, 92, 98, 106, 113, 121, 130, 139, 149, 160, 171, 184, 197, 211, 226, 243, 260, 279, 299, 320, 343, 368, 394, 422, 453, 485, 520, 557, 597, 640, 686, 735, 788, 844, 905, 970, 1040, 1114, 1194, 1280]
MONSTER_EXP_TABLE = [0, 10, 13, 15, 17, 20, 23, 26, 30, 35, 40, 46, 53, 61, 70, 80, 92, 106, 121, 139, 160, 184, 211, 243, 279, 320, 368, 422, 485, 557, 640, 735, 844, 970, 1114, 1280, 1470, 1689, 1940, 2229, 2560, 2941, 3378, 3880, 4457, 5120, 5881, 6756, 7760, 8914, 10240]

# Player XP thresholds for levels 1-50 (index 0 unused, index 1 = level 1, etc.)
# Based on the client's XP display showing ~4.3M for level 50 threshold
PLAYER_XP_THRESHOLDS = [
    0,          # Level 0 (unused)
    0,          # Level 1
    100,        # Level 2
    350,        # Level 3
    750,        # Level 4
    1400,       # Level 5
    2400,       # Level 6
    3900,       # Level 7
    6000,       # Level 8
    9000,       # Level 9
    13000,      # Level 10
    18500,      # Level 11
    26000,      # Level 12
    36000,      # Level 13
    49000,      # Level 14
    66000,      # Level 15
    88000,      # Level 16
    116000,     # Level 17
    152000,     # Level 18
    198000,     # Level 19
    256000,     # Level 20
    330000,     # Level 21
    424000,     # Level 22
    544000,     # Level 23
    697000,     # Level 24
    893000,     # Level 25
    1143000,    # Level 26
    1462000,    # Level 27
    1869000,    # Level 28
    2387000,    # Level 29
    3047000,    # Level 30
    3420000,    # Level 31
    3550000,    # Level 32
    3680000,    # Level 33
    3810000,    # Level 34
    3940000,    # Level 35
    4070000,    # Level 36
    4100000,    # Level 37
    4130000,    # Level 38
    4160000,    # Level 39
    4190000,    # Level 40
    4220000,    # Level 41
    4250000,    # Level 42
    4280000,    # Level 43
    4295000,    # Level 44
    4310000,    # Level 45
    4325000,    # Level 46
    4340000,    # Level 47
    4355000,    # Level 48
    4367860,    # Level 49 (when you get this, you're at level 49)
    4500000,    # Level 50 (if XP >= this, you're at max level 50)
]

def get_player_level_from_xp(xp: int) -> int:
    """Calculate player level based on XP. Returns level 1-50."""
    for level in range(len(PLAYER_XP_THRESHOLDS) - 1, 0, -1):
        if xp >= PLAYER_XP_THRESHOLDS[level]:
            return min(level, 50)
    return 1

_ent_type_cache = {}

def get_ent_type(ent_name: str):
    """Loads and caches EntType data with inheritance support."""
    if not _ent_type_cache:
        load_ent_types()
    
    return _ent_type_cache.get(ent_name)

def load_ent_types():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "data", "EntTypes.json")
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    raw_list = data.get("EntTypes", {}).get("EntType", [])
    raw_dict = {item["EntName"]: item for item in raw_list}

    # Resolve inheritance and parse scalars
    for name in raw_dict:
        _ent_type_cache[name] = _resolve_type(name, raw_dict)

def _resolve_type(name, raw_dict):
    item = raw_dict.get(name)
    if not item: return {}

    parent_name = item.get("parent")
    resolved = {}
    if parent_name and parent_name != "none" and parent_name in raw_dict:
        resolved = _resolve_type(parent_name, raw_dict).copy()
    
    # Overlay current properties
    for k, v in item.items():
        resolved[k] = v

    return resolved

def calculate_npc_hp(ent_name, level):
    ent_type = get_ent_type(ent_name)
    if not ent_type: 
        return 100 # Fallback
    
    scalar = float(ent_type.get("HitPoints", 1.0))
    # Clamp level to table size
    idx = max(0, min(level, len(MONSTER_HP_TABLE) - 1))
    
    return round(MONSTER_HP_TABLE[idx] * scalar)

def calculate_npc_gold(ent_name, level):
    ent_type = get_ent_type(ent_name)
    if not ent_type:
        return 0

    gold_drop_str = ent_type.get("GoldDrop", "0")
    scalars = str(gold_drop_str).split(",")
    primary_scalar = float(scalars[0])
    
    idx = max(0, min(level, len(MONSTER_GOLD_TABLE) - 1))
    base_gold = MONSTER_GOLD_TABLE[idx]
    
    # Rank Multiplier
    rank = ent_type.get("EntRank", "Minion")
    rank_mult = 1.0
    if rank == "Lieutenant":
        rank_mult = 3.0
    elif rank in ["MiniBoss", "Boss"]:
        rank_mult = 10.0
    
    # Formula from Entity.txt: _loc26_ = _loc10_ + uint((_loc10_ * 2 + 1) * Math.random());
    loc10 = primary_scalar * base_gold * 0.5 * rank_mult
    reward = loc10 + (loc10 * 2 + 1) * random.random()
    
    return int(reward)

def calculate_npc_exp(ent_name, level):
    ent_type = get_ent_type(ent_name)
    if not ent_type:
        return 0

    exp_mult = float(ent_type.get("ExpMult", 1.0))
    idx = max(0, min(level, len(MONSTER_EXP_TABLE) - 1))
    
    return round(MONSTER_EXP_TABLE[idx] * exp_mult)


# Valid gear ID ranges for random drops
# We will now load them dynamically from class templates
_gear_ids_by_class = {}
DROPPABLE_GEAR_IDS_FALLBACK = list(range(1, 27)) + list(range(79, 160)) + list(range(200, 250))

# Specific Drops (Realm/Boss)
_gear_data = None

def load_gear_data():
    global _gear_data
    if _gear_data: return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "data", "gear_data.json")
    if not os.path.exists(path):
        print(f"[WARN] gear_data.json not found at {path}")
        _gear_data = {"realm_drops": {}, "boss_drops": {}, "global_drops": []}
        return

    with open(path, "r", encoding="utf-8") as f:
        _gear_data = json.load(f)




def get_gear_id_for_entity(ent_name):
    """
    Returns a valid gear ID for the given entity based on Name (Boss) or Realm.
    Returns None if no valid drops found.
    """
    if not _gear_data:
        load_gear_data()
    
    ent_type = get_ent_type(ent_name)
    if not ent_type:
        return None
    
    # 1. Check Boss Drops (Specific Entity Name)
    # Some bosses might have specific drops defined by name in gear_data
    if ent_name in _gear_data.get("boss_drops", {}):
        return random.choice(_gear_data["boss_drops"][ent_name])
    
    # 2. Check Realm Drops
    realm = ent_type.get("Realm")
    if realm and realm in _gear_data.get("realm_drops", {}):
        return random.choice(_gear_data["realm_drops"][realm])
    
    # 3. Fallback: If no Realm or Boss match, but we have global drops?
    # The user request implies strict drops ("check which item drops on who/which map").
    # If the item doesn't have a Realm/Boss assigned, maybe it drops everywhere?
    # For now, let's include global drops if no specific realm match found.
    if _gear_data.get("global_drops"):
        return random.choice(_gear_data["global_drops"])
        
    return None


def load_class_gear_ids():
    """Loads class-specific gear IDs from template files."""
    if _gear_ids_by_class:
        return

    templates = {
        "Paladin": "paladin_template.json",
        "Rogue": "rogue_template.json",
        "Mage": "mage_template.json"
    }

    for cls, filename in templates.items():
        path = os.path.join("data", filename)
        if not os.path.exists(path):
            print(f"[WARN] {filename} not found")
            continue
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                inventory = data.get("inventoryGears", [])
                # Collect all gearIDs from the inventory
                gear_ids = [item.get("gearID", 0) for item in inventory if item.get("gearID", 0) > 0]
                # Also include equipped gears if any
                equipped = data.get("equippedGears", [])
                gear_ids.extend([item.get("gearID", 0) for item in equipped if item.get("gearID", 0) > 0])
                
                _gear_ids_by_class[cls] = list(set(gear_ids)) # De-duplicate
                # print(f"[INFO] Loaded {len(_gear_ids_by_class[cls])} gear IDs for {cls}")
        except Exception as e:
            print(f"[ERROR] Failed to load {filename}: {e}")

def get_random_gear_id(class_name=None):
    """Returns a random gear ID for enemy drops.
       If class_name is provided, tries to return a gear ID suitable for that class.
    """
    if not _gear_ids_by_class:
        load_class_gear_ids()

    if class_name and class_name in _gear_ids_by_class:
        ids = _gear_ids_by_class[class_name]
        if ids:
            return random.choice(ids)
    
    if class_name:
         # Try to match case-insensitive
         for key in _gear_ids_by_class:
             if key.lower() == class_name.lower():
                 ids = _gear_ids_by_class[key]
                 if ids:
                     return random.choice(ids)

    # Legacy fallback - prefer get_gear_id_for_entity now
    return random.choice(DROPPABLE_GEAR_IDS_FALLBACK)


# Material system
_materials_by_realm = {}

def load_materials():
    """Load materials.json and organize by Realm."""
    if _materials_by_realm:
        return  # Already loaded
    
    path = os.path.join("data", "Materials.json")
    if not os.path.exists(path):
        print("[WARN] Materials.json not found")
        return
    
    with open(path, "r", encoding="utf-8") as f:
        materials = json.load(f)
    
    # Group materials by Realm and Rarity
    for mat in materials:
        realm = mat.get("DropRealm", "").strip()
        rarity = mat.get("Rarity", "M").strip()
        mat_id = int(mat.get("MaterialID", 0))
        
        if realm and mat_id > 0:
            if realm not in _materials_by_realm:
                _materials_by_realm[realm] = {"M": [], "R": [], "L": []}
            
            _materials_by_realm[realm][rarity].append(mat_id)

def get_random_material_for_realm(realm):
    """
    Returns a random material ID for the given Realm.
    Rarity chances: 70% Common (M), 25% Rare (R), 5% Legendary (L)
    """
    if not _materials_by_realm:
        load_materials()
    
    if realm not in _materials_by_realm:
        return None
    
    roll = random.random()
    if roll < 0.05 and _materials_by_realm[realm]["L"]:
        # 5% Legendary
        return random.choice(_materials_by_realm[realm]["L"])
    elif roll < 0.30 and _materials_by_realm[realm]["R"]:
        # 25% Rare (0.05 to 0.30)
        return random.choice(_materials_by_realm[realm]["R"])
    else:
        # 70% Common
        if _materials_by_realm[realm]["M"]:
            return random.choice(_materials_by_realm[realm]["M"])
    
    return None

def calculate_drop_data(ent_name, ent_level, ent_rank="Minion", item_find_bonus=0.0):
    """
    Determines if gear should drop and what tier.
    Returns: (should_drop_gear, gear_tier)
    
    Tiers:
      0: Common
      1: Rare
      2: Legendary (Locked if level < 15)
    
    Base Chances (Cumulative):
      Legendary: 0.2% (0.000 - 0.002)
      Rare:      0.4% (0.002 - 0.006)
      Common:    1.0% (0.006 - 0.016)
    
    item_find_bonus: Multiplier from player's equipped charms (e.g., 0.10 = +10%)
    """
    # 1. Check strict requirements
    # Legendary (Tier 2) is blocked for early game
    can_drop_legendary = (ent_level >= 15)

    roll = random.random()
    
    # Apply item find bonus to thresholds (increases drop chance)
    find_mult = 1.0 + item_find_bonus
    
    # 2. Check Legendary Drop (Tier 2) - 0.2% Chance
    legendary_threshold = 0.002 * find_mult
    if can_drop_legendary and roll < legendary_threshold:
        return True, 2
        
    # 3. Check Rare Drop (Tier 1) - 0.4% Chance
    # Cumulative threshold: 0.002 + 0.004 = 0.006
    rare_threshold = 0.006 * find_mult
    if roll < rare_threshold:
        # If we are here, it's < 0.006. 
        # If it was < 0.002 and legendary was blocked, it becomes Rare.
        return True, 1
        
    # 4. Check Common Drop (Tier 0) - 1.0% Chance
    # Cumulative threshold: 0.006 + 0.010 = 0.016
    common_threshold = 0.016 * find_mult
    if roll < common_threshold:
        return True, 0
        
    return False, 0

