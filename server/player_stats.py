"""
Player stats calculation utilities.
Calculates find bonuses (gold/material/gear) from equipped gear runes.
"""

import json
import os

# Cache for charm data by ID
_charms_by_id = {}

def load_charms():
    """Load Charms.json and cache by CharmID."""
    global _charms_by_id
    if _charms_by_id:
        return  # Already loaded

    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "data", "Charms.json")
    
    if not os.path.exists(path):
        print(f"[WARN] Charms.json not found at {path}")
        return
    
    with open(path, "r", encoding="utf-8") as f:
        charms = json.load(f)
    
    for charm in charms:
        charm_id = int(charm.get("CharmID", 0))
        if charm_id > 0:
            _charms_by_id[charm_id] = charm


def get_charm_data(charm_id: int) -> dict:
    """Get charm data by ID."""
    if not _charms_by_id:
        load_charms()
    return _charms_by_id.get(charm_id, {})


def calculate_find_bonuses(char: dict) -> dict:
    """
    Calculate find bonuses from all equipped gear runes.
    
    Returns:
        dict: {
            "gold_find": float,   # From GoldDrop (e.g., 0.10 = +10%)
            "item_find": float,   # From ItemDrop (gear find)
            "craft_find": float   # From CraftDrop (material find)
        }
    """
    if not _charms_by_id:
        load_charms()
    
    bonuses = {
        "gold_find": 0.0,
        "item_find": 0.0,
        "craft_find": 0.0
    }
    
    equipped_gears = char.get("equippedGears", [])
    
    for gear in equipped_gears:
        if not gear or not isinstance(gear, dict):
            continue
        
        runes = gear.get("runes", [0, 0, 0])
        
        for rune_id in runes:
            if rune_id <= 0:
                continue
            
            charm = _charms_by_id.get(rune_id, {})
            
            # Sum up the find bonuses
            gold_drop = charm.get("GoldDrop")
            if gold_drop:
                bonuses["gold_find"] += float(gold_drop)
            
            item_drop = charm.get("ItemDrop")
            if item_drop:
                bonuses["item_find"] += float(item_drop)
            
            craft_drop = charm.get("CraftDrop")
            if craft_drop:
                bonuses["craft_find"] += float(craft_drop)
    
    return bonuses


def get_modified_gold(base_gold: int, gold_find: float) -> int:
    """Apply gold find bonus to base gold amount."""
    return int(base_gold * (1.0 + gold_find))


def get_modified_drop_chance(base_chance: float, find_bonus: float) -> float:
    """
    Apply find bonus to drop chance.
    
    Example: base_chance=0.30, find_bonus=0.10 -> 0.33 (10% more likely)
    """
    return base_chance * (1.0 + find_bonus)
