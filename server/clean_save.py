#!/usr/bin/env python3
"""
Script to clean player save file:
1. Remove legendary dyes from OwnedDyes and dyes lists
2. Remove lockbox class gear items from pets
3. Remove sigil market owned items (lockbox mounts/pets) from inventory
"""

import json
import os

# DyeTypes data - Legendary dyes have rarity "L"
LEGENDARY_DYE_IDS = [
    1,   # Brood Mother Black
    9,   # Clearcast Pearl
    10,  # Wizard Wool White
    18,  # Astral Obsidian
    24,  # Gleaming Gold
    29,  # Shining Silver
    33,  # Mighty Mammoth Ivory
    34,  # Fiery Phoenix Feather
    44,  # Velvet Valkyries
    51,  # Year Of The Mammoth
    66,  # Cheerocracy Pack Pink
    67,  # Elegant Emerald
    85,  # Leviathan Lapis Lazuli
    99,  # Alluring Amethyst
    136, # Sparkling Tourmaline
    143, # Dragon Coat Red
    181, # Iridescent Opal
    205, # Hail To The Forest
    211, # Broken Heart Black
    247, # Frostlord Satin
]

# Sigil Market Lockbox Items - Mount IDs (from mount_ids.json)
# These are the lockbox mounts that appear in sigil market
SIGIL_LOCKBOX_MOUNT_IDS = [
    106, # MountLockbox01L01 - Ivorstorm Guardian (Legendary)
    107, # MountLockbox01L02 - Hatebreed Charger (Legendary)
    108, # MountLockbox01R01 - Stormhoof Stallion (Rare)
]

# Sigil Market Lockbox Pets - Pet Type IDs
# Pet types based on pet_types.json lockbox pets
SIGIL_LOCKBOX_PET_TYPE_IDS = [
    65,  # Lockbox01L01 - Darkheart Apparition (Legendary)
    66,  # Lockbox01L02 - Dreamscale Dragonette (Legendary)
    67,  # Lockbox01RRed - Accursed Counselor (Rare)
    68,  # Lockbox01RYellow - Ruined Counselor (Rare)
    69,  # Lockbox01RBlue - Hexed Counselor (Rare)
    70,  # Lockbox01RGreen - Doomed Counselor (Rare)
]

def load_save(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_file(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {filepath}")

def clean_save(filepath):
    data = load_save(filepath)
    
    for char in data.get("characters", []):
        print(f"\n=== Cleaning character: {char.get('name', 'Unknown')} ===")
        
        # 1. Remove legendary dyes from OwnedDyes
        owned_dyes = char.get("OwnedDyes", [])
        original_count = len(owned_dyes)
        char["OwnedDyes"] = [d for d in owned_dyes if d not in LEGENDARY_DYE_IDS]
        removed_count = original_count - len(char["OwnedDyes"])
        print(f"[OwnedDyes] Removed {removed_count} legendary dyes (from {original_count} to {len(char['OwnedDyes'])})")
        
        # 2. Remove legendary dyes from dyes list (string names)
        dyes_list = char.get("dyes", [])
        original_dyes = len(dyes_list)
        char["dyes"] = []  # Clear all legendary dyes (they are all legendary in this list based on the names)
        print(f"[dyes] Removed {original_dyes} legendary dye names")
        
        # 3. Remove sigil market lockbox mounts
        mounts = char.get("mounts", [])
        original_mounts = len(mounts)
        char["mounts"] = [m for m in mounts if m not in SIGIL_LOCKBOX_MOUNT_IDS]
        removed_mounts = original_mounts - len(char["mounts"])
        print(f"[mounts] Removed {removed_mounts} lockbox mounts (IDs: {SIGIL_LOCKBOX_MOUNT_IDS})")
        
        # 4. Remove sigil market lockbox pets
        pets = char.get("pets", [])
        original_pets = len(pets)
        char["pets"] = [p for p in pets if p.get("typeID") not in SIGIL_LOCKBOX_PET_TYPE_IDS]
        removed_pets = original_pets - len(char["pets"])
        print(f"[pets] Removed {removed_pets} lockbox pets (TypeIDs: {SIGIL_LOCKBOX_PET_TYPE_IDS})")
        
    save_file(filepath, data)
    print("\n=== Cleanup complete! ===")

if __name__ == "__main__":
    save_path = os.path.join(os.path.dirname(__file__), "saves", "2.json")
    clean_save(save_path)
