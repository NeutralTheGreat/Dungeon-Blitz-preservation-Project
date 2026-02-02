import json
import os
import random

# Game constants from ActionScript/Entity.txt
MONSTER_HP_TABLE = [100, 4920, 5580, 6020, 6520, 7040, 7580, 8180, 8800, 9480, 10180, 10960, 11740, 12640, 13540, 14540, 15560, 16660, 17860, 19120, 20440, 21860, 23360, 24960, 26680, 28460, 30380, 32420, 34580, 36900, 39320, 41920, 44660, 47560, 50660, 53940, 57420, 61080, 64980, 69120, 73520, 78160, 83100, 88300, 93820, 99700, 105880, 112460, 119400, 126760, 134560]
MONSTER_GOLD_TABLE = [0, 43, 46, 49, 53, 57, 61, 65, 70, 75, 80, 86, 92, 98, 106, 113, 121, 130, 139, 149, 160, 171, 184, 197, 211, 226, 243, 260, 279, 299, 320, 343, 368, 394, 422, 453, 485, 520, 557, 597, 640, 686, 735, 788, 844, 905, 970, 1040, 1114, 1194, 1280]
MONSTER_EXP_TABLE = [0, 10, 13, 15, 17, 20, 23, 26, 30, 35, 40, 46, 53, 61, 70, 80, 92, 106, 121, 139, 160, 184, 211, 243, 279, 320, 368, 422, 485, 557, 640, 735, 844, 970, 1114, 1280, 1470, 1689, 1940, 2229, 2560, 2941, 3378, 3880, 4457, 5120, 5881, 6756, 7760, 8914, 10240]

_ent_type_cache = {}

def get_ent_type(ent_name: str):
    """Loads and caches EntType data with inheritance support."""
    if not _ent_type_cache:
        load_ent_types()
    
    return _ent_type_cache.get(ent_name)

def load_ent_types():
    path = os.path.join("data", "EntTypes.json")
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
# Based on paladin_template.json gear sets
DROPPABLE_GEAR_IDS = list(range(1, 27)) + list(range(79, 160)) + list(range(200, 250))

def get_random_gear_id():
    """Returns a random gear ID for enemy drops."""
    return random.choice(DROPPABLE_GEAR_IDS)

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
