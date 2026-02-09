#!/usr/bin/env python3
"""
Remove from player save (all characters):
- Class gear (lockbox Mage/Rogue/Paladin gear IDs 1165-1182) from inventoryGears and equippedGears.
- All legendary mounts (mount IDs with rarity L; from data or known lockbox legendary 106, 107).
- All legendary pets (pet typeIDs with DisplayRarity L from pet_types.json).
Optional: backup save to 1.backup.json before modifying.
"""
import json
import os
import shutil

# Class gear IDs: Mage 1165-1170, Rogue 1171-1176, Paladin 1177-1182 (from Commands.py CLASS_GEAR_IDS)
CLASS_GEAR_IDS = set(range(1165, 1183))

# Legendary mount IDs (lockbox legendary; server data has no global mount rarity, these are the known L mounts)
LEGENDARY_MOUNT_IDS = {106, 107}


def get_legendary_pet_type_ids(server_dir: str) -> set:
    """Load pet_types.json and return set of PetID where DisplayRarity == 'L'."""
    path = os.path.join(server_dir, "data", "pet_types.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {65, 66}  # fallback: Lockbox01L01, Lockbox01L02
    return {p["PetID"] for p in data if isinstance(p, dict) and p.get("DisplayRarity") == "L"}


def cleanup_save(save_path: str, backup: bool = True) -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    legendary_pets = get_legendary_pet_type_ids(script_dir)

    if backup:
        backup_path = save_path.replace(".json", ".backup.json")
        shutil.copy2(save_path, backup_path)
        print(f"Yedek: {backup_path}")

    with open(save_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for char in data.get("characters", []):
        name = char.get("name", "Unknown")

        # Class gear: inventory + equipped
        inv = char.get("inventoryGears", [])
        before_inv = len(inv)
        char["inventoryGears"] = [g for g in inv if g.get("gearID") not in CLASS_GEAR_IDS]
        removed_inv = before_inv - len(char["inventoryGears"])

        eq = char.get("equippedGears", [])
        before_eq = len(eq)
        char["equippedGears"] = [g for g in eq if g.get("gearID") not in CLASS_GEAR_IDS]
        removed_eq = before_eq - len(char["equippedGears"])

        # Legendary mounts
        mounts = char.get("mounts", [])
        before_mounts = len(mounts)
        char["mounts"] = [m for m in mounts if m not in LEGENDARY_MOUNT_IDS]
        removed_mounts = before_mounts - len(char["mounts"])

        # Legendary pets
        pets = char.get("pets", [])
        before_pets = len(pets)
        char["pets"] = [p for p in pets if p.get("typeID") not in legendary_pets]
        removed_pets = before_pets - len(char["pets"])

        if removed_inv or removed_eq or removed_mounts or removed_pets:
            print(
                f"{name}: class gear inv -{removed_inv} eq -{removed_eq} | "
                f"legendary mounts -{removed_mounts} | legendary pets -{removed_pets}"
            )

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("Kaydedildi:", os.path.abspath(save_path))

    # Optional validation: ensure no class gear / legendary mount/pet remain
    _validate_cleanup(data, CLASS_GEAR_IDS, LEGENDARY_MOUNT_IDS, legendary_pets)


def _validate_cleanup(data: dict, class_gear_ids: set, legendary_mount_ids: set, legendary_pet_ids: set) -> None:
    """Verify no class gear, legendary mount, or legendary pet remains in any character."""
    ok = True
    for char in data.get("characters", []):
        name = char.get("name", "Unknown")
        inv_gear = [g.get("gearID") for g in char.get("inventoryGears", []) if g.get("gearID") in class_gear_ids]
        eq_gear = [g.get("gearID") for g in char.get("equippedGears", []) if g.get("gearID") in class_gear_ids]
        leg_mounts = [m for m in char.get("mounts", []) if m in legendary_mount_ids]
        leg_pets = [p.get("typeID") for p in char.get("pets", []) if p.get("typeID") in legendary_pet_ids]
        if inv_gear or eq_gear or leg_mounts or leg_pets:
            print(f"  [UYARI] {name}: kalan class gear inv={inv_gear} eq={eq_gear} | legend mounts={leg_mounts} | legend pets={leg_pets}")
            ok = False
    if ok:
        print("Doğrulama: Tüm karakterlerde class gear ve efsanevi binek/pet kalmadı.")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_path = os.path.join(script_dir, "saves", "1.json")
    cleanup_save(default_path, backup=True)


if __name__ == "__main__":
    main()
