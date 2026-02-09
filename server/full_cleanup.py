#!/usr/bin/env python3
"""
Complete cleanup script to remove from player save:
- All class gear (lockbox Mage/Rogue/Paladin gear IDs 1165-1182)
- All legendary mounts (mount IDs 106, 107, 108)
- All sigil market items (sigil mounts + pets: 106, 107, 108 and 65-70)
- All legendary dyes (rarity L from DyeTypes.json)
- All legendary pets (pets with typeID in legendary pet IDs)
"""
import json
import os
import shutil

# Class gear IDs: Mage 1165-1170, Rogue 1171-1176, Paladin 1177-1182
CLASS_GEAR_IDS = set(range(1165, 1183))

# Legendary mount IDs (from lockbox)
LEGENDARY_MOUNT_IDS = {106, 107, 108}

# Sigil market pet IDs
SIGIL_PET_IDS = {65, 66, 67, 68, 69, 70}

# Legendary dye IDs (rarity L from DyeTypes.json)
LEGENDARY_DYE_IDS = {1, 9, 10, 18, 24, 29, 33, 34, 44, 51, 66, 67, 85, 99, 136, 143, 181, 205, 211, 247}


def get_legendary_pet_type_ids(server_dir: str) -> set:
    """Load pet_types.json and return set of PetID where DisplayRarity == 'L'."""
    path = os.path.join(server_dir, "data", "pet_types.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {65, 66}  # fallback
    return {p["PetID"] for p in data if isinstance(p, dict) and p.get("DisplayRarity") == "L"}


def full_cleanup_save(save_path: str, backup: bool = True) -> None:
    """Remove all specified items from the save file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    legendary_pets = get_legendary_pet_type_ids(script_dir)
    
    # Combine legendary and sigil pets
    all_legendary_pets = legendary_pets | SIGIL_PET_IDS

    if backup:
        backup_path = save_path.replace(".json", ".full_cleanup_backup.json")
        shutil.copy2(save_path, backup_path)
        print(f"Yedek oluşturuldu: {backup_path}")

    with open(save_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_stats = {
        "class_gear_inv": 0,
        "class_gear_eq": 0,
        "legendary_mounts": 0,
        "sigil_mounts": 0,
        "legendary_pets": 0,
        "sigil_pets": 0,
        "legendary_dyes": 0,
    }

    for char in data.get("characters", []):
        name = char.get("name", "Bilinmeyen")

        # 1. Class gear: inventory
        inv = char.get("inventoryGears", [])
        before_inv = len(inv)
        char["inventoryGears"] = [g for g in inv if g.get("gearID") not in CLASS_GEAR_IDS]
        removed_class_gear_inv = before_inv - len(char["inventoryGears"])
        total_stats["class_gear_inv"] += removed_class_gear_inv

        # 2. Class gear: equipped
        eq = char.get("equippedGears", [])
        before_eq = len(eq)
        char["equippedGears"] = [g for g in eq if g.get("gearID") not in CLASS_GEAR_IDS]
        removed_class_gear_eq = before_eq - len(char["equippedGears"])
        total_stats["class_gear_eq"] += removed_class_gear_eq

        # 3. Legendary and sigil mounts
        mounts = char.get("mounts", [])
        before_mounts = len(mounts)
        remaining_mounts = []
        for m in mounts:
            if m in LEGENDARY_MOUNT_IDS:
                total_stats["legendary_mounts"] += 1
            elif m in SIGIL_PET_IDS:
                total_stats["sigil_mounts"] += 1
            else:
                remaining_mounts.append(m)
        char["mounts"] = remaining_mounts

        # 4. Legendary and sigil pets
        pets = char.get("pets", [])
        before_pets = len(pets)
        remaining_pets = []
        for p in pets:
            p_type = p.get("typeID")
            if p_type in legendary_pets:
                total_stats["legendary_pets"] += 1
            elif p_type in SIGIL_PET_IDS:
                total_stats["sigil_pets"] += 1
            else:
                remaining_pets.append(p)
        char["pets"] = remaining_pets

        # 5. Legendary dyes
        dyes = char.get("OwnedDyes", [])
        before_dyes = len(dyes)
        char["OwnedDyes"] = [d for d in dyes if d not in LEGENDARY_DYE_IDS]
        removed_dyes = before_dyes - len(char["OwnedDyes"])
        total_stats["legendary_dyes"] += removed_dyes

        if removed_class_gear_inv or removed_class_gear_eq or before_mounts > len(char["mounts"]) or before_pets > len(char["pets"]) or removed_dyes:
            print(
                f"{name}: "
                f"class gear env -{removed_class_gear_inv} eq -{removed_class_gear_eq} | "
                f"binek -{before_mounts - len(char['mounts'])} | "
                f"evcil hayvan -{before_pets - len(char['pets'])} | "
                f"boya -{removed_dyes}"
            )

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("\n=== ÖZET ===")
    print(f"Class gear envanter: -{total_stats['class_gear_inv']}")
    print(f"Class gear donatılan: -{total_stats['class_gear_eq']}")
    print(f"Efsanevi binekler: -{total_stats['legendary_mounts']}")
    print(f"Sigil market binekleri: -{total_stats['sigil_mounts']}")
    print(f"Efsanevi evcil hayvanlar: -{total_stats['legendary_pets']}")
    print(f"Sigil market evcil hayvanları: -{total_stats['sigil_pets']}")
    print(f"Efsanevi boyalar: -{total_stats['legendary_dyes']}")
    print(f"\nToplam silinen: {sum(total_stats.values())}")
    print(f"Kaydedildi: {os.path.abspath(save_path)}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_path = os.path.join(script_dir, "saves", "2.json")
    full_cleanup_save(default_path, backup=True)


if __name__ == "__main__":
    main()
