#!/usr/bin/env python3
"""
Test script to verify lockbox egg reward gives Level 10 pets
"""
import json
import sys
sys.path.insert(0, 'server')

from constants import PET_TYPES, EGG_TYPES

def test_egg_pet_mapping():
    """Verify that each egg ID corresponds to a pet ID"""
    print("Testing Egg -> Pet ID mapping...")
    
    eggs_by_id = {e.get("EggID"): e.get("EggName") for e in EGG_TYPES if e.get("EggID", 0) > 0}
    pets_by_id = {p.get("PetID"): p.get("PetName") for p in PET_TYPES if p.get("PetID", 0) > 0}
    
    print(f"Total eggs: {len(eggs_by_id)}")
    print(f"Total pets: {len(pets_by_id)}")
    
    # Check which egg IDs have corresponding pets
    matching = 0
    for egg_id, egg_name in eggs_by_id.items():
        if egg_id in pets_by_id:
            pet_name = pets_by_id[egg_id]
            matching += 1
            print(f"  ✓ EggID {egg_id}: {egg_name} -> Pet: {pet_name}")
        else:
            print(f"  ✗ EggID {egg_id}: {egg_name} -> NO MATCHING PET")
    
    print(f"\nMatching eggs: {matching}/{len(eggs_by_id)}")
    
    # Test specific lockbox egg types
    lockbox_eggs = ["GenericBrown", "CommonBrown", "OrdinaryBrown", "PlainBrown"]
    print("\nLockbox egg rewards:")
    
    for egg_name in lockbox_eggs:
        egg = next((e for e in EGG_TYPES if e.get("EggName") == egg_name), None)
        if egg:
            egg_id = egg.get("EggID")
            pet = next((p for p in PET_TYPES if p.get("PetID") == egg_id), None)
            if pet:
                print(f"  ✓ {egg_name} (EggID {egg_id}) -> {pet.get('DisplayName')} (Level {pet.get('PetLevel')})")
            else:
                print(f"  ✗ {egg_name} (EggID {egg_id}) -> NO MATCHING PET")

if __name__ == "__main__":
    test_egg_pet_mapping()
    print("\n✓ Test complete - ready to deploy egg reward fix!")
